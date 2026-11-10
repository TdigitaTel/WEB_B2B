from datetime import datetime, timezone
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app import main as module
from app import order_reconciliation
from app.db import SessionLocal
from app.models import Order, User
from app.bootstrap import main as bootstrap
bootstrap()


@pytest.fixture
def case(monkeypatch):
    code='HOME-'+uuid4().hex[:12]
    with SessionLocal() as db:
        seed=db.scalar(select(User).where(User.email=='compras001@cliente.test'))
        user=User(email=code+'@example.test',password_hash=seed.password_hash,full_name='Inicio WEB',role='CLIENTE_ADMIN',erp_customer_code=code,active=True)
        db.add(user);db.flush();uid=user.id
        for index in range(1,8):
            db.add(Order(order_number=f'WEB-{7000+uid}-{index:07d}',customer_code=code,user_id=uid,company_code=0,delegation_code='00',origen_pedido='B2B',estado_registro_exit={2:'FACTURADO',3:'ENTREGADO',6:'FACTURADO'}.get(index,'PENDIENTE'),exit_order_year=2026,exit_series=f'HW{uid}',exit_order_number=str(100-index),nro_pedido_exit=f'2026/HW{uid}/{100-index}',created_at=datetime(2020,1,index,tzinfo=timezone.utc),deleted_at=datetime.now(timezone.utc) if index==7 else None))
        # A newer store order with a WEB-looking reference is still not a WEB order.
        db.add(Order(order_number=f'WEB-{7000+uid}-9999999',customer_code=code,company_code=0,delegation_code='00',origen_pedido='EXIT',estado_registro_exit='PENDIENTE'))
        db.add(Order(order_number=f'WEB-{7000+uid}-9999998',customer_code='OTHER-'+code,company_code=0,delegation_code='00',origen_pedido='B2B',estado_registro_exit='PENDIENTE'))
        db.commit()
    calls=[];status_calls=[]
    monkeypatch.setattr(module,'fetch_customer_exit_orders',lambda *a,**k:calls.append((a,k)) or [])
    monkeypatch.setattr(module,'fetch_delivery_statuses_for_orders',lambda keys:status_calls.append(keys) or [])
    monkeypatch.setattr(module,'fetch_customer_delivery_statuses',lambda *a,**k:pytest.fail('Home must not query every customer delivery note'))
    monkeypatch.setattr(module,'fetch_customer_delivery_notes',lambda *a,**k:[])
    monkeypatch.setattr(order_reconciliation,'fetch_existing_exit_order_keys',lambda keys:set(keys))
    client=TestClient(module.app)
    assert client.post('/api/v1/auth/login',json={'email':code+'@example.test','password':'123456'}).status_code==200
    return client,code,uid,calls,status_calls


def test_five_web_orders_across_history_number_desc_all_states_and_scope(case):
    client,code,uid,calls,status_calls=case
    result=client.get('/api/v1/orders?recent_web=true&state=PENDIENTE')
    assert result.status_code==200,result.text
    rows=result.json()
    assert [row['web_number'] for row in rows]==[f'WEB-{7000+uid}-{i:07d}' for i in [6,5,4,3,2]]
    assert all(row['origen_pedido']=='B2B' and row['customer_code']==code for row in rows)
    assert any(row['estado_registro_exit']=='FACTURADO' for row in rows)
    assert {call[1]['order_number'] for call in calls}=={'94','95','96','97','98'}
    assert len(status_calls)==1 and len(status_calls[0])==5
    assert all(key[2]==f'HW{uid}' for key in status_calls[0])
    assert client.get('/api/v1/orders?recent_web=true&order_query=6007768').status_code==422


def test_own_order_restriction_is_preserved(case):
    client,code,uid,*_=case
    with SessionLocal() as db:
        user=db.get(User,uid);user.own_orders_only=True
        latest=db.scalar(select(Order).where(Order.customer_code==code,Order.order_number==f'WEB-{7000+uid}-0000006'))
        latest.user_id=None;db.commit()
    result=client.get('/api/v1/orders?recent_web=true').json()
    assert [row['web_number'] for row in result]==[f'WEB-{7000+uid}-{i:07d}' for i in [5,4,3,2,1]]


