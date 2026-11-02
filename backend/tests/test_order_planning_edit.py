from datetime import datetime, timezone
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.bootstrap import main as bootstrap
from app.main import app
from app.db import SessionLocal
from app.models import Order, User, OrderStatusHistory, AuditEvent
bootstrap()
pytestmark=pytest.mark.usefixtures('operator_with_almeiras_access')
@pytest.fixture
def context():
    op=TestClient(app);op.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'})
    customer=TestClient(app);customer.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'})
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.role=='OPERADOR_TIENDA'))
        order=Order(order_number='WEB-PLAN-'+uuid4().hex,company_code=user.company_code,delegation_code=user.delegation_code,
            origen_pedido='B2B',estado_registro_exit='REGISTRADO',attention_deadline_at=datetime(2026,10,30,11,41,tzinfo=timezone.utc),notes='Inicial',subtotal=0,tax_total=0,total=0)
        db.add(order);db.commit();pk=order.id;oid=order.public_id
    return op,customer,f'/api/v1/store/orders/{oid}/planning',pk

def body():
    return {'expected_at':'2026-11-02T14:30:00+01:00','observations':'Entrega acordada con cliente','previous_expected_at':'2026-10-30T12:41:00+01:00','previous_observations':'Inicial'}

def test_persist_history_and_conflict(context):
    op,customer,path,pk=context
    assert customer.patch(path,json=body()).status_code==403
    assert TestClient(app).patch(path,json=body()).status_code==401
    result=op.patch(path,json=body());assert result.status_code==200,result.text
    assert result.json()['notes']==body()['observations']
    with SessionLocal() as db:
        order=db.get(Order,pk)
        assert order.attention_deadline_at.replace(tzinfo=timezone.utc)==datetime(2026,11,2,13,30,tzinfo=timezone.utc)
        assert order.notes==body()['observations'] and order.pickup_date is None and order.estado_registro_exit=='REGISTRADO'
        history=db.scalar(select(OrderStatusHistory).where(OrderStatusHistory.order_id==pk))
        assert '02/11/2026 14:30' in history.note
        audit=db.scalar(select(AuditEvent).where(AuditEvent.entity_id==order.public_id,AuditEvent.action=='ORDER_PLANNING_CHANGED'))
        assert audit.metadata_json['previous']['observations']=='Inicial'
    assert op.patch(path,json=body()).status_code==409
    current={**body(),'previous_expected_at':'2026-11-02T13:30:00Z','previous_observations':body()['observations']}
    assert op.patch(path,json=current).status_code==200
    with SessionLocal() as db:
        assert len(db.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id==pk)).all())==1
    assert op.patch(path,json={**current,'observations':'Solo observaciones'}).status_code==200

@pytest.mark.parametrize('stamp',['2026-11-02T14:30:00',None,'incorrecto'])
def test_timezone_required(context,stamp):
    op,_,path,_=context
    assert op.patch(path,json={**body(),'expected_at':stamp}).status_code==422

@pytest.mark.parametrize('state',['ATENDIDO','ENTREGADO','FACTURADO'])
def test_closed_order(context,state):
    op,_,path,pk=context
    with SessionLocal() as db:
        order=db.get(Order,pk);order.estado_registro_exit=state;db.commit()
    assert op.patch(path,json=body()).status_code==409

def test_scope(context):
    op,_,path,pk=context
    with SessionLocal() as db:
        order=db.get(Order,pk);order.company_code=987;order.delegation_code='ZZ';db.commit()
    assert op.patch(path,json=body()).status_code==404

def test_conflicting_notes_without_date_change(context):
    op,_,path,pk=context
    with SessionLocal() as db:
        order=db.get(Order,pk);order.notes='Otro operador';db.commit()
    assert op.patch(path,json=body()).status_code==409
