from decimal import Decimal
import pytest
from sqlalchemy import delete, select
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.models import (ReplenishmentDelegationCalculation as Current,ReplenishmentScenario as Scenario,
    ReplenishmentResult as Result,ReplenishmentJob as Job,ReplenishmentBatch as Batch,ReplenishmentAdjustment as Adjustment)
from app.replenishment_saved import redistribution
from test_replenishment_jobs import client, source, request, setup_source, PREFIX
from app import replenishment_worker as worker
bootstrap()

@pytest.fixture(autouse=True)
def clean_calculations():
    def clean():
        with SessionLocal() as db:
            for model in (Current,Adjustment,Result,Batch,Job,Scenario):db.execute(delete(model))
            db.commit()
    clean();yield;clean()


def test_saved_per_delegation_replaces_only_after_success(client,monkeypatch):
    setup_source(monkeypatch,['SAVED'])
    body=request();jid=client.post(PREFIX+'/jobs',json=body).json()['id'];assert worker.process_one()
    first=client.get(PREFIX+'/jobs/'+jid).json()['result']['id']
    saved=client.get(PREFIX+'/calculations').json()
    assert [r['delegation'] for r in saved['items']]==['01','02','04','05'] and not saved['missing_delegations']
    assert all(r['calculated_at'] and r['summary']['article_delegations']==1 for r in saved['items'])
    body['filters']['delegations']=['02']
    second_id=client.post(PREFIX+'/jobs',json=body).json()['id']
    assert {r['id'] for r in client.get(PREFIX+'/calculations').json()['items']}=={first}
    assert worker.process_one()
    second=client.get(PREFIX+'/jobs/'+second_id).json()['result']['id']
    saved=client.get(PREFIX+'/calculations').json()['items']
    assert next(r for r in saved if r['delegation']=='02')['id']==second
    assert {r['id'] for r in saved if r['delegation']!='02'}=={first}
    assert client.get(f'{PREFIX}/simulations/{first}/results?delegation=02').json()['total']==0
    assert client.get(f'{PREFIX}/simulations/{first}/results?delegation=01').json()['total']==1
    # A failed recalculation does not discard the usable saved calculation.
    client.post(PREFIX+'/jobs',json=body)
    monkeypatch.setattr(worker,'read_replenishment_source',lambda *a:(_ for _ in ()).throw(ValueError('Conexión interrumpida')))
    assert worker.process_one()
    assert next(r for r in client.get(PREFIX+'/calculations').json()['items'] if r['delegation']=='02')['id']==second
    # Replacing the final delegations releases the old snapshot/batches/results.
    setup_source(monkeypatch,['SAVED']);body['filters']['delegations']=['01','04','05']
    client.post(PREFIX+'/jobs',json=body);assert worker.process_one()
    with SessionLocal() as db:
        assert db.scalar(select(Scenario).where(Scenario.public_id==first)) is None
        assert db.scalar(select(Job).where(Job.public_id==jid)).status=='REPLACED'
        assert len(db.scalars(select(Current)).all())==4


def test_redistribution_requires_all_saved_calculations_and_permissions(client,monkeypatch):
    response=client.post(PREFIX+'/redistribution')
    assert response.status_code==409 and len(response.json()['detail']['missing_delegations'])==4
    setup_source(monkeypatch,['SAVED']);body=request();body['filters']['delegations']=['01']
    client.post(PREFIX+'/jobs',json=body);worker.process_one()
    response=client.post(PREFIX+'/redistribution')
    assert response.status_code==409
    assert [d['code'] for d in response.json()['detail']['missing_delegations']]==['02','04','05']
    from fastapi.testclient import TestClient
    from app.main import app
    customer=TestClient(app);customer.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'})
    assert customer.get(PREFIX+'/calculations').status_code==403
    assert customer.post(PREFIX+'/redistribution').status_code==403


def material(delegation,stock=10,maximum=10,need=0,incoming=0,outgoing=0,multiple=None,sku='MAT'):
    return {'sku':sku,'description':'Material','delegation':delegation,'unit_type':'UD','stock':stock,
        'incoming':incoming,'outgoing':outgoing,'maximum_stock':maximum,'inventory_position':stock+incoming-outgoing,
        'final_quantity':need,'daily_mean':1,'effective_multiple':multiple}


