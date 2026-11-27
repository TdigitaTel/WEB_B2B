import io
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import delete, select
from app.main import app
from app.db import SessionLocal
from app.models import RedistributionJob as Job, RedistributionBatch as Batch, ReplenishmentScenario as Scenario, ReplenishmentResult as Result
from app import redistribution_jobs as queue
from app import replenishment_worker as worker
from test_replenishment_saved import client, clean_calculations, setup_source, request, PREFIX


@pytest.fixture(autouse=True)
def clean_queue():
    def clean():
        with SessionLocal() as db:
            db.execute(delete(Batch));db.execute(delete(Job));db.commit()
    clean();yield;clean()


def publish(client,monkeypatch,codes):
    setup_source(monkeypatch,codes)
    response=client.post(PREFIX+'/jobs',json=request());assert response.status_code in (200,202),response.text
    assert worker.process_one()
    return client.get(PREFIX+'/jobs/'+response.json()['id']).json()['result']['id']


def create(client,**body):
    response=client.post(PREFIX+'/redistribution/jobs',json=body)
    assert response.status_code==202,response.text
    return response.json()


def test_queue_batches_progress_resume_and_export_without_recalculation(client,monkeypatch):
    codes=[f'MAT-{i:04d}' for i in range(1001)];publish(client,monkeypatch,codes)
    queued=create(client);path=PREFIX+'/redistribution/jobs/'+queued['id']
    assert queued['batch_size']==1000 and not queued['selection_ready']
    assert queued['status']=='QUEUED' and queued['progress']==0
    assert client.get(path+'/result').status_code==409
    # Reject the old long synchronous call explicitly, instead of letting it time out.
    assert client.post(PREFIX+'/redistribution').status_code==422
    with SessionLocal() as db:
        job=db.scalar(select(Job).where(Job.public_id==queued['id']));job.status='RUNNING';job.worker_token='first';job_id=job.id;db.commit()
    queue.initialize(job_id,'first')
    prepared=client.get(path).json();assert prepared['total_batches']==2 and prepared['total_articles']==1001
    assert queue.process_batch(job_id,'first')
    halfway=client.get(path).json();assert halfway['processed_articles']==1000 and halfway['completed_batches']==1
    assert 0<halfway['progress']<100
    assert client.get(path+'/result').status_code==409
    # Simulate process death after the first committed batch: reclaim and finish only pending work.
    sizes=[];original=queue.calculate_redistribution
    def checked(db,basis='MEAN',codes=None,**kwargs):
        sizes.append(len(codes));assert len(codes)<=1000
        return original(db,basis,codes,**kwargs)
    monkeypatch.setattr(queue,'calculate_redistribution',checked)
    assert worker.process_one()
    assert sizes==[1,0]
    completed=client.get(path).json();assert completed['status']=='COMPLETED' and completed['progress']==100
    assert completed['processed_articles']==1001 and completed['completed_batches']==2
    assert client.get(PREFIX+'/redistribution/jobs/current').json()['job']['id']==queued['id']
    with SessionLocal() as db:
        batches=list(db.scalars(select(Batch).where(Batch.job_id==job_id).order_by(Batch.number)))
        assert [len(batch.codes) for batch in batches]==[1000,1] and all(batch.result is not None for batch in batches)
    data=client.get(path+'/result').json()
    assert len(data['unmet_needs'])==100 and data['summary']['unmet_needs']==4004
    # Export consumes saved batch outputs; no engine/EXIT recalculation is allowed.
    monkeypatch.setattr(queue,'calculate_redistribution',lambda *a:(_ for _ in ()).throw(AssertionError('Do not recalculate Excel')))
    monkeypatch.setattr(worker,'read_replenishment_source',lambda *a:(_ for _ in ()).throw(AssertionError('No EXIT reads')))
    response=client.post(path+'/export.xlsx',json={'fingerprint':completed['result']['fingerprint']})
    assert response.status_code==200,response.text
    book=load_workbook(io.BytesIO(response.content),read_only=True)
    assert sum(1 for _ in book['Necesidades sin cubrir'].rows)==4005


