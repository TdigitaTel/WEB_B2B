from copy import deepcopy
from datetime import date
from io import BytesIO
from math import sqrt
from statistics import NormalDist
import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import delete, func, select
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.main import app
from app.procurement_models import ProcurementJob as Job, ProcurementBatch as Batch, ProcurementResult as Result
from app import procurement as module
from app.procurement_engine import calculate
from app.replenishment_engine import Parameters, demand_statistics
from app.models import ReplenishmentDelegationCalculation as Current

bootstrap()
BASE='/api/v1/store/replenishment/procurement'
D=['00','01','02','04','05']


def source(codes=['03283']):
    return {'captured_at':'2026-11-18T10:00:00+00:00','start':'2026-04-01','end':'2026-04-30',
        'articles':[{'sku':sku,'description':'Material '+sku,'unit_type':'UD','created_at':'2020-01-01','exit_multiple':12,
            'procurement_coverage_days':90,'procurement_lead_days':5,'brand_code':'42','brand_name':'Marca de prueba'} for sku in codes],
        'sales':[{'sku':sku,'delegation':d,'day':f'2026-04-{day:02}','sold':2,'returned':0} for sku in codes for d in D for day in range(1,31)],
        'stocks':[{'sku':sku,'delegation':d,'stock':20,'incoming':2,'outgoing':1} for sku in codes for d in D]}


def request():
    return {'filters':{'date_from':'2026-04-01','date_to':'2026-04-30','delegations':D},'use_safety_stock':False}


def test_network_purchase_counts_stock_once_and_uses_material_terms():
    row=calculate(source(),False)[0]
    assert row['monthly_mean']==300 and row['coverage_days']==90 and row['lead_days']==5
    assert row['stock']==100 and row['central_stock']==20 and row['inventory_position']==105
    assert row['variants']['MEAN']['daily_reference']==10
    assert row['variants']['MEAN']['target_stock']==950
    assert row['variants']['MEAN']['quantity']==845
    assert row['variants']['MEAN']['quantity_with_multiple']==852
    assert row['variants']['MEDIAN']['quantity']==845
    assert row['variants']['MODE']['quantity']==845
    # An internal transfer contributes -8 and +8 to position and cannot trigger a purchase by itself.
    raw=source();raw['stocks'][0]['outgoing']+=8;raw['stocks'][1]['incoming']+=8
    assert calculate(raw,False)[0]['variants']['MEAN']['quantity']==845


def test_safety_protects_entire_period_from_actual_network_daily_variation():
    raw=source();raw['sales'][0]['sold']=52
    row=calculate(raw,True)[0]
    expected=NormalDist().inv_cdf(.95)*row['daily_std']*sqrt(95)
    assert row['variants']['MEAN']['safety_stock']==pytest.approx(expected)
    assert calculate(raw,False)[0]['variants']['MEAN']['safety_stock']==0


@pytest.mark.parametrize('field,value',[('procurement_coverage_days',None),('procurement_coverage_days',0),('procurement_lead_days',-1),('procurement_lead_days',float('nan'))])
def test_missing_or_invalid_erp_terms_require_review_not_zero_purchase(field,value):
    raw=source();raw['articles'][0][field]=value
    row=calculate(raw)[0]
    assert row['variants']['MEAN']['status']=='REVIEW'
    assert row['variants']['MEAN']['quantity'] is None
    assert row['notes']


def test_missing_branch_zero_consumption_unavailable_mode_and_flags():
    raw=source();raw['stocks'].pop()
    assert calculate(raw)[0]['variants']['MEAN']['quantity'] is None
    raw=source();raw['sales']=[]
    assert calculate(raw)[0]['variants']['MEAN']['quantity']==0
    raw=source();raw['sales']=[{'sku':'03283','delegation':'00','day':'2026-04-01','sold':30,'returned':0}]
    row=calculate(raw,False)[0]
    assert row['variants']['MODE']['quantity'] is None
    assert row['exceptionality']['level']=='HIGH'
    assert any('un solo día' in note for note in row['notes'])
    # Informative exceptionality must not silently exclude demand from the base calculation.
    assert row['variants']['MEAN']['target_stock']==95


