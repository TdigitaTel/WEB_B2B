import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, delete
from app.main import app
from app.db import SessionLocal
from app.models import CustomerCatalogSetting, User, AuthSession
from app.bootstrap import main as bootstrap
from app.auth import hash_password

bootstrap()
PATH='/api/v1/account/catalog-price'
OLD='/api/v1/store/customer-access/catalog-price'


def login(email):
    client=TestClient(app)
    assert client.post('/api/v1/auth/login',json={'email':email,'password':'123456'}).status_code==200
    return client


@pytest.fixture
def clients(exit_erp_stub,classified_catalog):
    customer=login('compras001@cliente.test');operator=login('operador@bermudez.test')
    code=customer.get('/api/v1/account').json()['customer']['erp_id']
    yield customer,operator,code
    with SessionLocal() as db:
        row=db.get(CustomerCatalogSetting,code)
        if row:db.delete(row)
        db.commit()


def change(client,value):return client.patch(PATH,json={'highlight_price_without_tax':value})


def test_customer_saves_own_setting_and_price_amounts_do_not_change(clients):
    customer,operator,code=clients
    assert customer.get(PATH).json()=={'highlight_price_without_tax':False}
    before=customer.get('/api/v1/products?page_size=1').json()['items'][0]
    assert change(customer,True).status_code==200
    with SessionLocal() as db:assert db.get(CustomerCatalogSetting,code).highlight_price_without_tax is True
    after=customer.get('/api/v1/products?page_size=1').json()['items'][0]
    assert after['highlight_price_without_tax'] is True
    assert (after['price_with_tax'],after['price_without_tax'])==(before['price_with_tax'],before['price_without_tax'])
    assert customer.get('/api/v1/products/'+after['id']).json()['highlight_price_without_tax'] is True
    assert change(customer,False).status_code==200
    assert customer.get(PATH).json()['highlight_price_without_tax'] is False


def test_operator_and_old_management_endpoint_cannot_change_preference(clients):
    customer,operator,code=clients
    assert TestClient(app).get(PATH).status_code==401
    assert operator.get(PATH).status_code==403
    assert change(operator,True).status_code==403
    assert operator.get(OLD,params={'customer_code':code}).status_code==404
    assert operator.post(OLD,json={'customer_code':code,'highlight_price_without_tax':True}).status_code==404
    assert customer.get(PATH).json()['highlight_price_without_tax'] is False


def test_request_cannot_target_a_different_customer_and_is_strict(clients):
    customer,operator,code=clients
    assert customer.patch(PATH,json={'customer_code':'OTHER-CUSTOMER','highlight_price_without_tax':True}).status_code==422
    assert change(customer,'false').status_code==422
    other=login('compras002@cliente.test')
    assert change(customer,True).status_code==200
    assert other.get(PATH).json()['highlight_price_without_tax'] is False
    with SessionLocal() as db:assert db.get(CustomerCatalogSetting,'OTHER-CUSTOMER') is None


def test_subusers_inherit_but_cannot_change_shared_preference(clients):
    customer,operator,code=clients
    with SessionLocal() as db:
        parent=db.scalar(select(User).where(User.email=='compras001@cliente.test'))
        sub=User(email='price-child@example.test',full_name='Precio subusuario',password_hash=hash_password('123456'),role='CLIENTE',parent_user_id=parent.id,customer_id=parent.customer_id,erp_customer_code=code,active=True,can_manage_preferences=True)
        db.add(sub);db.commit();pk=sub.id
    try:
        child=login('price-child@example.test')
        assert change(customer,True).status_code==200
        assert child.get(PATH).json()['highlight_price_without_tax'] is True
        assert change(child,False).status_code==403
        assert child.get('/api/v1/products?page_size=1').json()['items'][0]['highlight_price_without_tax'] is True
        with SessionLocal() as db:db.get(User,pk).can_view_prices=False;db.commit()
        product=child.get('/api/v1/products?page_size=1').json()['items'][0]
        assert product['price_with_tax'] is None and product['price_without_tax'] is None
    finally:
        with SessionLocal() as db:
            db.execute(delete(AuthSession).where(AuthSession.user_id==pk));db.delete(db.get(User,pk));db.commit()


def test_existing_preference_and_preference_permission_are_preserved(clients):
    customer,operator,code=clients
    with SessionLocal() as db:
        row=CustomerCatalogSetting(customer_code=code,highlight_price_without_tax=True);db.add(row)
        user=db.scalar(select(User).where(User.email=='compras001@cliente.test'));pk=user.id;old=user.can_manage_preferences
        user.can_manage_preferences=False;db.commit()
    try:
        assert customer.get(PATH).json()['highlight_price_without_tax'] is True
        assert change(customer,False).status_code==403
    finally:
        with SessionLocal() as db:db.get(User,pk).can_manage_preferences=old;db.commit()


def test_favorites_and_suggestions_use_customer_choice(clients,monkeypatch):
    customer,operator,code=clients
    product=customer.get('/api/v1/products?page_size=1').json()['items'][0]
    monkeypatch.setattr('app.main.fetch_customer_favorite_articles',lambda customer_code,limit=8:[{'article_code':product['sku'],'purchased_units':5}])
    def suggestion():return next(row for row in customer.get('/api/v1/search/suggestions',params={'q':product['sku']}).json() if row['sku']==product['sku'])
    assert suggestion()['price_includes_tax'] is True
    change(customer,True)
    after=suggestion()
    assert after['price_includes_tax'] is False and after['price']==product['price_without_tax']
    favorite=customer.get('/api/v1/catalog/favorites').json()['items'][0]
    assert favorite['highlight_price_without_tax'] is True
