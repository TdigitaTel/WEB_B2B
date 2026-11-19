"""Regression cases for signed returns and real observation-day averages."""
from datetime import date,timedelta
import pytest
from app.replenishment_engine import Parameters,prepare_context,calculate_article,calculate_all_bases
from app.procurement_engine import calculate as purchase


def snapshot(start='2026-08-01',end='2026-08-31'):
    return {'consumption_method':'NET_PERIOD_V2','captured_at':'2026-09-01T00:00:00+00:00','start':start,'end':end,
        'articles':[{'sku':'03283','description':'Material','unit_type':'PZ','created_at':'2020-01-01','exit_multiple':10,
                     'procurement_coverage_days':90,'procurement_lead_days':5}],
        'sales':[], 'stocks':[{'sku':'03283','delegation':d,'stock':0,'incoming':0,'outgoing':0} for d in ('00','01','02','04','05')]}


def event(day,sold=0,returned=0,delegation='02'):
    return {'sku':'03283','delegation':delegation,'day':day,'sold':sold,'returned':returned}


def result(raw,**params):
    options={'simple_formula':True,'use_safety_stock':False,'multiple_mode':'NONE',**params}
    return calculate_article(raw['articles'][0],'02',prepare_context(raw,['02'],[],options),include_daily=True)


def test_returns_on_different_days_are_fully_deducted_and_legacy_is_reproducible():
    raw=snapshot();raw['sales']=[event('2026-08-02',sold=23),event('2026-08-10',returned=19)]
    row=result(raw)
    assert (row['gross_sales'],row['returns'],row['total_demand'],row['observed_days'])==(23,19,4,31)
    assert row['daily_mean']==pytest.approx(4/31)
    assert row['daily_reference']==pytest.approx(4/31)
    assert row['monthly_mean']==pytest.approx(4/31*30)  # Display reference only.
    assert row['monthly_consumption'][0]['sold']==23 and row['monthly_consumption'][0]['returned']==19
    assert row['monthly_consumption'][0]['consumption']==4
    assert row['monthly_consumption'][0]['daily_mean']==pytest.approx(4/31)
    assert row['monthly_consumption'][0]['monthly_consumption']==4
    assert not row['monthly_consumption'][0]['estimated']
    assert row['daily_sales'][9]['demand']==-19
    assert sum(w['demand'] for w in row['weekly_sales'])==4
    assert sum(d['demand'] for d in row['daily_sales'])==4
    assert row['consumption_method']=='NET_PERIOD_V2'
    del raw['consumption_method']
    old=result(raw)
    assert old['total_demand']==23 and old['daily_mean']==pytest.approx(23/30)
    assert old['daily_sales'][9]['demand']==0
    assert old['consumption_method']=='MONTHLY_NORMALIZED_V1'


def test_partial_months_use_real_days_and_include_months_without_movements():
    raw=snapshot('2026-01-30','2026-03-02')
    raw['sales']=[event('2026-01-30',sold=12),event('2026-03-02',sold=20)]
    row=result(raw)
    assert row['observed_days']==32 and row['total_demand']==32
    assert row['daily_mean']==1
    assert [m['observed_days'] for m in row['monthly_consumption']]==[2,28,2]
    assert [m['consumption'] for m in row['monthly_consumption']]==[12,0,20]
    assert [m['daily_mean'] for m in row['monthly_consumption']]==[6,0,10]
    assert not any(m['estimated'] for m in row['monthly_consumption'])
    assert row['daily_mean']!=pytest.approx((6+0+10)/3)


def test_leap_month_and_effective_history_window():
    raw=snapshot('2024-02-01','2024-02-29');raw['sales']=[event('2024-02-01',sold=29)]
    assert result(raw)['daily_mean']==1
    raw['articles'][0]['created_at']='2024-02-20';raw['sales']=[event('2024-02-29',sold=10)]
    row=result(raw)
    assert row['observed_days']==10 and row['daily_mean']==1
    row=result(raw,history_days=5)
    assert row['observed_days']==5 and row['daily_mean']==2


