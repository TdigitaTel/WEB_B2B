from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app.main import app, delivery_notes_payload
from app.db import SessionLocal
from app.models import Order


def test_notes_include_all_numbers_dates_and_status_without_duplicates():
    stamp=datetime(2026,10,22,9,15,tzinfo=timezone.utc)
    rows=[{'delivery_number':'2026/AL/1','attended_at':stamp,'is_printed':False,'is_invoiced':False},
          {'delivery_number':'2026/AL/2','attended_at':stamp,'is_printed':True,'is_invoiced':False},
          {'delivery_number':'2026/AL/3','attended_at':None,'is_printed':True,'is_invoiced':True}]
    result=delivery_notes_payload(rows+[rows[0]])
    assert len(result)==3
    assert [row['status'] for row in result]==['PENDIENTE_IMPRESION','IMPRESO','FACTURADO']
    assert result[0]['created_at'].astimezone(timezone.utc)==stamp
    assert result[2]['created_at'] is None


def test_operator_sees_only_notes_linked_to_selected_web_order(monkeypatch):
    from app import main as module
    operator=TestClient(app)
    operator.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'})
    with SessionLocal() as db:
        order=Order(order_number='WEB-MULTIPLE-NOTES',customer_code='CLI00001',company_code=0,delegation_code='00',
                    origen_pedido='B2B',estado_registro_exit='REGISTRADO',nro_pedido_exit='2026/AL/MULTI')
        db.add(order);db.commit();oid=order.public_id
    stamp=datetime(2026,10,22,9,15,tzinfo=timezone.utc)
    notes=[{'order_number':'2026/AL/MULTI','delivery_number':'2026/AL/101','attended_at':stamp,'is_printed':True,'is_invoiced':False},
           {'order_number':'2026/AL/MULTI','delivery_number':'2026/AL/102','attended_at':stamp,'is_printed':False,'is_invoiced':False},
           {'order_number':'2026/AL/OTHER','delivery_number':'2026/AL/999','attended_at':stamp,'is_printed':True,'is_invoiced':True}]
    monkeypatch.setattr(module,'fetch_delivery_statuses_for_orders',lambda *args:notes)
    rows=operator.get('/api/v1/store/orders?view=web&delegation=TODAS').json()
    row=next(row for row in rows if row['id']==oid)
    assert [note['number'] for note in row['delivery_notes']]==['2026/AL/101','2026/AL/102']
    assert row['delivered_at'] is None
    monkeypatch.setattr(module,'fetch_delivery_statuses_for_orders',lambda *args: (_ for _ in ()).throw(RuntimeError('unavailable')))
    rows=operator.get('/api/v1/store/orders?view=web&delegation=TODAS').json()
    assert next(row for row in rows if row['id']==oid)['delivery_notes'] is None