def test_filters_apply_to_worklist_and_preserve_all_four_material_delegations(client,monkeypatch):
    publish(client,monkeypatch,['MATCH','OTHER'])
    with SessionLocal() as db:
        for row in db.scalars(select(Result)):
            payload=deepcopy(row.payload);payload.update(area_id=11,family_id=21 if row.sku=='MATCH' else 22,subfamily_id=31,type_id=41)
            row.payload=payload
        db.commit()
    job=create(client,filters={'q':'Material MAT','skus':['MATCH','OTHER'],'area_id':11,'family_id':21,'subfamily_id':31,'type_id':41})
    assert worker.process_one()
    assert client.get(PREFIX+'/redistribution/jobs/'+job['id']).json()['total_articles']==1
    path=PREFIX+'/redistribution/jobs/'+job['id'];data=client.get(path+'/result').json()
    assert {row['sku'] for row in data['unmet_needs']}=={'MATCH'}
    assert {row['delegation'] for row in data['unmet_needs']}=={'01','02','04','05'}
    assert data['filters']['family_id']==21
    empty=create(client,filters={'q':'NOT-FOUND'})
    assert empty['total_articles']==0 and worker.process_one()
    result=client.get(PREFIX+'/redistribution/jobs/'+empty['id']+'/result').json()
    assert not result['movements'] and not result['unmet_needs'] and result['analyzed_materials']==0


def test_source_changes_fail_job_and_invalidate_export_without_partial_publication(client,monkeypatch):
    publish(client,monkeypatch,['ONE']);job=create(client);path=PREFIX+'/redistribution/jobs/'+job['id']
    with SessionLocal() as db:
        scenario=db.scalar(select(Scenario));scenario.version+=1;db.commit()
    assert worker.process_one()
    failed=client.get(path).json()
    assert failed['status']=='FAILED' and 'han cambiado' in failed['error'] and failed['result'] is None
    assert client.get(path+'/result').status_code==409
    good=create(client);assert worker.process_one();goodpath=PREFIX+'/redistribution/jobs/'+good['id']
    result=client.get(goodpath).json()['result']
    with SessionLocal() as db:
        scenario=db.scalar(select(Scenario));scenario.version+=1;db.commit()
    assert client.post(goodpath+'/export.xlsx',json={'fingerprint':result['fingerprint']}).status_code==409


def test_queue_missing_sources_permissions_and_active_deduplication(client,monkeypatch):
    assert client.post(PREFIX+'/redistribution/jobs',json={}).status_code==409
    publish(client,monkeypatch,['ONE'])
    first=create(client);assert create(client)['id']==first['id']
    assert client.post(PREFIX+'/redistribution/jobs',json={'filters':{'q':'OTHER'}}).status_code==409
    customer=TestClient(app)
    assert customer.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'}).status_code==200
    assert customer.get(PREFIX+'/redistribution/jobs/'+first['id']).status_code==403
    assert customer.post(PREFIX+'/redistribution/jobs',json={}).status_code==403


def test_completed_movements_are_paginated_and_export_remains_complete(client,monkeypatch):
    codes=[f'MOVE-{i:04d}' for i in range(120)];publish(client,monkeypatch,codes)
    with SessionLocal() as db:
        for row in db.scalars(select(Result)):
            value=deepcopy(row.payload);value.update(daily_reference=0.5,safety_stock=2.5,maximum_stock=10,stock=100 if row.delegation=='01' else 0 if row.delegation=='02' else 10,
                outgoing=0,incoming=0,inventory_position=100 if row.delegation=='01' else 0 if row.delegation=='02' else 10,
                final_quantity=3 if row.delegation=='02' else 0)
            row.payload=value
        db.commit()
    job=create(client);assert worker.process_one();path=PREFIX+'/redistribution/jobs/'+job['id']
    first=client.get(path+'/result').json();second=client.get(path+'/result?page=2').json();last=client.get(path+'/result?page=3').json()
    assert [len(page['movements']) for page in (first,second,last)]==[100,100,40]
    assert first['movement_total']==240
    assert len({(row['sku'],row['to_delegation']) for page in (first,second,last) for row in page['movements']})==240
    searched=client.get(path+'/result?q=MOVE-0001').json()
    assert searched['movement_total']==2 and {row['sku'] for row in searched['movements']}=={'MOVE-0001'}
    response=client.post(path+'/export.xlsx',json={'fingerprint':first['fingerprint']})
    assert response.status_code==200,response.text
    book=load_workbook(io.BytesIO(response.content),read_only=True)
    assert sum(1 for _ in book['Movimientos'].rows)==241
    admin=TestClient(app);assert admin.post('/api/v1/auth/login',json={'email':'admin@bermudez.test','password':'123456'}).status_code==200
    assert admin.get(path).status_code==404  # Different operator cannot read another operator's queued proposal.