def test_returns_are_netted_within_branch_day_before_network_aggregation():
    raw=source();raw['sales']=[{'sku':'03283','delegation':'00','day':'2026-04-01','sold':5,'returned':20},
        {'sku':'03283','delegation':'01','day':'2026-04-01','sold':10,'returned':0}]
    assert calculate(raw,False)[0]['total_demand']==10


@pytest.fixture
def client():
    client=TestClient(app);assert client.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'}).status_code==200
    yield client
    with SessionLocal() as db:
        db.execute(delete(Result));db.execute(delete(Batch));db.execute(delete(Job));db.commit()


def setup_source(monkeypatch,codes):
    calls=[]
    monkeypatch.setattr(module,'list_replenishment_codes',lambda *args:list(codes))
    def read(start,end,selected,limit):
        assert len(selected)<=1000 and limit==1000
        calls.append(list(selected));return source(selected)
    monkeypatch.setattr(module,'read_replenishment_source',read)
    monkeypatch.setattr(module,'read_procurement_terms',lambda codes:{a['sku']:{key:a[key] for key in ('procurement_coverage_days','procurement_lead_days','brand_code','brand_name')} for a in source(codes)['articles']})
    return calls


def test_queue_publication_pagination_filters_export_and_no_replenishment_replacement(client,monkeypatch):
    codes=[f'BUY-{i:04}' for i in range(1003)];calls=setup_source(monkeypatch,codes)
    with SessionLocal() as db:before=list(db.execute(select(Current.delegation,Current.scenario_id)).all())
    queued=client.post(BASE+'/jobs',json=request());assert queued.status_code==202 and not calls
    jid=queued.json()['id'];assert client.post(BASE+'/jobs',json=request()).json()['id']==jid
    assert client.get(BASE+f'/jobs/{jid}/results').status_code==409
    assert client.get(BASE+f'/jobs/{jid}/export.xlsx').status_code==409
    assert module.process_one()
    status=client.get(BASE+f'/jobs/{jid}').json()
    assert status['status']=='COMPLETED' and status['progress']==100 and status['processed_articles']==1003
    assert [len(c) for c in calls]==[1000,3] and status['summary']['MEAN']['buy']==1003
    monkeypatch.setattr(module,'read_replenishment_source',lambda *args:pytest.fail('Viewing a saved purchase must not read EXIT'))
    result=client.get(BASE+f'/jobs/{jid}/results?page=2').json();assert result['total']==1003 and len(result['items'])==50
    assert result['items'][0]['sku']=='BUY-0050'
    filtered=client.get(BASE+f'/jobs/{jid}/results?q=BUY-0001&brand=42&only_buy=true').json()
    assert filtered['total']==1 and filtered['items'][0]['proposal']['quantity']==845
    assert client.get(BASE+f'/jobs/{jid}/results?brand=missing').json()['total']==0
    assert client.get(BASE+f'/jobs/{jid}/results?basis=BAD').status_code==422
    exported=client.get(BASE+f'/jobs/{jid}/export.xlsx?q=BUY-0001&brand=42')
    assert exported.status_code==200
    sheet=load_workbook(BytesIO(exported.content)).active
    assert sheet.max_row==8 and sheet.cell(8,1).value=='BUY-0001' and sheet.cell(8,20).value==845
    with SessionLocal() as db:assert list(db.execute(select(Current.delegation,Current.scenario_id)).all())==before
    assert client.get(BASE+'/jobs/current').json()['latest_result']['id']==jid


