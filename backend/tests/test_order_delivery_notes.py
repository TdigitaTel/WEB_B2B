from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app.main import app, delivery_notes_payload
from app.db import SessionLocal
from app.models import Order
from app.bootstrap import main as bootstrap
bootstrap()


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


def test_customer_order_shows_linked_notes_and_original_exit_amounts(monkeypatch):
    from app import main as module
    from app.exit_orders import ExitOrderInput, ExitOrderLineInput
    stamp=datetime.now(timezone.utc)
    from sqlalchemy import select
    from app.models import User
    with SessionLocal() as db:
        actor=db.scalar(select(User).where(User.email=='operador@bermudez.test'))
        store_code,company=actor.delegation_code,actor.company_code
    record=ExitOrderInput(exit_order_id='2026/AL/AMOUNTS',order_number='AMOUNTS',customer_code='CLI00001',store_code=store_code,company_code=company,
        estado_registro_exit='REGISTRADO',source_updated_at=stamp,recorded_at=stamp,
        lines=[ExitOrderLineInput(sku='PRICE-TEST',description='Material',quantity=1,unit_price=100,discount_pct=100,net_amount=0,line_total=0)])
    monkeypatch.setattr(module,'fetch_customer_exit_orders',lambda *args:[record])
    rows=[{'order_number':record.exit_order_id,'delivery_number':'2026/AL/NOTE1','attended_at':stamp,'is_printed':False,'is_invoiced':False},
          {'order_number':'2026/AL/OTHER','delivery_number':'2026/AL/OTHERNOTE','attended_at':stamp,'is_printed':False,'is_invoiced':False}]
    monkeypatch.setattr(module,'fetch_customer_delivery_statuses',lambda *args:rows)
    client=TestClient(app)
    client.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'})
    response=client.get('/api/v1/orders?state=TODOS')
    assert response.status_code==200,response.text
    order=next(row for row in response.json() if row['exit_number']==record.exit_order_id)
    assert [note['number'] for note in order['delivery_notes']]==['2026/AL/NOTE1']
    item=order['items'][0]
    assert item['unit_price']==100 and item['discount_pct']==100
    assert item['net_amount']==0 and item['line_total']==0


def test_operator_resolves_short_exit_number_and_opens_only_linked_note(monkeypatch):
    from app import main as module
    operator=TestClient(app)
    operator.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'})
    with SessionLocal() as db:
        order=Order(order_number='WEB-SHORT-NOTE',customer_code='CLI00001',company_code=0,delegation_code='00',
                    origen_pedido='B2B',estado_registro_exit='ATENDIDO',nro_pedido_exit='6007768')
        db.add(order);db.commit();oid=order.public_id
    stamp=datetime.now(timezone.utc)
    note={'order_number':'2026/AL/6007768','delivery_number':'2026/AL/9100','attended_at':stamp,'is_printed':True,'is_invoiced':False}
    monkeypatch.setattr(module,'fetch_delivery_statuses_for_orders',lambda *args:[])
    monkeypatch.setattr(module,'fetch_customer_delivery_statuses',lambda code:[note] if code=='CLI00001' else [])
    rows=operator.get('/api/v1/store/orders?view=web&delegation=TODAS').json()
    row=next(row for row in rows if row['id']==oid)
    assert [item['number'] for item in row['delivery_notes']]==['2026/AL/9100']
    document={'number':'2026/AL/9100','order_number':'2026/AL/6007768','items':[]}
    def documents(code,*args):
        assert code=='CLI00001'
        return [document]
    monkeypatch.setattr(module,'fetch_customer_delivery_notes',documents)
    url=f'/api/v1/store/orders/{oid}/delivery-note'
    assert operator.get(url,params={'number':'2026/AL/9100'}).json()['number']=='2026/AL/9100'
    document['order_number']='2025/AL/6007768'
    assert operator.get(url,params={'number':'2026/AL/9100'}).status_code==404
    document['order_number']='2026/AL/9999'
    assert operator.get(url,params={'number':'2026/AL/9100'}).status_code==404
    customer=TestClient(app)
    customer.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'})
    assert customer.get(url,params={'number':'2026/AL/9100'}).status_code==403
