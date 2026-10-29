import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db import SessionLocal
from app.models import CustomerCatalogSetting, User, OperatorAccess
from app.bootstrap import main as bootstrap
from app.auth import hash_password

bootstrap()
PATH='/api/v1/store/customer-access/catalog-price'


def login(email):
    client=TestClient(app)
    assert client.post('/api/v1/auth/login',json={'email':email,'password':'123456'}).status_code==200
    return client


@pytest.fixture
def clients(monkeypatch,exit_erp_stub,classified_catalog):
    from app import main
    monkeypatch.setattr('app.customer_access.fetch_customer',main.fetch_customer)
    customer=login('compras001@cliente.test');operator=login('operador@bermudez.test')
    code=customer.get('/api/v1/account').json()['customer']['erp_id']
    yield customer,operator,code
    with SessionLocal() as db:
        for key in [code,'OTHER-PRICE-CUSTOMER']:
            row=db.get(CustomerCatalogSetting,key)
            if row:db.delete(row)
        db.commit()


def test_default_persistence_and_price_values_unchanged(clients):
    customer,operator,code=clients
    assert operator.get(PATH,params={'customer_code':code}).json()['highlight_price_without_tax'] is False
    before=customer.get('/api/v1/products?page_size=1').json()['items'][0]
    assert before['highlight_price_without_tax'] is False
    response=operator.post(PATH,json={'customer_code':' '+code+' ','highlight_price_without_tax':True})
    assert response.status_code==200 and response.json()['customer_code']==code
    with SessionLocal() as db:assert db.get(CustomerCatalogSetting,code).highlight_price_without_tax is True
    after=customer.get('/api/v1/products?page_size=1').json()['items'][0]
    assert after['highlight_price_without_tax'] is True
    assert after['price_with_tax']==before['price_with_tax'] and after['price_without_tax']==before['price_without_tax']
    detail=customer.get('/api/v1/products/'+after['id']).json()
    assert detail['highlight_price_without_tax'] is True
    assert operator.post(PATH,json={'customer_code':code,'highlight_price_without_tax':False}).status_code==200
    assert customer.get('/api/v1/products?page_size=1').json()['items'][0]['highlight_price_without_tax'] is False


def test_permissions_and_invalid_input(clients,monkeypatch):
    customer,operator,code=clients
    assert TestClient(app).get(PATH,params={'customer_code':code}).status_code==401
    assert customer.get(PATH,params={'customer_code':code}).status_code==403
    assert customer.post(PATH,json={'customer_code':code,'highlight_price_without_tax':True}).status_code==403
    assert operator.post(PATH,json={'customer_code':code,'highlight_price_without_tax':'false'}).status_code==422
    assert operator.post(PATH,json={'customer_code':' ','highlight_price_without_tax':True}).status_code==422
    monkeypatch.setattr('app.customer_access.fetch_customer',lambda code:None)
    assert operator.post(PATH,json={'customer_code':'UNKNOWN','highlight_price_without_tax':True}).status_code==404
    with SessionLocal() as db:assert db.get(CustomerCatalogSetting,'UNKNOWN') is None


def test_customer_setting_is_shared_with_subusers_and_isolated(clients):
    customer,operator,code=clients
    with SessionLocal() as db:
        parent=db.scalar(select(User).where(User.email=='compras001@cliente.test'))
        sub=User(email='price-child@example.test',full_name='Precio subusuario',password_hash=hash_password('123456'),role='CLIENTE',parent_user_id=parent.id,customer_id=parent.customer_id,erp_customer_code=code,active=True)
        db.add(sub);db.commit();pk=sub.id
    try:
        child=login('price-child@example.test')
        operator.post(PATH,json={'customer_code':code,'highlight_price_without_tax':True})
        assert child.get('/api/v1/products?page_size=1').json()['items'][0]['highlight_price_without_tax'] is True
        operator.post(PATH,json={'customer_code':'OTHER-PRICE-CUSTOMER','highlight_price_without_tax':False})
        assert customer.get('/api/v1/products?page_size=1').json()['items'][0]['highlight_price_without_tax'] is True
        with SessionLocal() as db:
            db.get(User,pk).can_view_prices=False;db.commit()
        protected=child.get('/api/v1/products?page_size=1').json()['items'][0]
        assert protected['price_with_tax'] is None and protected['price_without_tax'] is None
        assert protected['highlight_price_without_tax'] is True
    finally:
        from app.models import AuthSession
        from sqlalchemy import delete
        with SessionLocal() as db:
            db.execute(delete(AuthSession).where(AuthSession.user_id==pk));db.delete(db.get(User,pk));db.commit()


def test_suggestions_use_highlighted_amount_and_label(clients):
    customer,operator,code=clients
    product=customer.get('/api/v1/products?page_size=1').json()['items'][0]
    def suggestion():return next(item for item in customer.get('/api/v1/search/suggestions',params={'q':product['sku']}).json() if item['sku']==product['sku'])
    before=suggestion()
    assert before['price_includes_tax'] is True and before['price']==product['price_with_tax']
    operator.post(PATH,json={'customer_code':code,'highlight_price_without_tax':True})
    after=suggestion()
    assert after['price_includes_tax'] is False and after['price']==product['price_without_tax']


def test_operator_needs_customer_management_permission(clients):
    customer,operator,code=clients
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email=='operador@bermudez.test'));pk=user.id
        saved=db.get(OperatorAccess,pk);old=dict(saved.permissions) if saved else None
        if not saved:saved=OperatorAccess(user_id=pk,exit_code='PRICE-PERMISSION');db.add(saved)
        saved.permissions={'customers':False,'orders':True};db.commit()
    try:
        assert operator.get(PATH,params={'customer_code':code}).status_code==403
        assert operator.post(PATH,json={'customer_code':code,'highlight_price_without_tax':True}).status_code==403
    finally:
        with SessionLocal() as db:
            saved=db.get(OperatorAccess,pk)
            if old is None:db.delete(saved)
            else:saved.permissions=old
            db.commit()


def test_favorites_use_same_customer_preference(clients,monkeypatch):
    customer,operator,code=clients
    product=customer.get('/api/v1/products?page_size=1').json()['items'][0]
    monkeypatch.setattr('app.main.fetch_customer_favorite_articles',lambda customer_code,limit=8:[{'article_code':product['sku'],'purchased_units':5}])
    before=customer.get('/api/v1/catalog/favorites').json()['items'][0]
    assert before['highlight_price_without_tax'] is False
    operator.post(PATH,json={'customer_code':code,'highlight_price_without_tax':True})
    after=customer.get('/api/v1/catalog/favorites').json()['items'][0]
    assert after['highlight_price_without_tax'] is True
    assert (after['price_with_tax'],after['price_without_tax'])==(before['price_with_tax'],before['price_without_tax'])