def test_source_changes_after_committed_batch_keep_partial_result_unpublished(client,monkeypatch):
    publish(client,monkeypatch,['ONE']);queued=create(client);path=PREFIX+'/redistribution/jobs/'+queued['id']
    with SessionLocal() as db:
        job=db.scalar(select(Job).where(Job.public_id==queued['id']));job.status='RUNNING';job.worker_token='first';jid=job.id;db.commit()
    queue.initialize(jid,'first');assert queue.process_batch(jid,'first')
    assert client.get(path).json()['completed_batches']==1
    with SessionLocal() as db:
        scenario=db.scalar(select(Scenario));scenario.version+=1;db.commit()
    assert worker.process_one()
    assert client.get(path).json()['status']=='FAILED'
    assert client.get(path+'/result').status_code==409


def test_movement_details_freeze_inputs_and_allocations_without_recalculating(client,monkeypatch):
    publish(client,monkeypatch,['DETAIL'])
    with SessionLocal() as db:
        for row in db.scalars(select(Result)):
            value=deepcopy(row.payload)
            stock=100 if row.delegation=='01' else 0 if row.delegation=='02' else 10
            value.update(daily_reference=0.5,safety_stock=2.5,maximum_stock=10,stock=stock,outgoing=0,incoming=40 if row.delegation=='01' else 0,
                inventory_position=stock+(40 if row.delegation=='01' else 0),final_quantity=3 if row.delegation=='02' else 0,
                effective_multiple=1)
            row.payload=value
        db.commit()
    queued=create(client);assert worker.process_one();path=PREFIX+'/redistribution/jobs/'+queued['id']
    data=client.get(path+'/result').json();transfer,returned=data['movements']
    assert transfer['quantity']==3 and returned['quantity']==87
    assert transfer['detail_id']!=returned['detail_id']
    assert 'calculation_detail' not in transfer  # Keep listing/pagination small.
    with SessionLocal() as db:
        batch=db.scalar(select(Batch).where(Batch.job_id==db.scalar(select(Job.id).where(Job.public_id==queued['id']))))
        assert len(batch.result['movement_details'])==2
    def forbidden(*args,**kwargs):raise AssertionError('Opening a persisted detail must not recalculate or read EXIT')
    monkeypatch.setattr(queue,'calculate_redistribution',forbidden)
    monkeypatch.setattr(worker,'read_replenishment_source',forbidden)
    detail=client.get(path+'/movements/'+transfer['detail_id'])
    assert detail.status_code==200,detail.text
    evidence=detail.json();trace=evidence['detail']
    assert not evidence['reconstructed'] and evidence['fingerprint']==data['fingerprint']
    assert trace['origin']['stock']==100 and trace['origin']['incoming']==40
    assert trace['origin']['source']['version']==1 and trace['origin']['parameters']['simple_formula'] is True
    assert trace['raw_surplus']==trace['initial_surplus']==90  # Future incoming never increases donor surplus.
    assert trace['dispatch_step']==1 and trace['origin_before']==90 and trace['origin_after']==87
    assert trace['destination_initial_need']==3 and trace['destination_before']==3 and trace['destination_after']==0
    assert trace['destination']['delegation']=='02'
    returned_detail=client.get(path+'/movements/'+returned['detail_id']).json()['detail']
    assert returned_detail['origin_before']==87 and returned_detail['already_allocated']==3
    assert returned_detail['destination'] is None
    assert returned_detail['prior_movements'][0]['quantity']==3 and returned_detail['sequence']==2
    assert client.get(path+'/movements/1-999').status_code==404
    assert client.get(path+'/movements/bad-id').status_code==404
    searched=client.get(path+'/result?q=DETAIL&page_size=1&page=2').json()
    assert searched['movements'][0]['detail_id']==returned['detail_id']
    admin=TestClient(app);assert admin.post('/api/v1/auth/login',json={'email':'admin@bermudez.test','password':'123456'}).status_code==200
    assert admin.get(path+'/movements/'+transfer['detail_id']).status_code==404
    with SessionLocal() as db:
        scenario=db.scalar(select(Scenario));scenario.version+=1;db.commit()
    assert client.get(path+'/movements/'+transfer['detail_id']).status_code==409


