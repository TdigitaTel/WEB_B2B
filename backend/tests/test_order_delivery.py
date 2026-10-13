from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.models import Order, OrderStatusHistory, User
from app.main import app
from app.exit_orders import ExitOrderInput, upsert_exit_order
bootstrap()

def same_time(a,b):
    return datetime.fromisoformat(a).replace(tzinfo=timezone.utc)==datetime.fromisoformat(b).replace(tzinfo=timezone.utc)

def test_delivery_is_persisted_and_survives_refresh(monkeypatch):
    from app import main as module
    operator=TestClient(app)
    operator.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'})
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email=='operador@bermudez.test'))
        order=Order(order_number='WEB-DELIVERY-TEST',customer_code='CLI00001',company_code=user.company_code,delegation_code=user.delegation_code,origen_pedido='B2B',estado_registro_exit='ATENDIDO',nro_pedido_exit='2026/TEST/DELIVERY',subtotal=0,tax_total=0,total=0)
        db.add(order);db.commit();public_id=order.public_id;code=order.delegation_code;company=order.company_code;actor_id=user.id
    customer=TestClient(app)
    customer.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'})
    body={'order_id':public_id,'order_date':'2026-10-11'}
    assert customer.post('/api/v1/store/orders/delivery',json=body).status_code==403
    first=operator.post('/api/v1/store/orders/delivery',json=body)
    assert first.status_code==200,first.text
    stamp=first.json()['delivered_at']
    assert stamp and first.json()['estado_registro_exit']=='ENTREGADO'
    repeat=operator.post('/api/v1/store/orders/delivery',json=body)
    assert repeat.status_code==200 and same_time(repeat.json()['delivered_at'],stamp)
    record=ExitOrderInput(exit_order_id='2026/TEST/DELIVERY',order_number='DELIVERY',customer_code='CLI00001',store_code=code,company_code=company,estado_registro_exit='REGISTRADO',source_updated_at=datetime.now(timezone.utc),recorded_at=datetime.now(timezone.utc),customer_reference='WEB-DELIVERY-TEST',auxiliary_reference='PEDIDO GENERADO WEB B2B',lines=[])
    with SessionLocal() as db:
        synced=upsert_exit_order(db,record,db.get(User,actor_id))
        assert synced.estado_registro_exit=='ENTREGADO' and synced.delivered_at
        events=db.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id==synced.id,OrderStatusHistory.source=='WEB',OrderStatusHistory.estado_registro_exit=='ENTREGADO')).all()
        assert len(events)==1 and events[0].changed_by_user_id==actor_id
        db.commit()
    monkeypatch.setattr(module,'fetch_exit_orders_live',lambda *args:[record])
    monkeypatch.setattr(module,'fetch_delivery_statuses_for_orders',lambda *args:[])
    assert not any(row['nro_pedido_exit'] == record.exit_order_id for row in operator.get('/api/v1/store/orders?view=web&delegation=TODAS&state=PENDIENTE').json())
    listed=operator.get('/api/v1/store/orders?view=web&delegation=TODAS&state=ENTREGADO').json()
    delivered = [row for row in listed if row['nro_pedido_exit'] == record.exit_order_id]
    assert len(delivered)==1 and same_time(delivered[0]['delivered_at'],stamp)
    monkeypatch.setattr(module,'fetch_customer_exit_orders',lambda *args:[record])
    monkeypatch.setattr(module,'fetch_customer_delivery_statuses',lambda *args:[])
    visible=customer.get('/api/v1/orders?state=ENTREGADO&date_from=2026-01-01&date_to=2027-01-01')
    assert visible.status_code==200,visible.text
    found=next(o for o in visible.json() if o['id']==public_id)
    assert same_time(found['delivered_at'],stamp) and found['estado_registro_exit']=='ENTREGADO'

def test_other_delegation_cannot_confirm_delivery():
    operator=TestClient(app)
    operator.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'})
    with SessionLocal() as db:
        order=Order(order_number='WEB-OTHER-DELEGATION',customer_code='CLI00001',company_code=999,delegation_code='999',origen_pedido='B2B',estado_registro_exit='ATENDIDO',subtotal=0,tax_total=0,total=0)
        db.add(order);db.commit();order_id=order.public_id
    assert operator.post('/api/v1/store/orders/delivery',json={'order_id':order_id,'order_date':'2026-10-11'}).status_code==404
    with SessionLocal() as db:
        assert db.scalar(select(Order).where(Order.public_id==order_id)).delivered_at is None

def test_live_web_delivery_creates_local_record_once(monkeypatch):
    from app import main as module
    operator=TestClient(app)
    operator.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'})
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email=='operador@bermudez.test'))
        record=ExitOrderInput(exit_order_id='2026/TEST/LIVE',order_number='LIVE-DELIVERY',customer_code='CLI00001',store_code=user.delegation_code,company_code=user.company_code,estado_registro_exit='ATENDIDO',source_updated_at=datetime.now(timezone.utc),auxiliary_reference='PEDIDO GENERADO WEB B2B',lines=[])
    monkeypatch.setattr(module,'fetch_exit_orders_live',lambda *args:[record])
    data={'order_id':record.exit_order_id,'order_date':'2026-10-11'}
    first=operator.post('/api/v1/store/orders/delivery',json=data)
    assert first.status_code==200,first.text
    repeat=operator.post('/api/v1/store/orders/delivery',json=data)
    assert repeat.status_code==200 and same_time(first.json()['delivered_at'],repeat.json()['delivered_at'])
    with SessionLocal() as db:
        rows=db.scalars(select(Order).where(Order.nro_pedido_exit==record.exit_order_id)).all()
        assert len(rows)==1 and rows[0].delivered_at is not None
    assert operator.post('/api/v1/store/orders/delivery',json={'order_id':'missing','order_date':'2026-10-11'}).status_code==404


def test_delivery_requires_attended_state():
    operator=TestClient(app)
    operator.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'})
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email=='operador@bermudez.test'))
        ids=[]
        for state in ('PENDIENTE','REGISTRADO','EN_PROCESO','EN_PREPARACION','FACTURADO'):
            order=Order(order_number=f'WEB-DELIVERY-BLOCK-{state}', company_code=user.company_code,delegation_code=user.delegation_code,origen_pedido='B2B',estado_registro_exit=state,subtotal=0,tax_total=0,total=0)
            db.add(order);db.flush();ids.append(order.public_id)
        db.commit()
    for oid in ids:
        response=operator.post('/api/v1/store/orders/delivery',json={'order_id':oid,'order_date':'2026-10-13'})
        assert response.status_code==409,response.text
        with SessionLocal() as db:
            assert db.scalar(select(Order).where(Order.public_id==oid)).delivered_at is None
