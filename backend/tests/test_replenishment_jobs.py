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
