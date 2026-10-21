"""Aislamiento de identidades, permisos y credenciales de las subcuentas."""
from datetime import datetime, timedelta
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.bootstrap import main as bootstrap
from app.main import app
from app.db import SessionLocal
from app.auth import hash_password
from app.models import User, Order
from app import main
from app.exit_orders import ExitOrderInput
from app.price_visibility import protect_payload

bootstrap()
PASSWORD = "principal-password-2026"
CHILD_PASSWORD = "subuser-personal-2026"
FLAGS = dict(can_view_prices=False, can_view_delivery_notes=False, can_view_invoices=False,
             can_manage_preferences=False, own_orders_only=True)


def principal():
    suffix = uuid4().hex[:12]
    with SessionLocal() as db:
        row = User(email=f"principal-{suffix}@example.test", full_name=f"Principal {suffix}",
                   password_hash=hash_password(PASSWORD), erp_customer_code=f"SUB-{suffix}", role="CLIENTE", active=True)
        db.add(row); db.commit()
        email, code, uid = row.email, row.erp_customer_code, row.id
    client = TestClient(app)
    assert client.post('/api/v1/auth/login', json={'email':email,'password':PASSWORD}).status_code == 200
    return client, code, uid


def child(parent, **flags):
    response = parent.post('/api/v1/account/subusers', json={'full_name':'Empleado de prueba',
                          'email':f'{uuid4().hex}@example.test', **FLAGS, **flags})
    assert response.status_code == 201, response.text
    row = response.json()
    client = TestClient(app)
    login = client.post('/api/v1/auth/login', json={'email':row['email'],'password':row['initial_password']})
    assert login.status_code == 200, login.text
    assert login.json()['user']['is_subuser'] and not login.json()['user']['can_manage_subusers']
    assert client.get('/api/v1/products').status_code == 403
    assert client.patch('/api/v1/account/password', json={'current_password':row['initial_password'], 'new_password':CHILD_PASSWORD}).status_code == 200
    return client, row


def test_management_is_principal_only_and_initial_secret_disappears():
    parent, code, uid = principal()
    sub, row = child(parent)
    other, _, _ = principal()
    assert sub.get('/api/v1/account/subusers').status_code == 403
    assert sub.post('/api/v1/account/subusers', json={'full_name':'No','email':'no@example.test'}).status_code == 403
    assert other.patch(f"/api/v1/account/subusers/{row['id']}", json={**FLAGS,'active':True}).status_code == 404
    assert parent.get('/api/v1/account/subusers').json()[0]['initial_password'] is None
    info = sub.get('/api/v1/account').json()
    assert info['customer']['erp_id'] == code
    assert info['user']['login_name'] == row['full_name']
    # A shared EXIT code identifies only the principal, never a child.
    assert TestClient(app).post('/api/v1/auth/login', json={'email':code,'password':CHILD_PASSWORD}).status_code == 401
    with SessionLocal() as db:
        saved = db.scalar(select(User).where(User.public_id == row['id']))
        assert saved.parent_user_id == uid and saved.erp_customer_code == code
        assert saved.initial_password_ciphertext is None


def test_permissions_prices_and_parent_disable(monkeypatch):
    parent, _, uid = principal()
    sub, row = child(parent)
    monkeypatch.setattr(main, 'fetch_customer_delivery_notes', lambda *args: [{'id':'note', 'number':'NOTE-1', 'total':12, 'subtotal':10, 'items':[{'unit_price':10, 'net_amount':10}]}])
    products = sub.get('/api/v1/products?page_size=2').json()
    assert products['total'] > 0 and products['items']
    assert all(p['customer_price'] is None and p['price_without_tax'] is None for p in products['items'])
    assert sub.get('/api/v1/invoices').status_code == 403
    assert sub.get('/api/v1/delivery-notes').status_code == 403
    assert sub.patch('/api/v1/account/preferences', json={'show_delivery_note_images':True,'show_order_images':True}).status_code == 403
    assert sub.get('/api/v1/documents/FACTURA/anything/file').status_code == 403
    assert parent.patch(f"/api/v1/account/subusers/{row['id']}", json={**FLAGS,'active':True,'can_view_delivery_notes':True}).status_code == 200
    assert sub.get('/api/v1/account').status_code == 401  # permissions revoke existing sessions
    assert sub.post('/api/v1/auth/login', json={'email':row['email'],'password':CHILD_PASSWORD}).status_code == 200
    notes = sub.get('/api/v1/delivery-notes')
    assert notes.status_code == 200 and notes.json()[0]['total'] is None
    assert notes.json()[0]['items'][0]['unit_price'] is None
    assert sub.get('/api/v1/documents/export?kind=ALBARAN').status_code == 403
    with SessionLocal() as db:
        db.get(User, uid).active = False; db.commit()
    assert sub.get('/api/v1/account').status_code == 401
    assert sub.post('/api/v1/auth/login', json={'email':row['email'],'password':CHILD_PASSWORD}).status_code == 401


