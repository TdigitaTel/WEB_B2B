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


def test_pending_creates_missing_robot_event_once():
    operator=TestClient(app)
    operator.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'})
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.role=='OPERADOR_TIENDA'))
        order=Order(order_number='WEB-PENDING-NO-EVENT',company_code=user.company_code,delegation_code='00',origen_pedido='B2B',estado_registro_exit='REGISTRADO',nro_pedido_exit='2026/AL/NOEVENT',subtotal=0,tax_total=0,total=0)
        db.add(order);db.commit();oid=order.public_id
    assert operator.patch(f'/api/v1/store/orders/{oid}/registration',json={'state':'PENDIENTE'}).status_code==200
    # Ya está pendiente: la nueva regla rechaza repetir el cambio sin duplicar eventos.
    assert operator.patch(f'/api/v1/store/orders/{oid}/registration',json={'state':'PENDIENTE'}).status_code==409
    with SessionLocal() as db:
        events=db.scalars(select(IntegrationOutbox).where(IntegrationOutbox.aggregate_id==oid)).all()
        assert len(events)==1 and events[0].sync_status==SyncStatus.pending
        assert events[0].event_type=='ORDER_CREATED'
        assert db.scalar(select(Order).where(Order.public_id==oid)).nro_pedido_exit is None


def test_manual_exit_datetime_from_blocked_records_actual_history_and_is_idempotent(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo
    from app.config import settings
    from app.models import AuditEvent
    operator=TestClient(app)
    operator.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'})
    customer=TestClient(app)
    customer.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'})
    registered=datetime.now(timezone.utc).replace(microsecond=0)-timedelta(minutes=5)
    madrid=registered.astimezone(ZoneInfo('Europe/Madrid')).replace(tzinfo=None).isoformat()
    with SessionLocal() as db:
        actor=db.scalar(select(User).where(User.role=='OPERADOR_TIENDA'))
        row=Order(order_number='WEB-MANUAL-WITH-DATETIME',company_code=actor.company_code,delegation_code='00',customer_code='CLI00001',origen_pedido='B2B',estado_registro_exit='BLOQUEADO',subtotal=1,tax_total=0,total=1)
        db.add(row);db.flush()
        db.add(OrderStatusHistory(order_id=row.id,estado_registro_exit='PENDIENTE',created_at=registered-timedelta(minutes=5),source='WEB'))
        db.add(IntegrationOutbox(aggregate_type='ORDER',aggregate_id=row.public_id,event_type='ORDER_CREATED',payload={},sync_status=SyncStatus.error,last_error='Robot no disponible'))
        db.commit();oid=row.public_id;pk=row.id;actor_id=actor.id
    path=f'/api/v1/store/orders/{oid}/registration'
    data={'state':'REGISTRADO','exit_order_number':'2026/AL/MANUAL-DATETIME','exit_registered_at':madrid}
    assert customer.patch(path,json=data).status_code==403
    response=operator.patch(path,json=data)
    assert response.status_code==200,response.text
    assert response.json()['estado_registro_exit']=='REGISTRADO'
    events=[event for event in response.json()['history'] if event['estado_registro_exit']=='REGISTRADO']
    assert len(events)==1 and 'Registro manual en EXIT' in events[0]['note']
    assert operator.patch(path,json=data).status_code==200
    with SessionLocal() as db:
        saved=db.get(Order,pk)
        assert saved.fecha_registro_exit.replace(tzinfo=timezone.utc)==registered
        history=db.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id==pk,OrderStatusHistory.estado_registro_exit=='REGISTRADO')).all()
        assert len(history)==1 and history[0].changed_by_user_id==actor_id
        assert history[0].created_at.replace(tzinfo=timezone.utc)==registered
        assert not db.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id==pk,OrderStatusHistory.estado_registro_exit.in_(['ATENDIDO','ENTREGADO']))).all()
        outbox=db.scalar(select(IntegrationOutbox).where(IntegrationOutbox.aggregate_id==oid))
        assert outbox.sync_status==SyncStatus.synced and outbox.last_error is None
        audit=db.scalar(select(AuditEvent).where(AuditEvent.entity_id==oid,AuditEvent.action=='ORDER_REGISTRATION_CHANGED'))
        assert audit.user_id==actor_id and audit.metadata_json['exit_registered_at']==registered.isoformat()
    client_order=customer.get(f'/api/v1/orders/{oid}').json()
    assert any(event['estado_registro_exit']=='REGISTRADO' for event in client_order['history'])
    assert next(stage for stage in client_order['workflow'] if stage['etapa']=='EN_PROCESAMIENTO')['completed_at']
    monkeypatch.setattr(settings,'show_order_status_history',False)
    listing=operator.get('/api/v1/store/orders?view=web&state=TODOS&delegation=TODAS')
    assert listing.status_code==200,listing.text
    visible=next(item for item in listing.json() if item['id']==oid)
    assert visible['history_enabled'] and any(event['estado_registro_exit']=='REGISTRADO' for event in visible['history'])
    assert customer.get(f'/api/v1/orders/{oid}').json()['history_enabled'] is False