def test_empty_home_does_not_fetch_exit_or_fill_with_store_orders(case):
    client,code,uid,calls,status_calls=case
    with SessionLocal() as db:
        for order in db.scalars(select(Order).where(Order.customer_code==code,Order.origen_pedido=='B2B')):
            order.deleted_at=datetime.now(timezone.utc)
        db.commit()
    assert client.get('/api/v1/orders?recent_web=true').json()==[]
    assert calls==[] and status_calls==[]


def test_missing_exit_is_hidden_at_home_but_original_record_is_preserved(case,monkeypatch):
    client,code,uid,*_=case
    monkeypatch.setattr(order_reconciliation,'fetch_existing_exit_order_keys',lambda keys:set())
    rows=client.get('/api/v1/orders?recent_web=true').json()
    # Closed orders retain their history; confirmed missing pending orders are hidden.
    assert [row['web_number'] for row in rows]==[f'WEB-{7000+uid}-{i:07d}' for i in [6,3,2]]
    with SessionLocal() as db:
        order=db.scalar(select(Order).where(Order.customer_code==code,Order.order_number==f'WEB-{7000+uid}-0000005'))
        assert order.deleted_at is None and order.reconciliation_reason=='MISSING_EXIT'


def test_live_exit_update_keeps_web_number_and_never_imports_unlinked_order(case,monkeypatch):
    from app.exit_orders import ExitOrderInput
    client,code,uid,*_=case
    record=ExitOrderInput(exit_order_id=f'2026/HW{uid}/94',order_number=f'2026/HW{uid}/94',
        exit_company_code=0,exit_order_year=2026,exit_series=f'HW{uid}',exit_order_number='94',
        customer_code=code,company_code=0,store_code='00',estado_registro_exit='REGISTRADO',
        source_updated_at=datetime.now(timezone.utc),lines=[])
    other=record.model_copy(update={'company_code':99,'exit_company_code':99})
    monkeypatch.setattr(module,'fetch_customer_exit_orders',lambda *a,**k:[record,other] if k.get('order_number')=='94' else [])
    rows=client.get('/api/v1/orders?recent_web=true').json()
    assert [row['web_number'] for row in rows]==[f'WEB-{7000+uid}-{i:07d}' for i in [6,5,4,3,2]]
    assert rows[0]['number']==record.order_number
    assert rows[0]['estado_registro_exit']=='REGISTRADO'
    with SessionLocal() as db:
        assert not db.scalars(select(Order).where(Order.customer_code==code,Order.company_code==99)).all()


def test_failed_existence_check_does_not_hide_pending_home_orders(case,monkeypatch):
    client,code,uid,*_=case
    def unavailable(keys):raise RuntimeError('EXIT unavailable')
    monkeypatch.setattr(order_reconciliation,'fetch_existing_exit_order_keys',unavailable)
    rows=client.get('/api/v1/orders?recent_web=true').json()
    assert [row['web_number'] for row in rows]==[f'WEB-{7000+uid}-{i:07d}' for i in [6,5,4,3,2]]
    with SessionLocal() as db:
        assert all(row.reconciliation_reason is None for row in db.scalars(select(Order).where(Order.customer_code==code)))


def test_reappearing_exit_order_returns_to_home(case,monkeypatch):
    client,code,uid,*_=case
    monkeypatch.setattr(order_reconciliation,'fetch_existing_exit_order_keys',lambda keys:set())
    first=client.get('/api/v1/orders?recent_web=true').json()
    assert not any(row['web_number'].endswith('0000005') for row in first)
    monkeypatch.setattr(order_reconciliation,'fetch_existing_exit_order_keys',lambda keys:set(keys))
    restored=client.get('/api/v1/orders?recent_web=true').json()
    assert len(restored)==5 and any(row['web_number'].endswith('0000005') for row in restored)
