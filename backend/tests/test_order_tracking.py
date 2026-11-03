from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.main import app
from app.models import Order, OrderItem, OrderLinePlanning, OrderTrackingLink, User
from app.exit_orders import ExitOrderInput

bootstrap()
pytestmark = pytest.mark.usefixtures("operator_with_almeiras_access")


@pytest.fixture(autouse=True)
def tracking_sources(monkeypatch):
    from app import order_tracking as module
    monkeypatch.setattr(module, "fetch_customer_exit_orders", lambda *a, **k: [])
    monkeypatch.setattr(module, "fetch_delivery_statuses_for_orders", lambda *a, **k: [])


def operator():
    client = TestClient(app)
    assert client.post("/api/v1/auth/login", json={"email":"operador@bermudez.test","password":"123456"}).status_code == 200
    return client


def setup_order(company=None):
    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.email == "operador@bermudez.test"))
        order = Order(order_number="WEB-TRACK-" + uuid4().hex, customer_code="CLI00001", company_code=actor.company_code if company is None else company,
                      delegation_code=actor.delegation_code, origen_pedido="B2B", estado_registro_exit="REGISTRADO",
                      exit_order_year=2026, exit_series="AL", exit_order_number=str(int(uuid4().hex[:8],16)),
                      notes="PRIVATE-NOTES", delivery_address="PRIVATE-ADDRESS", subtotal=100, total=121, tax_total=21,
                      attention_deadline_at=datetime(2026,11,5,12,tzinfo=timezone.utc))
        db.add(order);db.flush()
        order.nro_pedido_exit=f"2026/AL/{order.exit_order_number}"
        item = OrderItem(order_id=order.id, sku="TRACK-ARTICLE", description="Material de prueba", quantity=2, unit="MT", unit_price=50, tax_rate=21, line_total=100, served_quantity=0, pending_quantity=2, exit_line_number="1")
        db.add(item);db.flush()
        db.add(OrderLinePlanning(order_key=f"WEB:{order.public_id}", lines={str(item.id):{"sku":item.sku,"status":"PROVEEDOR","expected_at":"2026-11-05T12:00:00Z","observation":"PRIVATE-OBSERVATION"}}))
        db.commit()
        return order.public_id


def create(client, order_id):
    response = client.post(f"/api/v1/store/orders/{order_id}/tracking-link")
    assert response.status_code == 200, response.text
    result=response.json();assert result["path"].startswith("/seguimiento#token=")
    return result["path"].split("=",1)[1]


def read(token):
    return TestClient(app).post("/api/v1/order-tracking/read",json={"token":token})


def test_unlogged_tracking_is_read_only_minimal_and_hash_only():
    order_id=setup_order(); token=create(operator(),order_id)
    response=read(token);assert response.status_code==200,response.text
    data=response.json();assert data["state"]=="REGISTRADO" and data["items"][0]["situation"]=="PROVEEDOR"
    assert data["items"][0]["expected_at"]=="2026-11-05T12:00:00Z"
    assert "PRIVATE" not in response.text
    assert not ({"customer", "customer_code", "notes", "total", "subtotal", "documents", "delivery_address", "id"} & data.keys())
    assert not ({"unit_price", "line_total", "observation"} & data["items"][0].keys())
    assert response.headers["cache-control"]=="no-store, private"
    assert response.headers["referrer-policy"]=="no-referrer"
    with SessionLocal() as db:
        link=db.scalar(select(OrderTrackingLink).where(OrderTrackingLink.token_hash==hashlib.sha256(token.encode()).hexdigest()))
        assert link and link.token_hash != token
    assert TestClient(app).patch(f"/api/v1/store/orders/{order_id}/planning",json={}).status_code==401


def test_roles_and_scope_protect_link_creation():
    order_id=setup_order()
    assert TestClient(app).post(f"/api/v1/store/orders/{order_id}/tracking-link").status_code==401
    customer=TestClient(app);customer.post("/api/v1/auth/login",json={"email":"compras001@cliente.test","password":"123456"})
    assert customer.post(f"/api/v1/store/orders/{order_id}/tracking-link").status_code==403
    assert operator().post(f"/api/v1/store/orders/{setup_order(company=99999)}/tracking-link").status_code==404


def test_reissue_revocation_and_expiry_invalidate_secret():
    client=operator();order_id=setup_order();first=create(client,order_id);second=create(client,order_id)
    assert read(first).status_code==404 and read(second).status_code==200
    assert read("x"*43).status_code==404
    assert client.delete(f"/api/v1/store/orders/{order_id}/tracking-link").status_code==200
    assert read(second).status_code==404
    third=create(client,order_id)
    with SessionLocal() as db:
        link=db.scalar(select(OrderTrackingLink).where(OrderTrackingLink.token_hash==hashlib.sha256(third.encode()).hexdigest()))
        link.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
    assert read(third).status_code==404
    assert client.get(f"/api/v1/store/orders/{order_id}/tracking-link").json()["active"] is False


def test_token_is_bound_to_one_order_and_existing_token_is_not_revealed():
    client=operator();one=setup_order();two=setup_order();token=create(client,one)
    result=TestClient(app).post("/api/v1/order-tracking/read",json={"token":token,"order_id":two})
    with SessionLocal() as db:
        assert result.json()["web_number"]==db.scalar(select(Order).where(Order.public_id==one)).order_number
    status=client.get(f"/api/v1/store/orders/{one}/tracking-link").json()
    assert status["active"] and token not in str(status) and "path" not in status


def test_live_status_matches_all_four_keys_and_outage_retains_snapshot(monkeypatch):
    from app import order_tracking as module
    order_id=setup_order();token=create(operator(),order_id)
    with SessionLocal() as db:
        order=db.scalar(select(Order).where(Order.public_id==order_id))
        live=ExitOrderInput(exit_order_id=order.nro_pedido_exit,order_number=order.nro_pedido_exit,
                           customer_code=order.customer_code,store_code=order.delegation_code,company_code=order.company_code,
                           estado_registro_exit="ATENDIDO",source_updated_at=datetime.now(timezone.utc),lines=[])
        wrong=live.model_copy(update={"exit_order_id":live.exit_order_id.replace("/AL/","/OTHER/")})
    monkeypatch.setattr(module,"fetch_customer_exit_orders",lambda *a,**k:[wrong])
    assert read(token).json()["state"]=="REGISTRADO"
    monkeypatch.setattr(module,"fetch_customer_exit_orders",lambda *a,**k:[wrong,live])
    assert read(token).json()["state"]=="ATENDIDO"
    def unavailable(*a,**k):raise RuntimeError("SQL no disponible")
    monkeypatch.setattr(module,"fetch_customer_exit_orders",unavailable)
    data=read(token).json();assert data["state"]=="REGISTRADO" and data["warning"] and len(data["items"])==1