def test_redistribution_conserves_physical_stock_prioritizes_need_and_returns_remainder():
    rows=[material('01',stock=40,outgoing=5),material('02',stock=0,need=8),material('04',stock=2,need=4),material('05',stock=20)]
    result=redistribution(rows);moves=result['movements']
    assert [(m['from_delegation'],m['to_delegation'],m['quantity']) for m in moves]==[
        ('01','02',8),('01','04',4),('01','00',13),('05','00',10)]
    assert not result['unmet_needs'] and not result['material_warnings']
    assert result['summary']['transfers']==2 and result['summary']['returns_to_central']==2
    for code in ('01','05'):
        row=next(r for r in rows if r['delegation']==code)
        sent=sum(m['quantity'] for m in moves if m['from_delegation']==code)
        assert row['stock']-row['outgoing']-sent>=row['maximum_stock']
    assert rows[0]['stock']==40  # Pure proposal; no stock mutation.


def test_redistribution_never_dispatches_incoming_or_missing_material_data():
    rows=[material('01',stock=8,incoming=100),material('02',stock=0,need=10),material('04'),material('05')]
    result=redistribution(rows)
    assert not result['movements'] and result['unmet_needs'][0]['quantity']==10
    assert redistribution(rows[:-1])['material_warnings'][0]['sku']=='MAT'
    rows[0]['stock']=None
    assert not redistribution(rows)['movements']
    rows[0]['stock']=8;rows[1]['unit_type']='M'
    assert 'unidades' in redistribution(rows)['material_warnings'][0]['reason']


def test_redistribution_respects_both_decimal_multiples_and_does_not_overallocate():
    rows=[material('01',stock=35.9,maximum=10,multiple=2.5),material('02',stock=0,need=16,multiple=4),material('04',stock=0,need=10,multiple=5),material('05')]
    result=redistribution(rows);moves=result['movements']
    # LCM(2.5,4)=20 cannot satisfy a need of 16 without exceeding it.
    assert not any(m['to_delegation']=='02' for m in moves)
    assert [(m['to_delegation'],m['quantity']) for m in moves]==[('04',10),('00',15)]
    assert result['unmet_needs'][0]['quantity']==16
    assert sum(Decimal(str(m['quantity'])) for m in moves)==Decimal(25)


def test_redistribution_api_uses_current_snapshots_without_exit_reads(client,monkeypatch):
    setup_source(monkeypatch,['SAVED'])
    client.post(PREFIX+'/jobs',json=request());worker.process_one()
    with SessionLocal() as db:
        for result in db.scalars(select(Result)):
            row=material(result.delegation,stock=30 if result.delegation=='01' else 0,need=4 if result.delegation=='02' else 0,sku=result.sku)
            result.payload={**result.payload,**row}
        db.commit()
    monkeypatch.setattr(worker,'read_replenishment_source',lambda *a:pytest.fail('Must use snapshots'))
    response=client.post(PREFIX+'/redistribution')
    assert response.status_code==200
    plan=response.json();assert plan['read_only_exit']
    assert len(plan['calculations'])==4 and plan['movements'][0]['to_delegation']=='02'
    assert plan['movements'][0]['quantity']==4


def test_redistribution_excel_matches_proposal_and_rejects_changed_data(client,monkeypatch):
    import io
    from openpyxl import load_workbook
    setup_source(monkeypatch,['000012'])
    client.post(PREFIX+'/jobs',json=request());worker.process_one()
    with SessionLocal() as db:
        for result in db.scalars(select(Result)):
            row=material(result.delegation,stock=30 if result.delegation=='01' else 0,need=4 if result.delegation=='02' else 0,sku=result.sku)
            row['description']='=HYPERLINK("example.test","Material")'
            result.payload={**result.payload,**row}
        db.commit()
    proposal=client.post(PREFIX+'/redistribution').json()
    response=client.post(PREFIX+'/redistribution/export.xlsx',json={'fingerprint':proposal['fingerprint']})
    assert response.status_code==200 and 'spreadsheetml' in response.headers['content-type']
    book=load_workbook(io.BytesIO(response.content))
    assert book.sheetnames==['Movimientos','Necesidades sin cubrir','Alertas','Cálculos utilizados','Resumen']
    sheet=book['Movimientos']
    assert sheet.max_row==len(proposal['movements'])+1
    assert sheet['A2'].value=='000012' and sheet['A2'].data_type=='s'
    assert sheet['B2'].value.startswith('=HYPERLINK') and sheet['B2'].data_type=='s'
    assert sheet['C2'].value=='01' and sheet['E2'].value=='02'
    assert sheet['G2'].value==4 and sheet['G2'].data_type=='n'
    assert sheet['E3'].value=='00' and sheet['F3'].value=='Almeiras'
    assert book['Cálculos utilizados'].max_row==5
    assert book['Resumen']['B3'].value==proposal['fingerprint']
    with SessionLocal() as db:
        result=db.scalar(select(Result).where(Result.delegation=='02'))
        result.payload={**result.payload,'final_quantity':3};db.commit()
    response=client.post(PREFIX+'/redistribution/export.xlsx',json={'fingerprint':proposal['fingerprint']})
    assert response.status_code==409 and 'Vuelve a calcular' in response.json()['detail']
    assert client.post(PREFIX+'/redistribution/export.xlsx',json={'fingerprint':'bad'}).status_code==422


