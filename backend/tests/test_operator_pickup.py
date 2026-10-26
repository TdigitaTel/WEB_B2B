import pytest
pytestmark = pytest.mark.usefixtures("operator_with_almeiras_access")
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.main import app
from app.models import Order, OrderStatusHistory, User

bootstrap()


def test_operator_can_override_immediate_and_history_is_recorded(monkeypatch, pickup_schedule):
    operator=TestClient(app)
    operator.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'})
    customer=TestClient(app)
    customer.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'})
    store=customer.get('/api/v1/stores').json()[0]
    tomorrow=datetime.now(ZoneInfo('Europe/Madrid')).date()+timedelta(days=1)
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.role=='OPERADOR_TIENDA'))
        order=Order(order_number='WEB-PICKUP-OVERRIDE',company_code=store['company_code'],delegation_code=store['code'],origen_pedido='B2B',estado_registro_exit='PENDIENTE',pickup_date=tomorrow,subtotal=0,tax_total=0,total=0)
        db.add(order);db.commit();oid=order.public_id;pk=order.id
    path=f'/api/v1/store/orders/{oid}/pickup'
    assert customer.patch(path,json={'pickup_date':None}).status_code==403
    assert operator.patch(path,json={}).status_code==422
    assert operator.patch(path,json={'pickup_date':None}).status_code==200
    with SessionLocal() as db:
        assert db.get(Order,pk).pickup_date is None
        assert 'Inmediata' in db.scalar(select(OrderStatusHistory).where(OrderStatusHistory.order_id==pk)).note
    assert operator.patch(path,json={'pickup_date':tomorrow.isoformat()}).status_code==200
    with SessionLocal() as db:
        row=db.get(Order,pk);row.estado_registro_exit='ENTREGADO';db.commit()
    assert operator.patch(path,json={'pickup_date':None}).status_code==409