def test_order_ownership_and_audit_snapshots(monkeypatch):
    parent, code, uid = principal()
    sub, row = child(parent)
    sibling, sibling_row = child(parent)
    def create(client):
        products = client.get('/api/v1/products?page_size=1').json()['items']
        assert client.post('/api/v1/cart/items', json={'product_id':products[0]['id'],'quantity':1}).status_code == 201
        store = client.get('/api/v1/stores').json()[0]
        result = client.post('/api/v1/orders', json={'company_code':store['company_code'],'delegation_code':store['code'],'draft':True})
        assert result.status_code == 201, result.text
        return result.json(), store
    order, store = create(sub)
    parent_order, _ = create(parent)
    assert order['total'] is None and order['items'][0]['unit_price'] is None
    assert order['customer_code'] == code and order['creator_user_name'] == row['full_name']
    assert order['principal_user_name'].startswith('Principal')
    for method, path in [('get',''),('post','/repeat'),('post','/submit'),('delete','')]:
        response = getattr(sub, method)(f"/api/v1/orders/{parent_order['id']}{path}")
        assert response.status_code == 404, response.text
        response = getattr(sibling, method)(f"/api/v1/orders/{order['id']}{path}")
        assert response.status_code == 404
    now = datetime.now()
    monkeypatch.setattr(main,'fetch_customer_exit_orders', lambda *args: [ExitOrderInput(
        exit_order_id='OTHER-EXIT',order_number='OTHER-EXIT',customer_code=code,store_code=store['code'],
        company_code=store['company_code'],estado_registro_exit='REGISTRADO',source_updated_at=now,recorded_at=now)])
    params = {'state':'TODOS','date_from':(now-timedelta(days=1)).date().isoformat(),'date_to':(now+timedelta(days=1)).date().isoformat()}
    listed = sub.get('/api/v1/orders', params=params)
    assert listed.status_code == 200, listed.text
    assert [o['id'] for o in listed.json()] == [order['id']]
    assert parent.get(f"/api/v1/orders/{order['id']}").status_code == 200
    with SessionLocal() as db:
        saved = db.scalar(select(Order).where(Order.public_id == order['id']))
        child_user = db.scalar(select(User).where(User.public_id == row['id']))
        assert saved.user_id == child_user.id and saved.principal_user_id == uid
        assert saved.total > 0 and saved.creator_user_name == row['full_name']
    # Permission can deliberately expose company-wide orders.
    assert parent.patch(f"/api/v1/account/subusers/{row['id']}", json={**FLAGS,'active':True,'own_orders_only':False}).status_code == 200
    sub.post('/api/v1/auth/login', json={'email':row['email'],'password':CHILD_PASSWORD})
    assert sub.get(f"/api/v1/orders/{parent_order['id']}").status_code == 200


def test_qr_is_per_user_and_password_reset_revokes_it():
    parent, _, uid = principal()
    sub, row = child(parent)
    result = parent.post(f"/api/v1/account/subusers/{row['id']}/qr", json={})
    assert result.status_code == 200, result.text
    token = result.json()['url'].split('qr=')[1]
    login = TestClient(app).post('/api/v1/auth/qr',json={'token':token})
    assert login.status_code == 200 and login.json()['user']['id'] == row['id']
    own = sub.post('/api/v1/account/qr',json={})
    assert own.status_code == 200 and own.json()['url'] == result.json()['url']
    reset = parent.post(f"/api/v1/account/subusers/{row['id']}/password",json={})
    assert reset.status_code == 200 and reset.json()['initial_password']
    assert sub.get('/api/v1/account').status_code == 401
    assert TestClient(app).post('/api/v1/auth/qr',json={'token':token}).status_code == 401
    assert TestClient(app).post('/api/v1/auth/login',json={'email':row['email'],'password':CHILD_PASSWORD}).status_code == 401
    assert TestClient(app).post('/api/v1/auth/login',json={'email':row['email'],'password':reset.json()['initial_password']}).status_code == 200


def test_document_filter_and_financial_redaction():
    value = {'items':[{'number':'WEB-1','total':12,'subtotal':10,'items':[{'unit_price':10,'line_total':10}],
                      'documents':[{'type':'ALBARAN','total':10,'available':True},{'type':'FACTURA','total':12,'available':True}]}], 'total':1, 'page':1}
    result = protect_payload(value, {'can_view_delivery_notes':True,'can_view_invoices':False}, True)
    assert result['total'] == 1
    order = result['items'][0]
    assert order['total'] is None and order['items'][0]['unit_price'] is None
    assert len(order['documents']) == 1 and order['documents'][0]['total'] is None
    assert order['documents'][0]['available'] is False