def test_redistribution_excel_with_empty_movements_and_missing_calculations(client,monkeypatch):
    import io
    from openpyxl import load_workbook
    assert client.post(PREFIX+'/redistribution/export.xlsx',json={'fingerprint':'0'*64}).status_code==409
    setup_source(monkeypatch,['EMPTY'])
    client.post(PREFIX+'/jobs',json=request());worker.process_one()
    proposal=client.post(PREFIX+'/redistribution').json()
    assert proposal['movements']==[] and proposal['unmet_needs']
    response=client.post(PREFIX+'/redistribution/export.xlsx',json={'fingerprint':proposal['fingerprint']})
    assert response.status_code==200
    book=load_workbook(io.BytesIO(response.content))
    assert book['Movimientos'].max_row==1
    assert book['Necesidades sin cubrir'].max_row>1
    from fastapi.testclient import TestClient
    from app.main import app
    customer=TestClient(app);customer.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'})
    assert customer.post(PREFIX+'/redistribution/export.xlsx',json={'fingerprint':proposal['fingerprint']}).status_code==403


def test_redistribution_compares_statistics_from_saved_sources_without_overwriting(client,monkeypatch):
    from datetime import date,timedelta
    import io
    from openpyxl import load_workbook
    setup_source(monkeypatch,['STAT'])
    raw=source(['STAT']);raw['start']='2026-04-01';raw['end']='2026-04-30'
    values=[1]*11+[2]*10+[20]*9
    raw['sales']=[{'sku':'STAT','delegation':delegation,'day':(date(2026,4,1)+timedelta(days=i)).isoformat(),'sold':value,'returned':0} for delegation in ['01','02','04','05'] for i,value in enumerate(values)]
    for stock in raw['stocks']:stock['stock']=500 if stock['delegation']=='01' else 0
    monkeypatch.setattr(worker,'read_replenishment_source',lambda *a:raw)
    body=request();body['filters']['date_to']='2026-04-30';body['temporary_parameters']['use_safety_stock']=False
    queued=client.post(PREFIX+'/jobs',json=body).json();assert worker.process_one()
    with SessionLocal() as db:before=[dict(row.payload) for row in db.scalars(select(Result).order_by(Result.id))]
    proposals={}
    for basis in ['MEAN','MEDIAN','MODE']:
        result=client.post(PREFIX+'/redistribution',json={'consumption_basis':basis})
        assert result.status_code==200,result.text
        proposal=result.json();assert proposal['consumption_basis']==basis
        assert not proposal['material_warnings']
        proposals[basis]=proposal
    returns={key:sum(move['quantity'] for move in value['movements'] if move['kind']=='RETURN_CENTRAL') for key,value in proposals.items()}
    assert returns['MEAN']<returns['MEDIAN']<returns['MODE']
    assert len({proposal['fingerprint'] for proposal in proposals.values()})==3
    chosen=proposals['MEDIAN']
    exported=client.post(PREFIX+'/redistribution/export.xlsx',json={'fingerprint':chosen['fingerprint'],'consumption_basis':'MEDIAN'})
    assert exported.status_code==200,exported.text
    summary=dict(load_workbook(io.BytesIO(exported.content))['Resumen'].iter_rows(min_row=2,values_only=True))
    assert summary['Criterio de consumo']=='Mediana'
    assert client.post(PREFIX+'/redistribution/export.xlsx',json={'fingerprint':chosen['fingerprint'],'consumption_basis':'MEAN'}).status_code==409
    with SessionLocal() as db:assert [row.payload for row in db.scalars(select(Result).order_by(Result.id))]==before
    assert client.post(PREFIX+'/redistribution',json={'consumption_basis':'INVALID'}).status_code==422
