from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.exit_orders import ExitOrderInput, ExitOrderLineInput, reconcile_exit_lines, upsert_exit_order
from app.main import app
from app.models import Order, OrderItem, OrderLinePlanning, User
from app.line_planning import local_context

bootstrap()
pytestmark = pytest.mark.usefixtures("operator_with_almeiras_access")


def setup_order(db, numbered=True):
    actor = db.scalar(select(User).where(User.email == "operador@bermudez.test"))
    customer = db.scalar(select(User).where(User.email == "compras001@cliente.test"))
    order = Order(order_number="WEB-PRESERVE-" + uuid4().hex, user_id=customer.id,
                  customer_code="CLI00001", company_code=actor.company_code,
                  delegation_code=actor.delegation_code, origen_pedido="B2B",
                  estado_registro_exit="REGISTRADO", nro_pedido_exit="2026/AL/" + str(int(uuid4().hex[:7], 16)),
                  subtotal=10, tax_total=2.1, total=12.1)
    db.add(order); db.flush()
    items = []
    for n in (1, 2):
        item = OrderItem(order_id=order.id, created_in_web=True, exit_line_number=str(n) if numbered else None,
                         sku="REPEATED", description="Original WEB", quantity=2,
                         unit="MT", unit_price=5, tax_rate=21, line_total=Decimal("12.10"),
                         served_quantity=0, pending_quantity=2)
        db.add(item); items.append(item)
    db.flush()
    return actor, order, items


def line(number):
    return ExitOrderLineInput(line_number=number, sku="REPEATED", description="EXIT changed text",
                              quantity=1, unit="PZ", unit_price=1, served_quantity=1, pending_quantity=0)


def record(order, lines):
    return ExitOrderInput(exit_order_id=order.nro_pedido_exit, order_number=order.nro_pedido_exit,
                          customer_code=order.customer_code, company_code=order.company_code,
                          store_code=order.delegation_code, estado_registro_exit="REGISTRADO",
                          source_updated_at=datetime.now(timezone.utc), lines=lines)


def test_import_keeps_original_lines_ids_planning_and_recovers():
    with SessionLocal() as db:
        actor, order, items = setup_order(db)
        ids = [item.id for item in items]
        plan = {str(items[0].id): {"sku": "REPEATED", "manual": True,
                                  "expected_at": "2026-11-10T10:00:00Z", "observation": "Acuerdo cliente"}}
        db.add(OrderLinePlanning(order_key=f"WEB:{order.public_id}", lines=plan))
        db.commit()
        upsert_exit_order(db, record(order, [line("2")]), actor); db.commit()
        rows = list(db.scalars(select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id)))
        assert [item.id for item in rows] == ids
        assert rows[0].exit_removed_at and rows[1].exit_removed_at is None
        stamp = rows[0].exit_removed_at
        assert rows[1].description == "Original WEB" and rows[1].quantity == 2
        assert rows[1].unit == "MT" and rows[1].unit_price == 5 and rows[1].line_total == Decimal("12.10")
        assert rows[1].served_quantity == 1
        assert db.get(OrderLinePlanning, f"WEB:{order.public_id}").lines == plan
        assert local_context(db, order)[4][0]["pending"] == 0
        upsert_exit_order(db, record(order, [line("2")]), actor); db.commit()
        assert db.get(OrderItem, ids[0]).exit_removed_at == stamp
        upsert_exit_order(db, record(order, [line("1"), line("2")]), actor); db.commit()
        assert db.get(OrderItem, ids[0]).exit_removed_at is None
        assert len(list(db.scalars(select(OrderItem).where(OrderItem.order_id == order.id)))) == 2


def test_empty_detail_retains_all_lines_and_omitted_detail_changes_nothing():
    with SessionLocal() as db:
        actor, order, items = setup_order(db)
        incoming = record(order, []).model_dump(exclude={"lines"})
        upsert_exit_order(db, ExitOrderInput(**incoming), actor); db.commit()
        assert all(item.exit_removed_at is None for item in items)
        upsert_exit_order(db, record(order, []), actor); db.commit()
        assert all(item.exit_removed_at for item in items)
        assert all(item.quantity == 2 and item.pending_quantity == 2 for item in items)


def test_legacy_duplicate_sku_is_not_arbitrarily_removed_or_duplicated():
    with SessionLocal() as db:
        _, order, items = setup_order(db, numbered=False)
        ids = [item.id for item in items]
        reconcile_exit_lines(db, order, [line("2")]); db.commit()
        rows = list(db.scalars(select(OrderItem).where(OrderItem.order_id == order.id)))
        assert [item.id for item in rows] == ids
        assert all(item.exit_removed_at is None and item.exit_line_number is None for item in rows)


