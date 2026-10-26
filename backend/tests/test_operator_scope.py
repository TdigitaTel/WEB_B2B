from fastapi.testclient import TestClient
from sqlalchemy import select
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.models import User, Order, OperatorAccess
from app.main import app
bootstrap()


def test_visibility_and_mutations_follow_configured_delegations(monkeypatch):
    import app.main as module
    from app.exit_orders import ExitOrderInput
    from app.delegations import Delegation
    client=TestClient(app)
    client.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'})
    monkeypatch.setattr(module,'fetch_customer_exit_orders',lambda *a:[])
    monkeypatch.setattr(module,'fetch_kardex_timings',lambda *a:{})
    monkeypatch.setattr(module,'fetch_delivery_statuses_for_orders',lambda *a:[])
    with SessionLocal() as db:
        actor=db.scalar(select(User).where(User.email=='operador@bermudez.test'));pk=actor.id
        assert db.get(OperatorAccess,pk) is None
        access=OperatorAccess(user_id=pk,exit_code='SCOPE-TEST',permissions={'orders':True,'delegation_ids':['999:A']})
        db.add(access)
        ids={}
        for code in ['A','B']:
            order=Order(order_number='WEB-SCOPE-'+code,company_code=999,delegation_code=code,origen_pedido='B2B',estado_registro_exit='REGISTRADO')
            db.add(order);db.flush();ids[code]=order.public_id
        db.commit()
    records=[ExitOrderInput(exit_order_id='2026/TEST/'+code,order_number=code,customer_code='SCOPE-C',company_code=999,store_code=code,estado_registro_exit='ATENDIDO',source_updated_at='2026-10-26T10:00:00Z') for code in ['A','B']]
    monkeypatch.setattr(module,'fetch_exit_orders_live',lambda *a:records)
    monkeypatch.setattr(module,'live_delegations',lambda:[Delegation(999,code,code,'','','') for code in ['A','B']])
    try:
        rows=client.get('/api/v1/store/orders?view=web&delegation=TODAS').json()
        assert ids['A'] in {r['id'] for r in rows} and ids['B'] not in {r['id'] for r in rows}
        assert [r['id'] for r in client.get('/api/v1/store/orders/delegations').json()]==['999:A']
        attended=client.get('/api/v1/store/orders?view=attended').json()
        assert {r['nro_pedido_exit'] for r in attended}=={'2026/TEST/A'}
        assert client.patch(f"/api/v1/store/orders/{ids['B']}/registration",json={'state':'PENDIENTE'}).status_code==404
        assert client.patch(f"/api/v1/store/orders/{ids['A']}/registration",json={'state':'PENDIENTE'}).status_code==200
        with SessionLocal() as db:
            access=db.get(OperatorAccess,pk);access.permissions={**access.permissions,'all_delegations':True};db.commit()
        rows=client.get('/api/v1/store/orders?view=web&delegation=TODAS').json()
        assert set(ids.values()).issubset({r['id'] for r in rows})
        assert len(client.get('/api/v1/store/orders/delegations').json())==2
        assert client.patch(f"/api/v1/store/orders/{ids['B']}/registration",json={'state':'PENDIENTE'}).status_code==200
    finally:
        with SessionLocal() as db:
            db.delete(db.get(OperatorAccess,pk));db.commit()
