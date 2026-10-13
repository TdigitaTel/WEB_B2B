from datetime import datetime, timezone
from sqlalchemy import select
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.models import Order, User
from app.main import store_orders
from app.exit_orders import ExitOrderInput


def test_pending_registered_and_deduplication(monkeypatch):
    from app import main as module
    bootstrap()
    stamp = datetime.now(timezone.utc)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.role == "OPERADOR_TIENDA"))
        for number, exit_number in [("WEB-BOARD-PENDING", None), ("WEB-BOARD-LINKED", "2026/AL/987")]:
            db.add(Order(order_number=number, customer_code="CLI00001", company_code=user.company_code, delegation_code=user.delegation_code, origen_pedido="B2B", estado_registro_exit="PENDIENTE", nro_pedido_exit=exit_number, subtotal=0, tax_total=0, total=0))
        db.commit()
        record = ExitOrderInput(exit_order_id="2026/AL/987", order_number="987", customer_code="CLI00001", store_code=user.delegation_code, company_code=user.company_code, estado_registro_exit="REGISTRADO", source_updated_at=stamp, recorded_at=stamp, customer_reference="WEB-BOARD-LINKED", auxiliary_reference="PEDIDO GENERADO WEB B2B", lines=[])
        monkeypatch.setattr(module, "fetch_exit_orders_live", lambda *args: [record])
        monkeypatch.setattr(module, "fetch_kardex_timings", lambda *args: {})
        all_rows = store_orders(view="web", state="TODOS", user=user, db=db)
        assert sum(row["nro_pedido_exit"] == "2026/AL/987" for row in all_rows) == 1
        assert any(row["number"] == "WEB-BOARD-PENDING" for row in all_rows)
        pending = store_orders(view="web", state="PENDIENTE", user=user, db=db)
        assert any(row["number"] == "WEB-BOARD-PENDING" for row in pending)
        assert not any(row["nro_pedido_exit"] for row in pending)
        registered = store_orders(view="web", state="REGISTRADO", user=user, db=db)
        assert any(row["nro_pedido_exit"] == "2026/AL/987" for row in registered)
        assert all(row["nro_pedido_exit"] for row in registered)
        monkeypatch.setattr(module, "fetch_exit_orders_live", lambda *args: [])
        fallback = store_orders(view="web", state="TODOS", user=user, db=db)
        assert any(row["number"] == "WEB-BOARD-LINKED" for row in fallback)
        def unavailable(*args):
            raise RuntimeError("EXIT no disponible")
        monkeypatch.setattr(module, "fetch_exit_orders_live", unavailable)
        assert any(row["number"] == "WEB-BOARD-PENDING" for row in store_orders(view="web", state="TODOS", user=user, db=db))


def test_retry_pending_order_permissions_and_registration(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models import IntegrationOutbox, SyncStatus
    from app import main as module
    bootstrap()
    operator = TestClient(app)
    operator.post('/api/v1/auth/login', json={'email':'operador@bermudez.test','password':'123456'})
    customer = TestClient(app)
    customer.post('/api/v1/auth/login', json={'email':'compras001@cliente.test','password':'123456'})
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email=='operador@bermudez.test'))
        order = Order(order_number='WEB-RETRY-TEST', customer_code='CLI00001', company_code=user.company_code, delegation_code=user.delegation_code, origen_pedido='B2B', estado_registro_exit='EN_PROCESO', sync_status=SyncStatus.error, subtotal=0, tax_total=0, total=0)
        db.add(order); db.commit(); public_id=order.public_id
    url=f'/api/v1/store/orders/{public_id}/retry'
    assert customer.post(url).status_code == 403
    monkeypatch.setattr(module,'fetch_exit_orders_live',lambda *args, **kwargs: [])
    assert operator.post(url).status_code == 200
    assert operator.post(url).status_code == 200
    with SessionLocal() as db:
        order=db.scalar(select(Order).where(Order.public_id==public_id))
        assert order.estado_registro_exit=='PENDIENTE' and order.sync_status==SyncStatus.pending
        assert len(db.scalars(select(IntegrationOutbox).where(IntegrationOutbox.aggregate_id==public_id)).all())==1
        order.nro_pedido_exit='2026/AL/123';db.commit()
    assert operator.post(url).status_code==409
