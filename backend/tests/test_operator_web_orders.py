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
            db.add(Order(order_number=number, customer_code="CLI00001", company_code=user.company_code, delegation_code=user.delegation_code, origen_pedido="B2B", estado_registro_exit="REGISTRADO" if exit_number else "PENDIENTE", nro_pedido_exit=exit_number, subtotal=0, tax_total=0, total=0))
        db.add(Order(order_number="EXIT-NON-WEB-TEST", customer_code="CLI00001", company_code=user.company_code, delegation_code=user.delegation_code, origen_pedido="EXIT", estado_registro_exit="REGISTRADO", subtotal=0, tax_total=0, total=0))
        db.add(Order(order_number="WEB-BOARD-DRAFT", customer_code="CLI00001", company_code=user.company_code, delegation_code=user.delegation_code, origen_pedido="B2B", estado_registro_exit="BORRADOR", subtotal=0, tax_total=0, total=0))
        db.commit()
        record = ExitOrderInput(exit_order_id="2026/AL/987", order_number="987", customer_code="CLI00001", store_code=user.delegation_code, company_code=user.company_code, estado_registro_exit="REGISTRADO", source_updated_at=stamp, recorded_at=stamp, customer_reference="WEB-BOARD-LINKED", auxiliary_reference="PEDIDO GENERADO WEB B2B", lines=[])
        monkeypatch.setattr(module, "fetch_exit_orders_live", lambda *args: [record])
        monkeypatch.setattr(module, "fetch_customer_exit_orders", lambda *args: [record])
        monkeypatch.setattr(module, "fetch_kardex_timings", lambda *args: {})
        all_rows = store_orders(view="web", state="TODOS", user=user, db=db, delegation="TODAS")
        assert sum(row["nro_pedido_exit"] == "2026/AL/987" for row in all_rows) == 1
        assert any(row["number"] == "WEB-BOARD-PENDING" for row in all_rows)
        assert all(row["origen_pedido"] == "B2B" for row in all_rows)
        assert any(row["number"] == "WEB-BOARD-DRAFT" for row in all_rows)
        drafts = store_orders(view="web", state="BORRADOR", user=user, db=db, delegation="TODAS")
        assert drafts and all(row["estado_registro_exit"] == "BORRADOR" for row in drafts)
        pending = store_orders(view="web", state="PENDIENTE", user=user, db=db, delegation="TODAS")
        assert any(row["number"] == "WEB-BOARD-PENDING" for row in pending)
        assert not any(row["nro_pedido_exit"] for row in pending)
        registered = store_orders(view="web", state="REGISTRADO", user=user, db=db, delegation="TODAS")
        assert any(row["nro_pedido_exit"] == "2026/AL/987" for row in registered)
        assert all(row["estado_registro_exit"] == "REGISTRADO" for row in registered)
        monkeypatch.setattr(module, "fetch_exit_orders_live", lambda *args: [])
        fallback = store_orders(view="web", state="TODOS", user=user, db=db, delegation="TODAS")
        assert any(row["number"] == "WEB-BOARD-LINKED" for row in fallback)
        def unavailable(*args):
            raise RuntimeError("EXIT no disponible")
        monkeypatch.setattr(module, "fetch_exit_orders_live", unavailable)
        assert any(row["number"] == "WEB-BOARD-PENDING" for row in store_orders(view="web", state="TODOS", user=user, db=db, delegation="TODAS"))


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


def test_web_date_filters_bind_postgresql_dates():
    from datetime import date
    from types import SimpleNamespace
    from sqlalchemy import Date
    from sqlalchemy.dialects import postgresql
    from app.main import web_store_orders

    class ReadSession:
        statement = None
        def scalars(self, statement):
            self.statement = statement
            return self
        def all(self):
            return []

    db = ReadSession()
    start, end = date(2026, 9, 13), date(2026, 10, 13)
    assert web_store_orders(db, SimpleNamespace(role="ADMIN"), start, end, "TODOS", "TODAS") == []
    compiled = db.statement.compile(dialect=postgresql.dialect())
    date_binds = [bind for bind in compiled.binds.values() if isinstance(bind.value, date)]
    assert {bind.value for bind in date_binds} == {start, end}
    assert all(isinstance(bind.type, Date) for bind in date_binds)


def test_operator_can_read_other_delegations_and_default_is_almeiras(monkeypatch):
    from app import main as module
    from app.main import web_store_orders
    bootstrap()
    monkeypatch.setattr(module, "fetch_customer_exit_orders", lambda *args: [])
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "operador@bermudez.test"))
        for code in ("00", "01"):
            db.add(Order(order_number=f"WEB-DELEGATION-{code}", customer_code="CLI00001", company_code=user.company_code, delegation_code=code, origen_pedido="B2B", estado_registro_exit="PENDIENTE", subtotal=0, tax_total=0, total=0))
        db.commit()
        default = web_store_orders(db, user, None, None, "TODOS")
        assert default and all(row["delegation_code"] == "00" for row in default)
        assert any(row["number"] == "WEB-DELEGATION-00" for row in default)
        all_rows = web_store_orders(db, user, None, None, "TODOS", "TODAS")
        assert {"WEB-DELEGATION-00", "WEB-DELEGATION-01"}.issubset({row["number"] for row in all_rows})
        coruna = web_store_orders(db, user, None, None, "TODOS", "01")
        assert coruna and all(row["delegation_code"] == "01" for row in coruna)
