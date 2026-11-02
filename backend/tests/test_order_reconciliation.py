from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.models import Order, AuditEvent, User
from app import order_reconciliation as module
from app import main as main_module
from app.main import app
bootstrap()

def row(db, number, origin='EXIT', company=0, reference=None, state='REGISTRADO'):
    value=Order(order_number=uuid4().hex,customer_code='CLI00001',company_code=company,delegation_code='00',
                nro_pedido_exit=reference or f'2026/AL/{number}',origen_pedido=origin,estado_registro_exit=state,
                created_at=datetime.now(timezone.utc),subtotal=0,tax_total=0,total=0)
    db.add(value);db.flush();return value

def test_missing_exact_and_duplicates_are_retired_but_web_is_retained(monkeypatch):
    existing={(0,2026,'AL','6008552'),(1,2026,'AL','6008552'),(0,2026,'OTHER','6008552'),(0,2025,'AL','6008552')}
    queried=[]
    monkeypatch.setattr(module,'fetch_existing_exit_order_keys',lambda keys:queried.extend(keys) or existing.intersection(keys))
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email=='compras001@cliente.test'))
        web=row(db,'6008552','B2B');shadow=row(db,'6008552');missing=row(db,'6008550');other_company=row(db,'6008552',company=1)
        other_year=row(db,'6008552',reference='2025/AL/6008552');other_series=row(db,'6008552',reference='2026/OTHER/6008552');pending=row(db,'',origin='B2B',reference='6008')
        rows=[web,shadow,missing,other_company,other_series,other_year,pending]
        hidden=module.reconcile_orders(db,rows,rows,[],[],user);db.commit()
        assert hidden=={shadow.public_id,missing.public_id}
        assert web.reconciliation_reason is None and shadow.reconciliation_reason=='DUPLICATE_EXIT'
        assert missing.reconciliation_reason=='MISSING_EXIT' and db.get(Order,missing.id) is not None
        assert pending.reconciliation_hidden_at is None
        assert (0,2026,'AL','6008550') in queried and len(queried)==5
        count=len(db.scalars(select(AuditEvent).where(AuditEvent.action=='ORDER_RECONCILED')).all())
        module.reconcile_orders(db,rows,rows,[],[],user);db.commit()
        assert len(db.scalars(select(AuditEvent).where(AuditEvent.action=='ORDER_RECONCILED')).all())==count
        existing.add((0,2026,'AL','6008550'))
        module.reconcile_orders(db,rows,rows,[],[],user);db.commit()
        assert missing.reconciliation_hidden_at is None and missing.reconciliation_reason is None
        assert shadow.reconciliation_reason=='DUPLICATE_EXIT'


def test_outage_delivery_and_complete_order_do_not_become_deleted(monkeypatch):
    def unavailable(keys):raise RuntimeError('EXIT no disponible')
    monkeypatch.setattr(module,'fetch_existing_exit_order_keys',unavailable)
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email=='compras001@cliente.test'));value=row(db,'FAIL')
        assert not module.reconcile_orders(db,[value],[value],[],[],user)
        assert value.reconciliation_hidden_at is None
        monkeypatch.setattr(module,'fetch_existing_exit_order_keys',lambda keys:set())
        assert not module.reconcile_orders(db,[value],[value],[],[],user,notes_available=False)
        assert not module.reconcile_orders(db,[value],[value],[],[(0,2026,'AL','FAIL')],user)
        value.estado_registro_exit='ATENDIDO'
        assert not module.reconcile_orders(db,[value],[value],[],[],user)
        value.estado_registro_exit='REGISTRADO';value.delivered_at=datetime.now(timezone.utc)
        assert not module.reconcile_orders(db,[value],[value],[],[],user)


def test_home_api_removes_confirmed_missing_not_records_outside_live_date_range(monkeypatch):
    monkeypatch.setattr(main_module,'fetch_customer_exit_orders',lambda *a,**kw:[])
    monkeypatch.setattr(main_module,'fetch_customer_delivery_statuses',lambda *a:[])
    existing=set();observed=[]
    monkeypatch.setattr(module,'fetch_existing_exit_order_keys',lambda keys:observed.extend(keys) or existing.intersection(keys))
    with SessionLocal() as db:
        missing=row(db,'API-MISSING');outside_range=row(db,'API-PRESENT');unlinked=row(db,'','B2B',reference='123')
        missing_id=missing.public_id;present_id=outside_range.public_id;pending_id=unlinked.public_id
        existing.add((0,2026,'AL','API-PRESENT'));db.commit()
    client=TestClient(app);assert client.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'}).status_code==200
    response=client.get('/api/v1/orders?state=TODOS');assert response.status_code==200,response.text
    ids={value['id'] for value in response.json()}
    assert missing_id not in ids and present_id in ids and pending_id in ids
    with SessionLocal() as db:
        missing=db.scalar(select(Order).where(Order.public_id==missing_id));assert missing.reconciliation_reason=='MISSING_EXIT'
    assert (0,2026,'AL','API-PRESENT') in observed


def test_sql_query_uses_all_four_fields_and_bounded_batches(monkeypatch):
    from app import exit_db
    executed=[]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params):executed.append((sql,params))
        def fetchall(self):return [{'company':0,'year':2026,'series':'AL','number':'6008552'}] if len(executed)==1 else []
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def cursor(self):return Cursor()
    monkeypatch.setattr(exit_db,'connect_sqlserver',lambda:Connection())
    monkeypatch.setattr(exit_db,'_columns',lambda *a:{'company':'CodigoEmpresa','year':'EjercicioPedido','series':'SeriePedido','number':'NumeroPedido'})
    keys=[(0,2026,'AL',str(6008552+i)) for i in range(401)]
    assert exit_db.fetch_existing_exit_order_keys(keys)=={keys[0]}
    assert len(executed)==3 and max(len(params) for _,params in executed)==800
    for sql,params in executed:
        assert 'CodigoEmpresa' in sql and 'EjercicioPedido' in sql and 'SeriePedido' in sql and 'NumeroPedido' in sql
        assert 'BETWEEN' not in sql and 'TOP ' not in sql and 'StatusPedido' not in sql and 'FechaGrabacion' not in sql
        assert sql.count('%s')==len(params)


@pytest.mark.usefixtures('operator_with_almeiras_access')
def test_operator_web_board_uses_same_reconciliation(monkeypatch):
    monkeypatch.setattr(main_module,'fetch_customer_exit_orders',lambda *a,**kw:[])
    monkeypatch.setattr(main_module,'fetch_customer_delivery_statuses',lambda *a:[])
    monkeypatch.setattr(main_module,'fetch_delivery_statuses_for_orders',lambda *a:[])
    monkeypatch.setattr(module,'fetch_existing_exit_order_keys',lambda keys:set())
    with SessionLocal() as db:
        op=db.scalar(select(User).where(User.role=='OPERADOR_TIENDA'))
        missing=row(db,'OP-MISSING','B2B',company=op.company_code);missing.delegation_code=op.delegation_code
        pending=row(db,'','B2B',company=op.company_code,reference='OP-SHORT');pending.delegation_code=op.delegation_code
        ids=missing.public_id,pending.public_id;db.commit()
    client=TestClient(app);assert client.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'}).status_code==200
    response=client.get('/api/v1/store/orders?view=web&state=TODOS&delegation=TODAS');assert response.status_code==200,response.text
    result={value['id'] for value in response.json()}
    assert ids[0] not in result and ids[1] in result
