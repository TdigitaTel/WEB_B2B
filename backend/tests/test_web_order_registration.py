from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.main import app
from app.models import Order, OrderItem, OrderStatusHistory, IntegrationOutbox, SyncStatus, User

bootstrap()


def test_operator_link_unlink_delete_and_permissions():
    operator = TestClient(app)
    assert operator.post('/api/v1/auth/login', json={'email':'operador@bermudez.test','password':'123456'}).status_code == 200
    customer = TestClient(app)
    customer.post('/api/v1/auth/login', json={'email':'compras001@cliente.test','password':'123456'})
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.role=='OPERADOR_TIENDA'))
        order = Order(order_number='WEB-MANUAL-TEST', company_code=user.company_code, delegation_code='00', customer_code='CLI00001', origen_pedido='B2B', estado_registro_exit='ATENDIDO', subtotal=1, tax_total=0, total=1)
        db.add(order); db.flush()
        db.add(OrderItem(order_id=order.id, sku='MANUAL', description='Material', quantity=2, unit='UD', unit_price=1, discount_pct=0, tax_rate=0, line_total=2, served_quantity=2, pending_quantity=0))
        db.add(IntegrationOutbox(aggregate_type='ORDER', aggregate_id=order.public_id, event_type='ORDER_CREATED', payload={}, sync_status=SyncStatus.error))
        db.commit(); oid=order.public_id; local_id=order.id
    path=f'/api/v1/store/orders/{oid}'
    assert customer.patch(path+'/registration',json={'state':'PENDIENTE'}).status_code==403
    assert customer.delete(path).status_code==403
    assert operator.delete(path).status_code==409
    assert operator.patch(path+'/registration',json={'state':'REGISTRADO','exit_order_number':'  '}).status_code==422
    linked=operator.patch(path+'/registration',json={'state':'REGISTRADO','exit_order_number':'2026~AL~MANUAL'})
    assert linked.status_code==200, linked.text
    assert linked.json()['nro_pedido_exit']=='2026/AL/MANUAL'
    assert linked.json()['estado_registro_exit']=='REGISTRADO'
    assert operator.delete(path).status_code==409
    pending=operator.patch(path+'/registration',json={'state':'PENDIENTE'})
    assert pending.status_code==200, pending.text
    assert pending.json()['nro_pedido_exit'] is None and pending.json()['fecha_registro_exit'] is None
    assert pending.json()['delivered_at'] is None
    assert pending.json()['items'][0]['served_quantity']==0
    with SessionLocal() as db:
        event=db.scalar(select(IntegrationOutbox).where(IntegrationOutbox.aggregate_id==oid))
        assert event.sync_status==SyncStatus.pending
    assert operator.delete(path).status_code==200
    with SessionLocal() as db:
        assert db.get(Order,local_id) is None
        assert not db.scalars(select(OrderItem).where(OrderItem.order_id==local_id)).all()
        assert not db.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id==local_id)).all()
        assert not db.scalars(select(IntegrationOutbox).where(IntegrationOutbox.aggregate_id==oid)).all()


def test_duplicate_exit_link_and_non_web_are_rejected():
    operator=TestClient(app)
    operator.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'})
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.role=='OPERADOR_TIENDA'))
        ids=[]
        for number, origin, exit_number in [('WEB-DUP-A','B2B','2026/AL/DUP'),('WEB-DUP-B','B2B',None),('EXIT-ONLY','EXIT',None)]:
            row=Order(order_number=number, company_code=user.company_code, delegation_code='00', origen_pedido=origin, estado_registro_exit='REGISTRADO' if exit_number else 'PENDIENTE', nro_pedido_exit=exit_number, subtotal=0,tax_total=0,total=0)
            db.add(row);db.flush();ids.append(row.public_id)
        db.commit()
    assert operator.patch(f'/api/v1/store/orders/{ids[1]}/registration',json={'state':'REGISTRADO','exit_order_number':'2026~AL~DUP'}).status_code==409
    assert operator.patch(f'/api/v1/store/orders/{ids[2]}/registration',json={'state':'PENDIENTE'}).status_code==404
    assert operator.delete(f'/api/v1/store/orders/{ids[2]}').status_code==404
