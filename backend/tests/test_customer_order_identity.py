from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import main as module
from app.db import SessionLocal
from app.models import Order, User
from app.exit_orders import ExitOrderInput, ExitOrderLineInput
from app.order_identity import linked_customer_order
from app.bootstrap import main as bootstrap
bootstrap()


def make_case(suffix, shadow=True):
    stamp = datetime.now(timezone.utc)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == 'compras001@cliente.test'))
        web = Order(order_number=f'WEB-LINK-{suffix}', customer_code='CLI00001', user_id=user.id,
                    company_code=0, delegation_code="00",
                    nro_pedido_exit=f'60083{suffix}', origen_pedido='B2B', estado_registro_exit='REGISTRADO',
                    subtotal=Decimal('3.68'), tax_total=Decimal('.77'), total=Decimal('4.45'), created_at=stamp)
        db.add(web)
        external = f'{stamp.year}/AL/{web.nro_pedido_exit}'
        if shadow:
            db.add(Order(order_number=f'EXIT-LINK-{suffix}', customer_code='CLI00001', user_id=user.id,
                         company_code=0, delegation_code="00",
                         nro_pedido_exit=external, origen_pedido='EXIT', estado_registro_exit='REGISTRADO',created_at=stamp))
        db.commit()
        record = ExitOrderInput(exit_order_id=external, order_number=f'EXIT-LINK-{suffix}',
            customer_code='CLI00001', company_code=0, store_code="00",
            estado_registro_exit='REGISTRADO', source_updated_at=stamp, recorded_at=stamp,
            subtotal=Decimal('1.84'),tax_total=Decimal('.39'),total=Decimal('2.23'),
            lines=[ExitOrderLineInput(sku='LINK-MATERIAL',description='Material EXIT',quantity=1,unit_price=Decimal('1.84'),line_total=Decimal('1.84'))])
        return web.public_id, record


def client():
    result = TestClient(module.app)
    assert result.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'}).status_code==200
    return result


@pytest.mark.parametrize('shadow', [False, True])
def test_customer_sees_one_web_order_with_live_exit_amounts(monkeypatch, shadow):
    oid, record = make_case('75' if shadow else '76', shadow)
    monkeypatch.setattr(module,'fetch_customer_exit_orders',lambda *args:[record])
    monkeypatch.setattr(module,'fetch_customer_delivery_statuses',lambda *args:[])
    customer = client()
    for _ in range(2):
        response=customer.get('/api/v1/orders?state=TODOS')
        assert response.status_code==200,response.text
        rows=[row for row in response.json() if row['nro_pedido_exit'] and row['nro_pedido_exit'].endswith(record.exit_order_id.split('/')[-1])]
        assert len(rows)==1
        row=rows[0]
        assert row['id']==oid and row['is_web_order'] and row['local_order']
        assert row['web_number'].startswith('WEB-LINK-')
        assert row['exit_number']==record.exit_order_id
        assert row['total']==2.23 and row['items'][0]['description']=='Material EXIT'
    with SessionLocal() as db:
        assert db.scalar(select(Order).where(Order.public_id==oid)).origen_pedido=='B2B'
        if shadow:
            assert db.scalar(select(Order).where(Order.nro_pedido_exit==record.exit_order_id)) is not None


def test_existing_projection_is_hidden_without_live_row(monkeypatch):
    oid,record=make_case('77')
    monkeypatch.setattr(module,'fetch_customer_exit_orders',lambda *args:[])
    monkeypatch.setattr(module,'fetch_customer_delivery_statuses',lambda *args:[])
    rows=client().get('/api/v1/orders?state=TODOS').json()
    rows=[row for row in rows if str(row['nro_pedido_exit'] or '').endswith('6008377')]
    assert len(rows)==1 and rows[0]['id']==oid


def test_link_respects_scope_year_series_and_ambiguity():
    from types import SimpleNamespace
    stamp=datetime(2026,10,29,tzinfo=timezone.utc)
    web=SimpleNamespace(id=1,customer_code='C',company_code=1,delegation_code='00',
        nro_pedido_exit='6008375',created_at=stamp,fecha_registro_exit=None,origen_pedido='B2B',order_number='WEB-X')
    record=SimpleNamespace(customer_code='C',company_code=1,store_code='00',exit_order_id='2026/AL/6008375',web_order_number=None,customer_reference=None)
    assert linked_customer_order([web],record,[record])[0] is web
    for field,value in [('customer_code','OTHER'),('company_code',2),('store_code','02'),('exit_order_id','2025/AL/6008375')]:
        other=SimpleNamespace(**{**vars(record),field:value})
        assert linked_customer_order([web],other,[other])[0] is None
    another=SimpleNamespace(**{**vars(record),'exit_order_id':'2026/OT/6008375'})
    assert linked_customer_order([web],record,[record,another])[0] is None
    web.nro_pedido_exit='2026/OT/6008375'
    assert linked_customer_order([web],record,[record])[0] is None
    web.nro_pedido_exit='2026~AL~6008375'
    assert linked_customer_order([web],record,[record])[0] is web
