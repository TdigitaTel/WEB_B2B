from copy import deepcopy
from io import BytesIO
import pytest
from openpyxl import load_workbook
from sqlalchemy import select, update
from app.db import SessionLocal
from app.models import ReplenishmentResult as Result
from app.replenishment_alerts import stock_alert_code
from test_replenishment_saved import client, clean_calculations, setup_source, request, PREFIX
from app import replenishment_worker as worker


def base(**patch):
    return {'delegation':'02','stock':0,'final_quantity':10,'quantity_without_multiple':10,'central_available':0,
        'central_stock':0,'central_incoming':500,'central_covers_without_multiple':False,**patch}

@pytest.mark.parametrize('patch,expected',[
    ({},'NO_STOCK'),({'central_stock':100},'NO_STOCK'), # Own reserve/commitments can consume physical stock.
    ({'quantity_without_multiple':0},'NONE'),({'manually_excluded':True},'NONE'),
    ({'central_available':5},'INSUFFICIENT'),({'central_available':20},'INSUFFICIENT'), # Joint demand is not covered.
    ({'central_available':20,'central_covers_without_multiple':True},'NONE'),
    ({'central_available':None,'central_stock':None},'UNKNOWN'),({'central_available':None,'central_stock':0},'NO_STOCK'),
    ({'delegation':'00','stock':5},'NONE'),({'delegation':'00','stock':0},'NO_STOCK'),
    ({'delegation':'00','stock':None},'UNKNOWN')])
def test_alarm_classification_and_no_false_zero_stock(patch,expected):
    assert stock_alert_code(base(**patch))==expected


def test_saved_alarms_filter_counters_excel_and_legacy_projection_without_exit(client,monkeypatch):
    codes=['ZERO','PARTIAL','COVERED','NO-NEED','UNKNOWN','RESERVED']
    setup_source(monkeypatch,codes);body=request();body['all_consumption_bases']=True
    queued=client.post(PREFIX+'/jobs',json=body).json();assert worker.process_one()
    sid=client.get(PREFIX+'/jobs/'+queued['id']).json()['result']['id']
    with SessionLocal() as db:
        for stored in db.scalars(select(Result)):
            row=deepcopy(stored.payload)
            for variant in [row,*row.get('consumption_variants',{}).values()]:
                available={'ZERO':0,'PARTIAL':5,'COVERED':50,'NO-NEED':0,'UNKNOWN':None,'RESERVED':0}[stored.sku]
                need=0 if stored.sku=='NO-NEED' else 10
                variant.update(final_quantity=need,quantity_without_multiple=need,quantity_before_rounding=need,
                    recommended_quantity=need,comparison_eligible=True,central_available=available,
                    central_stock=None if stored.sku=='UNKNOWN' else 50 if stored.sku=='RESERVED' else available,
                    central_incoming=500,central_covers_without_multiple=stored.sku=='COVERED',central_can_supply=stored.sku=='COVERED')
            # The same material can be covered for one criterion and need stock for another.
            if stored.sku=='COVERED':row['consumption_variants']['MEDIAN'].update(central_available=0,central_covers_without_multiple=False,central_can_supply=False)
            stored.payload=row
        db.commit()
        # Simulate an old projection which has not been backfilled. Reads must still work immediately.
        stored=db.scalar(select(Result).where(Result.sku=='ZERO',Result.delegation=='02'))
        legacy=deepcopy(stored.filter_data);legacy.pop('stock_alert_code',None)
        for variant in legacy.get('consumption_variants',{}).values():variant.pop('stock_alert_code',None)
        db.execute(update(Result).where(Result.id==stored.id).values(filter_data=legacy));db.commit()
    monkeypatch.setattr(worker,'read_replenishment_source',lambda *args:pytest.fail('Alarm viewing must not read EXIT'))
    path=PREFIX+'/simulations/'+sid
    query={'delegation':'02','consumption_basis':'MEAN'}
    data=client.get(path+'/results',params=query).json()
    assert data['summary']['central_no_stock']==2 and data['summary']['central_insufficient']==1, {'summary':data['summary'],'rows':[(r['sku'],r['stock_alert']) for r in data['items']]}
    assert data['summary']['central_attention']==3 and data['summary']['central_unknown']==1
    assert {row['sku']:row['stock_alert']['code'] for row in data['items']}=={'ZERO':'NO_STOCK','RESERVED':'NO_STOCK','PARTIAL':'INSUFFICIENT','COVERED':'NONE','NO-NEED':'NONE','UNKNOWN':'UNKNOWN'}
    filtered=client.get(path+'/results',params={**query,'stock_alert':'NO_STOCK','page_size':1}).json()
    assert filtered['total']==2 and len(filtered['items'])==1
    filtered=client.get(path+'/results',params={**query,'stock_alert':'ATTENTION'}).json()
    assert filtered['total']==3 and 'UNKNOWN' not in {row['sku'] for row in filtered['items']}
    median=client.get(path+'/results',params={**query,'consumption_basis':'MEDIAN','stock_alert':'NO_STOCK'}).json()
    assert median['total']==3
    assert client.get(path+'/results',params={**query,'stock_alert':'UNKNOWN'}).json()['total']==1
    assert client.get(path+'/results',params={**query,'stock_alert':'BAD'}).status_code==422
    response=client.get(path+'/export.xlsx',params={**query,'stock_alert':'NO_STOCK'})
    assert response.status_code==200
    sheet=load_workbook(BytesIO(response.content)).active;headers=[c.value for c in sheet[1]]
    assert sheet.max_row==3
    column=headers.index('Alerta de reposición / Almeiras')+1
    assert all('Almeiras sin disponible' in sheet.cell(index,column).value for index in range(2,4))
    saved=client.get(PREFIX+'/calculations').json()['items']
    assert next(row for row in saved if row['delegation']=='02')['summary']['central_attention']==3

    # Coverage selector uses the same saved data for the table, totals and export.
    expected={'ALL':set(codes),'COVERED':{'COVERED'},'UNCOVERED':{'ZERO','PARTIAL','RESERVED'},'UNKNOWN':{'UNKNOWN'}}
    for coverage,skus in expected.items():
        params={**query,'needed_only':True,'central_coverage':coverage}
        result=client.get(path+'/results',params=params).json()
        assert {item['sku'] for item in result['items']}==skus-{'NO-NEED'}
        assert result['total']==len(skus-{'NO-NEED'})
    assert client.get(path+'/results',params={**query,'consumption_basis':'MEDIAN','central_coverage':'COVERED'}).json()['total']==0
    page=client.get(path+'/results',params={**query,'central_coverage':'UNCOVERED','page_size':1}).json()
    assert page['total']==3 and len(page['items'])==1
    assert client.get(path+'/results',params={**query,'delegation':'00','central_coverage':'COVERED'}).json()['total']==0
    assert client.get(path+'/results',params={**query,'central_coverage':'BAD'}).status_code==422
    exported=client.get(path+'/export.xlsx',params={**query,'central_coverage':'COVERED'})
    assert load_workbook(BytesIO(exported.content)).active.max_row==2