def test_negative_net_keeps_actual_balance_but_planning_never_uses_negative_demand():
    raw=snapshot();raw['sales']=[event('2026-08-02',sold=5),event('2026-08-10',returned=12)]
    row=result(raw)
    assert row['total_demand']==-7 and row['daily_mean']==pytest.approx(-7/31)
    assert row['daily_reference']==0 and row['minimum_stock']==0 and row['maximum_stock']==0
    assert row['final_quantity']==0
    assert any(note['code']=='NETO_NEGATIVO' for note in row['recommendations'])
    variants=calculate_all_bases(raw,['02'],[],{'simple_formula':True,'use_safety_stock':False,'multiple_mode':'NONE'})
    assert variants[0]['total_demand']==-7


def test_spot_comparison_retains_returns_and_percentage_uses_positive_days():
    raw=snapshot('2026-04-01','2026-04-30')
    raw['sales']=[event((date(2026,4,1)+timedelta(days=i)).isoformat(),sold=30 if i==1 else 0 if i==0 else 1,returned=19 if i==0 else 0) for i in range(30)]
    row=result(raw);spot=row['spot_analysis']
    assert row['total_demand']==39 and row['daily_mean']==pytest.approx(39/30)
    assert spot['daily_mean_without_peaks']==pytest.approx(9/30)
    assert spot['flagged_share_percent']==pytest.approx(30/58*100)
    assert spot['share_basis']=='POSITIVE_DAILY_NET'


def test_procurement_nets_returns_across_dates_and_branches():
    raw=snapshot();raw['sales']=[event('2026-08-02',sold=23),event('2026-08-10',returned=19,delegation='00')]
    row=purchase(raw,use_safety_stock=False)[0]
    assert row['gross_sales']==23 and row['returns']==19 and row['total_demand']==4
    assert row['variants']['MEAN']['daily_reference']==pytest.approx(4/31)
    assert row['variants']['MEAN']['target_stock']==pytest.approx(4/31*95)
    assert row['variants']['MEAN']['quantity']==13
    assert row['consumption_method']=='NET_PERIOD_V2'


def test_new_saved_result_api_and_excel_expose_accounting_balance(monkeypatch):
    import io
    from openpyxl import load_workbook
    import app.replenishment as module
    from test_replenishment import login
    raw=snapshot();raw['sales']=[event('2026-08-02',sold=23),event('2026-08-10',returned=19)]
    monkeypatch.setattr(module,'read_replenishment_source',lambda *a:raw)
    client=login();base='/api/v1/store/replenishment/simulations'
    response=client.post(base,json={'filters':{'date_from':raw['start'],'date_to':raw['end'],'delegations':['02']},'all_consumption_bases':True,
        'temporary_parameters':{'simple_formula':True,'use_safety_stock':False,'multiple_mode':'NONE'}})
    assert response.status_code==201,response.text
    path=base+'/'+response.json()['id']
    for basis in ('MEAN','MEDIAN','MODE'):
        row=client.get(path+'/results',params={'consumption_basis':basis}).json()['items'][0]
        assert row['total_demand']==4 and row['daily_mean']==pytest.approx(4/31)
        detail=client.get(path+'/results/'+str(row['id']),params={'consumption_basis':basis}).json()
        assert detail['consumption_method']=='NET_PERIOD_V2'
        assert sum(d['demand'] for d in detail['daily_sales'])==4
        assert detail['gross_sales']-detail['returns']==4
    sheet=load_workbook(io.BytesIO(client.get(path+'/export.xlsx').content)).active
    headers=[c.value for c in sheet[1]];values=[c.value for c in sheet[2]]
    for label,expected in [('Ventas del periodo',23),('Devoluciones del periodo',19),('Neto del periodo',4),('Días analizados',31),('Método de consumo','NET_PERIOD_V2')]:
        assert values[headers.index(label)]==expected
