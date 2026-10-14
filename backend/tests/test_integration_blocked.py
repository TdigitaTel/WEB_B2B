from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.bootstrap import main as bootstrap
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Order, OrderStatusHistory

bootstrap()


def test_rpa_can_register_blocked_order_and_repeat(monkeypatch):
    monkeypatch.setattr(settings, "integration_api_key", "blocked-test-key")
    client=TestClient(app)
    with SessionLocal() as db:
        order=Order(order_number="WEB-RPA-BLOCKED", company_code=0, delegation_code="00", origen_pedido="B2B", estado_registro_exit="BLOQUEADO", subtotal=0,tax_total=0,total=0)
        db.add(order);db.commit();oid=order.public_id;local_id=order.id
    data={"order_id":oid,"estado_registro_exit":"REGISTRADO","nro_pedido_exit":"2026/AL/RPA-BLOCKED","source":"RPA","occurred_at":"2026-10-14T10:00:00Z"}
    assert client.patch("/api/v1/integrations/orders/estado",json=data).status_code==401
    response=client.patch("/api/v1/integrations/orders/estado",headers={"X-Integration-Key":"blocked-test-key"},json=data)
    assert response.status_code==200,response.text
    assert response.json()["recorded_statuses"]==["REGISTRADO"]
    assert response.json()["order"]["nro_pedido_exit"]==data["nro_pedido_exit"]
    repeat=client.patch("/api/v1/integrations/orders/estado",headers={"X-Integration-Key":"blocked-test-key"},json=data)
    assert repeat.status_code==200 and repeat.json()["changed"] is False
    with SessionLocal() as db:
        order=db.get(Order,local_id)
        assert order.estado_registro_exit=="REGISTRADO" and order.fecha_registro_exit
        events=db.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id==local_id)).all()
        assert len(events)==1 and events[0].source=="RPA"
    backwards=client.patch("/api/v1/integrations/orders/estado",headers={"X-Integration-Key":"blocked-test-key"},json={**data,"estado_registro_exit":"PENDIENTE"})
    assert backwards.status_code==409


def test_blocked_order_cannot_skip_registration(monkeypatch):
    monkeypatch.setattr(settings,"integration_api_key","blocked-test-key")
    with SessionLocal() as db:
        order=Order(order_number="WEB-RPA-BLOCKED-SKIP",company_code=0,delegation_code="00",origen_pedido="B2B",estado_registro_exit="BLOQUEADO",subtotal=0,tax_total=0,total=0)
        db.add(order);db.commit();oid=order.public_id
    client=TestClient(app)
    response=client.patch("/api/v1/integrations/orders/estado",headers={"X-Integration-Key":"blocked-test-key"},json={"order_id":oid,"estado_registro_exit":"ENTREGADO","source":"RPA"})
    assert response.status_code==409