def test_resume_committed_blocks_and_keep_previous_after_failure(client,monkeypatch):
    setup_source(monkeypatch,['GOOD']);jid=client.post(BASE+'/jobs',json=request()).json()['id'];module.process_one()
    calls=setup_source(monkeypatch,[f'RESUME-{i:04}' for i in range(1001)])
    original=module.calculate
    def interrupt(raw,*args):
        if raw['articles'][0]['sku']=='RESUME-1000':raise KeyboardInterrupt()
        return original(raw,*args)
    monkeypatch.setattr(module,'calculate',interrupt)
    running=client.post(BASE+'/jobs',json=request()).json()['id']
    with pytest.raises(KeyboardInterrupt):module.process_one()
    assert client.get(BASE+f'/jobs/{running}').json()['processed_articles']==1000
    monkeypatch.setattr(module,'calculate',original);assert module.process_one()
    assert [len(c) for c in calls]==[1000,1,1]
    assert client.get(BASE+f'/jobs/{running}').json()['status']=='COMPLETED'
    setup_source(monkeypatch,['FAIL']);monkeypatch.setattr(module,'read_procurement_terms',lambda *args:(_ for _ in ()).throw(ValueError('Falta plazo de entrega')))
    failed=client.post(BASE+'/jobs',json=request()).json()['id'];module.process_one()
    assert client.get(BASE+f'/jobs/{failed}').json()['status']=='FAILED'
    assert client.get(BASE+'/jobs/current').json()['latest_result']['id']==running


def test_brand_selection_category_filters_and_excel_strings(client,monkeypatch):
    setup_source(monkeypatch,['=1+1','OTHER'])
    def metadata(codes):return {sku:{'procurement_coverage_days':90,'procurement_lead_days':5,'brand_code':'42' if sku=='=1+1' else '99','brand_name':'Wanted' if sku=='=1+1' else 'Other'} for sku in codes}
    monkeypatch.setattr(module,'read_procurement_terms',metadata)
    body=request();body['filters']['brand']='Wanted'
    jid=client.post(BASE+'/jobs',json=body).json()['id'];module.process_one()
    data=client.get(BASE+f'/jobs/{jid}/results').json();assert data['total']==1 and data['items'][0]['sku']=='=1+1'
    sheet=load_workbook(BytesIO(client.get(BASE+f'/jobs/{jid}/export.xlsx').content)).active
    assert sheet.cell(8,1).value=='=1+1' and sheet.cell(8,1).data_type=='s'
    assert client.get(BASE+f'/jobs/{jid}/results?family_id=999999').json()['total']==0
    body=request();body['filters']['delegations']=['00'];assert client.post(BASE+'/jobs',json=body).status_code==422


def test_procurement_terms_query_is_company_safe_batched_and_preserves_unmatched_brand(monkeypatch):
    from app import replenishment_source as module
    queries=[]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params):self.params=params;queries.append((sql,params))
        def fetchall(self):return [{'sku':sku,'coverage_days':90,'lead_days':5,'brand_code':None,'brand_name':None} for sku in self.params]
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def cursor(self):return Cursor()
    monkeypatch.setattr(module,'connect_sqlserver',Connection)
    result=module.read_procurement_terms([str(i) for i in range(1001)])
    assert len(queries)==2 and max(len(params) for _,params in queries)==1000
    assert all('LEFT JOIN dbo.Marcas' in sql and 'a.CodigoEmpresa=m.CodigoEmpresa' in sql and 'a.CodigoEmpresa=1' in sql for sql,_ in queries)
    assert result['0']['procurement_coverage_days']==90 and result['0']['brand_name']==''


def test_purchase_proposals_are_private_and_customer_cannot_access(client,monkeypatch):
    setup_source(monkeypatch,['PRIVATE'])
    jid=client.post(BASE+'/jobs',json=request()).json()['id'];module.process_one()
    admin=TestClient(app)
    assert admin.post('/api/v1/auth/login',json={'email':'admin@bermudez.test','password':'123456'}).status_code==200
    assert admin.get(BASE+f'/jobs/{jid}').status_code==404
    assert admin.get(BASE+f'/jobs/{jid}/results').status_code==404
    assert TestClient(app).get(BASE+'/jobs/current').status_code==401