def test_unique_legacy_line_is_linked_once_then_missing_is_retained():
    with SessionLocal() as db:
        _, order, items = setup_order(db, numbered=False)
        items[0].sku = "OTHER"; db.commit()
        reconcile_exit_lines(db, order, [line("2")]); db.commit()
        assert items[1].exit_line_number == "2" and items[1].exit_removed_at is None
        assert items[0].exit_removed_at
        new_line = ExitOrderLineInput(line_number="3", sku="ADDED", description="Nuevo en EXIT", quantity=3)
        reconcile_exit_lines(db, order, [line("2"), new_line]); db.commit()
        reconcile_exit_lines(db, order, [line("2"), new_line]); db.commit()
        assert len(list(db.scalars(select(OrderItem).where(OrderItem.order_id == order.id)))) == 3


def test_customer_operator_refresh_keep_removed_rows_and_failures_do_not_retire(monkeypatch):
    from app import main as module
    with SessionLocal() as db:
        _, order, items = setup_order(db)
        live = record(order, [line("2")]); public_id = order.public_id
        ids = [str(item.id) for item in items]
        db.commit()
    monkeypatch.setattr(module, "fetch_customer_exit_orders", lambda *a, **k: [live])
    customer = TestClient(app, raise_server_exceptions=False)
    assert customer.post("/api/v1/auth/login", json={"email":"compras001@cliente.test","password":"123456"}).status_code == 200
    response = customer.get("/api/v1/orders?state=TODOS")
    assert response.status_code == 200, response.text
    found = next(row for row in response.json() if row["id"] == public_id)
    assert [item["line_key"] for item in found["items"]] == ids
    assert found["items"][0]["exit_line_status"] == "ELIMINADA_EN_EXIT"
    assert found["items"][0]["quantity"] == 2 and found["items"][0]["description"] == "Original WEB"
    operator = TestClient(app)
    operator.post("/api/v1/auth/login", json={"email":"operador@bermudez.test","password":"123456"})
    response = operator.get("/api/v1/store/orders?view=web&delegation=TODAS&state=TODOS")
    assert response.status_code == 200, response.text
    found = next(row for row in response.json() if row["id"] == public_id)
    assert [item["line_key"] for item in found["items"]] == ids
    assert found["items"][0]["exit_removed_at"]
    assert found["items"][0]["created_in_web"] is True
    assert found["items"][0]["will_not_be_served"] is True
    assert found["items"][1]["entered_in_exit"] is True
    def unavailable(*a, **k):
        raise RuntimeError("EXIT no disponible")
    monkeypatch.setattr(module, "fetch_customer_exit_orders", unavailable)
    assert customer.get("/api/v1/orders?state=TODOS").status_code == 500
    assert operator.get("/api/v1/store/orders?view=web&delegation=TODAS&state=TODOS").status_code == 200
    with SessionLocal() as db:
        rows = [db.get(OrderItem, int(value)) for value in ids]
        assert rows[0].exit_removed_at and rows[1].exit_removed_at is None


def test_duplicate_exit_numbers_leave_original_detail_intact():
    with SessionLocal() as db:
        _, order, items = setup_order(db)
        with pytest.raises(ValueError, match="duplicados"):
            reconcile_exit_lines(db, order, [line("1"), line("1")])
        assert all(item.exit_removed_at is None and item.served_quantity == 0 for item in items)


def test_per_line_marks_are_confirmed_by_detail_and_remain_historical():
    from app.order_line_marks import line_marks
    with SessionLocal() as db:
        _, order, items = setup_order(db, numbered=False)
        items[0].sku = "OTHER"
        db.commit()
        assert line_marks(items[1]) == {"created_in_web": True, "entered_in_exit": False,
            "exit_entered_at": None, "removed_in_exit": False, "will_not_be_served": False}
        # A registered header is not proof that its materials were entered.
        new = ExitOrderLineInput(line_number="3", sku="EXIT-ONLY", description="Added in EXIT", quantity=1)
        reconcile_exit_lines(db, order, [line("2"), new]); db.commit()
        stamp = items[1].exit_entered_at
        assert stamp and line_marks(items[1])["entered_in_exit"]
        assert not line_marks(items[0])["entered_in_exit"]
        imported = db.scalar(select(OrderItem).where(OrderItem.order_id == order.id, OrderItem.sku == "EXIT-ONLY"))
        assert line_marks(imported)["created_in_web"] is False
        assert line_marks(imported)["entered_in_exit"] is True
        reconcile_exit_lines(db, order, []); db.commit()
        marks = line_marks(items[1])
        assert marks["created_in_web"] and marks["entered_in_exit"]
        assert marks["removed_in_exit"] and marks["will_not_be_served"]
        assert items[1].exit_entered_at == stamp
        reconcile_exit_lines(db, order, [line("2")]); db.commit()
        assert items[1].exit_entered_at == stamp
        assert not line_marks(items[1])["will_not_be_served"]
        assert not line_marks(items[1])["removed_in_exit"]
        assert line_marks(imported)["created_in_web"] is False

def test_legacy_origin_is_unknown_and_ambiguous_matches_do_not_confirm_entry():
    from app.order_line_marks import line_marks
    with SessionLocal() as db:
        _, order, items = setup_order(db, numbered=False)
        items[0].created_in_web = None
        reconcile_exit_lines(db, order, [line("2")]); db.commit()
        assert line_marks(items[0])["created_in_web"] is None
        assert all(not line_marks(item)["entered_in_exit"] for item in items)
