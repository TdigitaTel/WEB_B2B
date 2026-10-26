import pytest
pytestmark = pytest.mark.usefixtures("operator_with_almeiras_access")
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db import SessionLocal
from app.models import CustomerDeliverySetting, Order, User
from app.bootstrap import main as bootstrap
bootstrap()

import pytest

@pytest.fixture(autouse=True)
def delivery_customer_lookup(monkeypatch, exit_erp_stub):
    from app import main, customer_access
    monkeypatch.setattr(customer_access, "fetch_customer", main.fetch_customer)


def login(email):
    client=TestClient(app)
    assert client.post('/api/v1/auth/login',json={'email':email,'password':'123456'}).status_code==200
    return client


def setup_clients():
    customer=login('compras001@cliente.test')
    operator=login('operador@bermudez.test')
    code=customer.get('/api/v1/account').json()['customer']['erp_id']
    with SessionLocal() as db:
        setting=db.get(CustomerDeliverySetting,code)
        if setting: db.delete(setting);db.commit()
    return customer,operator,code


def test_default_pickup_operator_permission_and_persistence():
    customer,operator,code=setup_clients()
    path='/api/v1/store/customer-access/delivery'
    assert customer.get('/api/v1/cart').json()['delivery_enabled'] is False
    assert operator.get(path,params={'customer_code':code}).json()['delivery_enabled'] is False
    assert customer.post(path,json={'customer_code':code,'delivery_enabled':True}).status_code==403
    assert operator.post(path,json={'customer_code':code,'delivery_enabled':True}).status_code==200
    assert customer.get('/api/v1/cart').json()['delivery_enabled'] is True
    with SessionLocal() as db:
        assert db.get(CustomerDeliverySetting,code).delivery_enabled
    assert operator.post(path,json={'customer_code':code,'delivery_enabled':False}).status_code==200
    assert customer.get('/api/v1/cart').json()['delivery_enabled'] is False


def test_delivery_order_requires_permission_and_address(pickup_schedule):
    customer,operator,code=setup_clients()
    store=customer.get('/api/v1/stores').json()[0]
    product=customer.get('/api/v1/products?page_size=1').json()['items'][0]
    customer.post('/api/v1/cart/items',json={'product_id':product['id'],'quantity':1})
    day=(datetime.now(ZoneInfo('Europe/Madrid')).date()+timedelta(days=1)).isoformat()
    payload={'company_code':store['company_code'],'delegation_code':store['code'],'pickup_date':day,
             'fulfillment_method':'DELIVERY','delivery_address':'  Calle de prueba 12  '}
    assert customer.post('/api/v1/orders',json=payload).status_code==403
    operator.post('/api/v1/store/customer-access/delivery',json={'customer_code':code,'delivery_enabled':True})
    assert customer.post('/api/v1/orders',json={**payload,'delivery_address':'   '}).status_code==422
    response=customer.post('/api/v1/orders',json=payload)
    assert response.status_code==201,response.text
    row=response.json()
    assert row['fulfillment_method']=='DELIVERY' and row['delivery_address']=='Calle de prueba 12'
    assert row['attention_deadline_at'] and row['delivered_at'] is None
    visible=operator.get('/api/v1/store/orders',params={'view':'web','delegation':'TODAS'}).json()
    assert next(o for o in visible if o['id']==row['id'])['fulfillment_method']=='DELIVERY'
    with SessionLocal() as db:
        order=db.scalar(select(Order).where(Order.public_id==row['id']))
        assert order.fulfillment_method=='DELIVERY' and order.delivery_address=='Calle de prueba 12'


def test_revoked_delivery_blocks_draft_submission():
    customer,operator,code=setup_clients()
    store=customer.get('/api/v1/stores').json()[0]
    product=customer.get('/api/v1/products?page_size=1').json()['items'][0]
    customer.post('/api/v1/cart/items',json={'product_id':product['id'],'quantity':1})
    path='/api/v1/store/customer-access/delivery'
    operator.post(path,json={'customer_code':code,'delivery_enabled':True})
    response=customer.post('/api/v1/orders',json={'draft':True,'company_code':store['company_code'],
                       'delegation_code':store['code'],'fulfillment_method':'DELIVERY','delivery_address':'Calle 1'})
    assert response.status_code==201,response.text
    operator.post(path,json={'customer_code':code,'delivery_enabled':False})
    assert customer.post('/api/v1/orders/'+response.json()['id']+'/submit').status_code==403


def test_subuser_inherits_customer_delivery_setting():
    from app.auth import hash_password
    customer,operator,code=setup_clients()
    with SessionLocal() as db:
        parent=db.scalar(select(User).where(User.email=='compras001@cliente.test'))
        sub=User(email='delivery-child@example.test',password_hash=hash_password('123456'),full_name='Delivery subusuario',
                 role='CLIENTE',parent_user_id=parent.id,customer_id=parent.customer_id,erp_customer_code=code,active=True)
        db.add(sub);db.commit()
    child=login('delivery-child@example.test')
    assert child.get('/api/v1/cart').json()['delivery_enabled'] is False
    operator.post('/api/v1/store/customer-access/delivery',json={'customer_code':code,'delivery_enabled':True})
    assert child.get('/api/v1/cart').json()['delivery_enabled'] is True