def test_legacy_movement_details_reconstruct_and_verify_only_the_selected_sku(client,monkeypatch):
    publish(client,monkeypatch,['LEGACY','OTHER'])
    with SessionLocal() as db:
        for row in db.scalars(select(Result)):
            value=deepcopy(row.payload);value.update(daily_reference=0.5,safety_stock=2.5,stock=100,maximum_stock=10,outgoing=0,incoming=0,inventory_position=100,final_quantity=0)
            row.payload=value
        db.commit()
    queued=create(client);assert worker.process_one();path=PREFIX+'/redistribution/jobs/'+queued['id']
    with SessionLocal() as db:
        batch=db.scalar(select(Batch));batch.result={key:value for key,value in batch.result.items() if key!='movement_details'};db.commit()
    move=client.get(path+'/result').json()['movements'][0]
    calls=[];original=queue.calculate_redistribution
    def checked(db,basis,codes,**kwargs):calls.append(codes);return original(db,basis,codes,**kwargs)
    monkeypatch.setattr(queue,'calculate_redistribution',checked)
    monkeypatch.setattr(worker,'read_replenishment_source',lambda *a:pytest.fail('Legacy detail must use the saved calculation'))
    response=client.get(path+'/movements/'+move['detail_id'])
    assert response.status_code==200,response.text
    assert response.json()['reconstructed'] and response.json()['movement']['quantity']==90
    assert calls==[[move['sku']]]
    with SessionLocal() as db:
        batch=db.scalar(select(Batch));value=deepcopy(batch.result);value['movements'][0]['quantity']=999;batch.result=value;db.commit()
    assert client.get(path+'/movements/'+move['detail_id']).status_code==409


def test_reserve_days_default_validation_persistence_and_excel(client,monkeypatch):
    publish(client,monkeypatch,['RESERVE'])
    for days in [0,366,1.5]:
        assert client.post(PREFIX+'/redistribution/jobs',json={'reserve_days':days}).status_code==422
    queued=create(client)
    assert queued['reserve_days']==15
    assert client.post(PREFIX+'/redistribution/jobs',json={'reserve_days':30}).status_code==409
    assert worker.process_one()
    path=PREFIX+'/redistribution/jobs/'+queued['id']
    result=client.get(path+'/result').json()
    assert result['reserve_days']==15
    exported=client.post(path+'/export.xlsx',json={'fingerprint':result['fingerprint']})
    book=load_workbook(io.BytesIO(exported.content))
    summary={row[0]:row[1] for row in book['Resumen'].iter_rows(min_row=2,values_only=True)}
    assert summary['Días de stock conservado']==15
    changed=client.post(PREFIX+'/redistribution/jobs',json={'reserve_days':30})
    assert changed.status_code==202,changed.text
    assert changed.json()['reserve_days']==30
    assert worker.process_one()
    updated=client.get(PREFIX+'/redistribution/jobs/'+changed.json()['id']+'/result').json()
    assert updated['reserve_days']==30 and updated['fingerprint']!=result['fingerprint']
