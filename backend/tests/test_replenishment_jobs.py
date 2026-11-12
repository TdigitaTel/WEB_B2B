"""Queue publication, bounded memory batches, crash recovery and parity with the pure engine."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from app.bootstrap import main as bootstrap
from app.main import app
from app.db import SessionLocal
from app.models import ReplenishmentJob as Job, ReplenishmentBatch as Batch, ReplenishmentScenario as Scenario, ReplenishmentResult as Result
from app import replenishment_worker as worker
from app.replenishment_engine import prepare_context, calculate_article, annotate_central

bootstrap()

PREFIX='/api/v1/store/replenishment'

@pytest.fixture
def client():
    client=TestClient(app)
    assert client.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'}).status_code==200
    yield client
    with SessionLocal() as db:
        jobs=db.scalars(select(Job)).all();scenarios=[row.scenario_id for row in jobs if row.scenario_id]
        db.execute(delete(Batch));db.execute(delete(Result).where(Result.scenario_id.in_(scenarios)))
        db.execute(delete(Job));db.execute(delete(Scenario).where(Scenario.id.in_(scenarios)));db.commit()


def source(codes):
    return {'captured_at':'2026-04-02T12:00:00+00:00','sales_delegations':['00','01','02','04','05'],
        'company':1,'start':'2026-04-01','end':'2026-04-02',
        'articles':[{'sku':sku,'description':'Material '+sku,'unit_type':'ROL','created_at':'2020-01-01'} for sku in codes],
        'sales':[{'sku':sku,'delegation':delegation,'day':'2026-04-01','sold':1,'returned':0} for sku in codes for delegation in ('00','01','02','04','05')],
        'stocks':[{'sku':sku,'delegation':delegation,'stock':50 if delegation=='00' else 0,'incoming':0,'outgoing':0} for sku in codes for delegation in ('00','01','02','04','05')]}


def request():
    return {'filters':{'date_from':'2026-04-01','date_to':'2026-04-02','delegations':['01','02','04','05']},
            'temporary_parameters':{'simple_formula':True,'review_days':7,'maximum_days':30,'multiple_mode':'NONE'}}


def setup_source(monkeypatch,codes,callback=None):
    calls=[]
    monkeypatch.setattr(worker,'list_replenishment_codes',lambda selected,limit,excluded_codes=None:list(codes))
    def read(start,end,selected,limit):
        assert len(selected)<=1000 and limit==1000
        if callback:callback(selected)
        calls.append(list(selected))
        return source(selected)
    monkeypatch.setattr(worker,'read_replenishment_source',read)
    return calls


def test_batches_are_committed_and_hidden_until_full_publication(client,monkeypatch):
    codes=[f'JOB-{i:05}' for i in range(2005)];observed=[]
    def inspect(selected):
        with SessionLocal() as db:
            job=db.scalar(select(Job));scenario=db.get(Scenario,job.scenario_id)
            count=db.scalar(select(func.count()).select_from(Result).where(Result.scenario_id==scenario.id))
            observed.append((job.processed_articles,count))
            assert client.get(f'{PREFIX}/simulations/{scenario.public_id}/results').status_code==409
            assert client.get(f'{PREFIX}/simulations/{scenario.public_id}/export.xlsx').status_code==409
            progress=client.get(f'{PREFIX}/jobs/{job.public_id}').json()
            assert progress['progress']<100 and progress['result'] is None
    calls=setup_source(monkeypatch,codes,inspect)
    queued=client.post(PREFIX+'/jobs',json=request())
    assert queued.status_code==202 and not calls  # request itself never queries EXIT
    jid=queued.json()['id']
    duplicate=client.post(PREFIX+'/jobs',json=request())
    assert duplicate.json()['id']==jid
    assert worker.process_one()
    assert [len(batch) for batch in calls]==[1000,1000,5]
    assert observed==[(0,0),(1000,4000),(2000,8000)]
    status=client.get(PREFIX+'/jobs/'+jid).json()
    assert status['status']=='COMPLETED' and status['progress']==100
    assert status['processed_articles']==2005 and status['completed_batches']==3
    assert status['result']['source_articles']==2005
    sid=status['result']['id']
    response=client.get(f'{PREFIX}/simulations/{sid}/results')
    assert response.status_code==200 and response.json()['total']==8020
    assert response.json()['summary']['articles_analyzed']==2005
    row=response.json()['items'][0]
    detail=client.get(f"{PREFIX}/simulations/{sid}/results/{row['id']}")
    assert detail.status_code==200 and len(detail.json()['daily_sales'])==2
    evidence=detail.json()
    assert evidence['daily_median'] is not None
    assert len(evidence['weekly_sales'])>=1
    assert sum(w['sold'] for w in evidence['weekly_sales'])==evidence['gross_sales']
    assert 'daily_modes' in evidence
    assert evidence['daily_median_frequency']==len(evidence['daily_median_dates'])
    assert 'daily_mode_occurrences' in evidence
    assert evidence['positive_consumption_days']==sum(d['demand']>0 for d in evidence['daily_sales'])
    assert client.get(f'{PREFIX}/simulations/{sid}/export.xlsx?q=JOB-00000').status_code==200
    # A SKU's complete set of delegations must yield exactly the same quantities/coverage as one-shot calculation.
    raw=source([row['sku']]);params=request()['temporary_parameters'];context=prepare_context(raw,['01','02','04','05'],[],params)
    expected=[calculate_article(raw['articles'][0],d,context) for d in ('01','02','04','05')];annotate_central(expected,raw)
    assert row['final_quantity']==expected[0]['final_quantity']
    assert row['central_total_requested']==expected[0]['central_total_requested']
    assert row['central_can_supply']==expected[0]['central_can_supply']
    current=client.get(PREFIX+'/jobs/current').json()
    assert current['latest_result']['id']==sid


def test_restart_resumes_only_uncommitted_batches(client,monkeypatch):
    codes=[f'RESUME-{i:05}' for i in range(1003)];calls=setup_source(monkeypatch,codes)
    jid=client.post(PREFIX+'/jobs',json=request()).json()['id']
    original=worker.process_batch
    def interrupt(*args):
        if original(*args):raise KeyboardInterrupt('simulated process death after a committed block')
    monkeypatch.setattr(worker,'process_batch',interrupt)
    with pytest.raises(KeyboardInterrupt):worker.process_one()
    status=client.get(PREFIX+'/jobs/'+jid).json()
    assert status['status']=='RUNNING' and status['processed_articles']==1000 and status['result'] is None
    monkeypatch.setattr(worker,'process_batch',original)
    assert worker.process_one()
    assert [len(batch) for batch in calls]==[1000,3]
    status=client.get(PREFIX+'/jobs/'+jid).json()
    assert status['status']=='COMPLETED' and status['processed_articles']==1003
    with SessionLocal() as db:
        job=db.scalar(select(Job).where(Job.public_id==jid))
        assert db.scalar(select(func.count()).select_from(Result).where(Result.scenario_id==job.scenario_id))==4012


def test_failed_block_never_replaces_previous_result(client,monkeypatch):
    setup_source(monkeypatch,['PREVIOUS'])
    previous_id=client.post(PREFIX+'/jobs',json=request()).json()['id'];worker.process_one()
    previous=client.get(PREFIX+'/jobs/'+previous_id).json()['result']
    def fail_after_one(codes):
        if codes[0]=='FAIL-01000':raise RuntimeError('private SQL details must not appear in API')
    setup_source(monkeypatch,[f'FAIL-{i:05}' for i in range(1002)],fail_after_one)
    jid=client.post(PREFIX+'/jobs',json=request()).json()['id'];worker.process_one()
    status=client.get(PREFIX+'/jobs/'+jid).json()
    assert status['status']=='FAILED' and status['processed_articles']==1000 and status['result'] is None
    assert 'private SQL' not in status['error']
    current=client.get(PREFIX+'/jobs/current').json()
    assert current['latest_result']['id']==previous['id']
    assert client.get(f"{PREFIX}/simulations/{previous['id']}/results").status_code==200


def test_selection_limit_and_invalid_parameters_fail_without_partial_publication(client,monkeypatch):
    body=request();body['temporary_parameters']['review_days']=0
    assert client.post(PREFIX+'/jobs',json=body).status_code==422
    def over_limit(selected,limit,excluded_codes=None):raise ValueError('La selección supera el límite configurado')
    monkeypatch.setattr(worker,'list_replenishment_codes',over_limit)
    jid=client.post(PREFIX+'/jobs',json=request()).json()['id'];worker.process_one()
    status=client.get(PREFIX+'/jobs/'+jid).json()
    assert status['status']=='FAILED' and 'límite' in status['error']
    assert status['progress']==0 and status['result'] is None
    customer=TestClient(app)
    assert customer.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'}).status_code==200
    assert customer.get(PREFIX+'/jobs/'+jid).status_code==403


def test_empty_selection_finishes_with_empty_result(client,monkeypatch):
    setup_source(monkeypatch,[])
    jid=client.post(PREFIX+'/jobs',json=request()).json()['id'];worker.process_one()
    status=client.get(PREFIX+'/jobs/'+jid).json()
    assert status['status']=='COMPLETED' and status['progress']==100 and status['total_articles']==0
    assert client.get(f"{PREFIX}/simulations/{status['result']['id']}/results").json()['total']==0


def test_repeated_process_death_stops_instead_of_retrying_forever(client,monkeypatch):
    calls=setup_source(monkeypatch,['INTERRUPTED'])
    def killed(*args):
        calls.append('interrupted')
        raise KeyboardInterrupt('simulated OOM/container restart')
    monkeypatch.setattr(worker,'read_replenishment_source',killed)
    jid=client.post(PREFIX+'/jobs',json=request()).json()['id']
    for _ in range(3):
        with pytest.raises(KeyboardInterrupt):worker.process_one()
    assert worker.process_one()
    status=client.get(PREFIX+'/jobs/'+jid).json()
    assert status['status']=='FAILED' and status['progress']==0
    assert len(calls)==3 and 'tres veces' in status['error']


def test_configured_limit_is_frozen_when_job_is_enqueued(client,monkeypatch):
    client.put(PREFIX+'/settings',json={'article_limit':30000})
    try:
        jid=client.post(PREFIX+'/jobs',json=request()).json()['id']
        client.put(PREFIX+'/settings',json={'article_limit':10000})
        seen=[]
        def listing(selected,limit,excluded_codes=None):seen.append(limit);return []
        monkeypatch.setattr(worker,'list_replenishment_codes',listing)
        worker.process_one()
        assert seen==[30000]
        assert client.get(PREFIX+'/jobs/'+jid).json()['result']['article_limit']==30000
    finally:client.put(PREFIX+'/settings',json={'article_limit':20000})


def test_job_status_is_scoped_to_its_owner(client):
    from app.auth import hash_password
    from app.models import User
    other=TestClient(app)
    with SessionLocal() as db:
        account=User(email='job-owner-test',full_name='Otro operador',role='OPERADOR_TIENDA',password_hash=hash_password('jobs-test123'),active=True)
        db.add(account);db.commit();uid=account.id
    try:
        assert other.post('/api/v1/auth/login',json={'email':'job-owner-test','password':'jobs-test123'}).status_code==200
        jid=client.post(PREFIX+'/jobs',json=request()).json()['id']
        assert other.get(PREFIX+'/jobs/'+jid).status_code==404
        assert other.get(PREFIX+'/jobs/current').json()=={'job':None,'latest_result':None}
    finally:
        from app.models import AuthSession
        with SessionLocal() as db:
            db.execute(delete(AuthSession).where(AuthSession.user_id==uid));db.execute(delete(User).where(User.id==uid));db.commit()


def test_article_enumeration_is_bounded_parameterized_and_has_no_sales_reads(monkeypatch):
    from contextlib import contextmanager
    from app import replenishment_source as source_module
    calls=[]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params):calls.append((sql,params))
        def fetchall(self):return [{'codigoarticulo':'00-B'},{'codigoarticulo':'00-A'}]
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def cursor(self):return Cursor()
    monkeypatch.setattr(source_module,'connect_sqlserver',lambda:Connection())
    assert source_module.list_replenishment_codes(["A'"],20000)==['00-A','00-B']
    assert calls[0][1]==("A'",) and "A'" not in calls[0][0]
    assert 'TOP 20001' in calls[0][0] and 'Albaran' not in calls[0][0] and 'Stock' not in calls[0][0]
    with pytest.raises(ValueError):source_module.list_replenishment_codes(None,1)


def test_sequential_delegations_complete_all_batches_before_next_and_joint_coverage(client,monkeypatch):
    codes=[f'SEQ-{i:04}' for i in range(1001)]
    setup_source(monkeypatch,codes)
    order=[];original=worker.calculate_article
    def capture(article,delegation,context):
        order.append(delegation);return original(article,delegation,context)
    monkeypatch.setattr(worker,'calculate_article',capture)
    body=request();body['filters']['delegations']=['01','02'];body['sequential_delegations']=True
    queued=client.post(PREFIX+'/jobs',json=body)
    assert queued.status_code==202,queued.text
    assert worker.process_one()
    status=client.get(PREFIX+'/jobs/'+queued.json()['id']).json()
    assert status['status']=='COMPLETED',status
    assert order==['01']*1001+['02']*1001
    assert status['total_batches']==status['completed_batches']==4
    assert status['total_articles']==status['processed_articles']==2002
    assert status['result']['source_articles']==1001
    assert status['result']['summary']['articles_analyzed']==1001
    path=PREFIX+'/simulations/'+status['result']['id']
    rows=client.get(path+'/results',params={'q':codes[0]}).json()['items']
    assert len(rows)==2
    with SessionLocal() as db:
        all_rows=list(db.scalars(select(Result).where(Result.scenario_id==db.scalar(select(Scenario.id).where(Scenario.public_id==status['result']['id'])))))
        assert status['result']['summary']['alerts']==sum(len(row.payload['recommendations']) for row in all_rows)
    assert rows[0]['central_total_requested']==pytest.approx(sum(row['final_quantity'] for row in rows))
    assert client.get(path+'/results/'+str(rows[0]['id'])).status_code==200


def test_all_three_saved_bases_filter_delegation_summaries_sort_detail_and_excel(client,monkeypatch):
    from datetime import date,timedelta
    import io
    from openpyxl import load_workbook
    from app import replenishment_saved
    setup_source(monkeypatch,['A','B'])
    def read(*args):
        raw=source(['A','B']);raw['end']='2026-04-30'
        raw['sales']=[{'sku':sku,'delegation':delegation,'day':(date(2026,4,1)+timedelta(days=i)).isoformat(),'sold':value,'returned':0}
            for sku,values in [('A',[1]*11+[2]*10+[20]*9),('B',[3]*30)]
            for delegation in ('00','01','02','04','05') for i,value in enumerate(values)]
        for stock in raw['stocks']:
            if stock['delegation']!='00':stock['stock']=21
        return raw
    monkeypatch.setattr(worker,'read_replenishment_source',read)
    body=request();body.update(all_consumption_bases=True,sequential_delegations=True)
    body['filters']['date_to']='2026-04-30';body['temporary_parameters']['use_safety_stock']=False
    queued=client.post(PREFIX+'/jobs',json=body).json();assert worker.process_one()
    status=client.get(PREFIX+'/jobs/'+queued['id']).json();assert status['status']=='COMPLETED',status
    assert status['result']['consumption_bases']==['MEAN','MEDIAN','MODE']
    path=PREFIX+'/simulations/'+status['result']['id']
    def forbidden(*args,**kwargs):raise AssertionError('Filtering must read stored calculations only')
    monkeypatch.setattr(worker,'read_replenishment_source',forbidden)
    monkeypatch.setattr(replenishment_saved,'rebased_planning_rows',forbidden)
    for basis,quantity,count,first in [('MEAN',36,2,'A'),('MEDIAN',0,1,'B'),('MODE',0,1,'B')]:
        params={'consumption_basis':basis,'delegation':'02','sort':'quantity','descending':True}
        response=client.get(path+'/results',params=params);assert response.status_code==200,response.text
        data=response.json();assert data['total']==2
        assert data['summary']['to_replenish']==count
        assert data['items'][0]['sku']==first
        assert all(row['delegation']=='02' and row['consumption_basis']==basis for row in data['items'])
        a=next(row for row in data['items'] if row['sku']=='A')
        assert a['final_quantity']==quantity
        assert 'consumption_variants' not in a
        prepared=client.get(path+'/results',params={**params,'needed_only':True}).json()
        assert prepared['total']==count and prepared['summary']['to_replenish']==count
        detail=client.get(path+'/results/'+str(a['id']),params={'consumption_basis':basis})
        assert detail.status_code==200,detail.text
        assert detail.json()['daily_reference']==a['daily_reference']
        assert detail.json()['parameters']['consumption_basis']==basis
        exported=client.get(path+'/export.xlsx',params={**params,'mode':'expanded'})
        assert exported.status_code==200,exported.text
        cells=list(load_workbook(io.BytesIO(exported.content)).active.values);headers=cells[0]
        assert len(cells)==3 and all(row[headers.index('Delegación')]=='02' for row in cells[1:])
        assert {row[headers.index('Criterio de consumo')] for row in cells[1:]}=={dict(MEAN='Media',MEDIAN='Mediana',MODE='Moda')[basis]}
        assert client.post(PREFIX+'/redistribution',json={'consumption_basis':basis}).status_code==200
    assert client.get(path+'/results',params={'consumption_basis':'INVALID'}).status_code==422
    # Manual updates retain the other saved views and update joint central coverage.
    row=client.get(path+'/results',params={'delegation':'02','q':'A'}).json()['items'][0]
    changed=client.post(path+'/results/'+str(row['id'])+'/adjustments',json={'quantity':5,'reason':'Cantidad revisada','expected_version':1})
    assert changed.status_code==200,changed.text
    for basis in ['MEAN','MEDIAN','MODE']:
        revised=client.get(path+'/results',params={'delegation':'02','q':'A','consumption_basis':basis}).json()['items'][0]
        assert revised['final_quantity']==5


def test_sequential_variant_joint_coverage_persists_when_mean_is_unchanged(client,monkeypatch):
    from datetime import date,timedelta
    setup_source(monkeypatch,['SPARSE'])
    def read(*args):
        raw=source(['SPARSE']);raw['end']='2026-04-30'
        raw['sales']=[{'sku':'SPARSE','delegation':delegation,'day':(date(2026,4,1)+timedelta(days=i)).isoformat(),'sold':30,'returned':0}
            for delegation in ('00','01','02','04','05') for i in range(7)]
        for stock in raw['stocks']:stock['stock']=1000 if stock['delegation']=='00' else 60
        return raw
    monkeypatch.setattr(worker,'read_replenishment_source',read)
    body=request();body.update(all_consumption_bases=True,sequential_delegations=True)
    body['filters']['date_to']='2026-04-30';body['temporary_parameters']['use_safety_stock']=False
    queued=client.post(PREFIX+'/jobs',json=body).json();assert worker.process_one()
    status=client.get(PREFIX+'/jobs/'+queued['id']).json();assert status['status']=='COMPLETED',status
    path=PREFIX+'/simulations/'+status['result']['id']+'/results'
    mean=client.get(path,params={'consumption_basis':'MEAN'}).json()['items']
    assert all(row['final_quantity']==0 for row in mean)
    for basis in ['MEDIAN','MODE']:
        rows=client.get(path,params={'consumption_basis':basis}).json()['items']
        assert len(rows)==4
        assert all(row['final_quantity']==180 for row in rows)
        assert all(row['central_total_requested']==720 for row in rows)