def test_manual_exit_rejects_invalid_future_and_nonexistent_madrid_time():
    from datetime import datetime,timedelta,timezone
    operator=TestClient(app)
    operator.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'})
    with SessionLocal() as db:
        actor=db.scalar(select(User).where(User.role=='OPERADOR_TIENDA'))
        row=Order(order_number='WEB-MANUAL-BAD-DATE',company_code=actor.company_code,delegation_code='00',origen_pedido='B2B',estado_registro_exit='PENDIENTE',subtotal=0,tax_total=0,total=0)
        db.add(row);db.commit();oid=row.public_id;pk=row.id
    path=f'/api/v1/store/orders/{oid}/registration'
    for value in ['fecha inválida',(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),'2026-03-29T02:30:00']:
        result=operator.patch(path,json={'state':'REGISTRADO','exit_order_number':'2026/AL/BAD-DATE','exit_registered_at':value})
        assert result.status_code==422,result.text
    with SessionLocal() as db:
        assert db.get(Order,pk).nro_pedido_exit is None
        assert not db.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id==pk)).all()


def test_only_registered_or_blocked_can_be_reset_to_pending():
    from datetime import datetime, timezone
    operator=TestClient(app)
    operator.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'})
    with SessionLocal() as db:
        actor=db.scalar(select(User).where(User.role=='OPERADOR_TIENDA'))
        cases=[]
        for state in ('BORRADOR','PENDIENTE','BLOQUEADO','EN_PROCESO','EN_PREPARACION','ATENDIDO','ENTREGADO','FACTURADO','REGISTRADO'):
            row=Order(order_number='WEB-RESET-GUARD-'+state,company_code=actor.company_code,delegation_code='00',
                      origen_pedido='B2B',estado_registro_exit=state,nro_pedido_exit='EXIT-RESET-'+state,
                      delivered_at=datetime.now(timezone.utc) if state=='ENTREGADO' else None)
            db.add(row);db.flush();cases.append((row.public_id,row.id,state,row.nro_pedido_exit))
        db.commit()
    for public_id,pk,state,number in cases:
        response=operator.patch(f'/api/v1/store/orders/{public_id}/registration',json={'state':'PENDIENTE'})
        assert response.status_code==(200 if state in {'REGISTRADO','BLOQUEADO'} else 409),response.text
        with SessionLocal() as db:
            row=db.get(Order,pk)
            assert row.estado_registro_exit==('PENDIENTE' if state in {'REGISTRADO','BLOQUEADO'} else state)
            assert row.nro_pedido_exit==(None if state in {'REGISTRADO','BLOQUEADO'} else number)
            if state not in {'REGISTRADO','BLOQUEADO'}:
                assert not db.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id==pk)).all()


def test_delivered_registered_or_blocked_cannot_be_reset_to_pending():
    from datetime import datetime, timezone
    operator = TestClient(app)
    operator.post('/api/v1/auth/login', json={'email': 'operador@bermudez.test', 'password': '123456'})
    for state in ('REGISTRADO', 'BLOQUEADO'):
        with SessionLocal() as db:
            actor = db.scalar(select(User).where(User.role == 'OPERADOR_TIENDA'))
            row = Order(order_number='WEB-DELIVERED-RESET-' + state, company_code=actor.company_code,
                        delegation_code='00', origen_pedido='B2B', estado_registro_exit=state,
                        delivered_at=datetime.now(timezone.utc))
            db.add(row); db.commit()
            public_id, pk = row.public_id, row.id
        response = operator.patch(f'/api/v1/store/orders/{public_id}/registration', json={'state': 'PENDIENTE'})
        assert response.status_code == 409, response.text
        with SessionLocal() as db:
            row = db.get(Order, pk)
            assert row.estado_registro_exit == state
            assert row.delivered_at is not None
            assert not db.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id == pk)).all()
