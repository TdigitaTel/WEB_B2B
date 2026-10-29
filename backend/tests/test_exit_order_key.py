from datetime import datetime, timezone
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.bootstrap import main as bootstrap
from app.config import settings
from app.db import SessionLocal
from app.models import Order, OrderItem, OrderStatusHistory
from app.main import app

bootstrap()
pytestmark=pytest.mark.usefixtures('operator_with_almeiras_access')


def create(number):
    with SessionLocal() as db:
        order=Order(order_number=number,customer_code='CLI00001',company_code=0,delegation_code='00',origen_pedido='B2B',estado_registro_exit='REGISTRADO')
        db.add(order);db.flush()
        db.add(OrderItem(order_id=order.id,sku='KEY',description='Material',quantity=1,unit='UD',unit_price=1,tax_rate=21,line_total=1))
        db.commit();return order.public_id,order.id


def test_robot_completes_structured_key_without_changing_state(monkeypatch):
    monkeypatch.setattr(settings,'integration_api_key','key-test')
    oid,local_id=create('WEB-KEY-RPA')
    client=TestClient(app);headers={'X-Integration-Key':'key-test'}
    identity={'exit_company_code':0,'exit_order_year':2026,'exit_series':'AL','exit_order_number':'7008375'}
    body={'order_id':oid,'estado_registro_exit':'REGISTRADO','source':'RPA',**identity}
    assert client.patch('/api/v1/integrations/orders/estado',json=body).status_code==401
    first=client.patch('/api/v1/integrations/orders/estado',json=body,headers=headers)
    assert first.status_code==200,first.text
    assert first.json()['changed'] is True
    for field,value in identity.items():
        assert first.json()['order'][field]==value
        assert first.json()['order']['items'][0][field]==value
    repeat=client.patch('/api/v1/integrations/orders/estado',json=body,headers=headers)
    assert repeat.status_code==200 and repeat.json()['changed'] is False
    with SessionLocal() as db:
        assert not db.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id==local_id)).all()
        assert 'exit_company_code' not in Order.__table__.columns
        assert 'exit_order_year' not in OrderItem.__table__.columns  # The detail inherits its parent key.
    listed=client.get('/api/v1/integrations/orders?estado_registro_exit=TODOS&include_items=true',headers=headers)
    assert next(row for row in listed.json()['items'] if row['id']==oid)['items'][0]['exit_order_number']=='7008375'


def test_full_key_unique_but_number_can_repeat_in_other_series(monkeypatch):
    monkeypatch.setattr(settings,'integration_api_key','key-test')
    client=TestClient(app);headers={'X-Integration-Key':'key-test'}
    ids=[create(f'WEB-KEY-UNIQUE-{i}')[0] for i in range(3)]
    body={'estado_registro_exit':'REGISTRADO','exit_company_code':0,'exit_order_year':2026,'exit_series':'UNIQUE','exit_order_number':'99'}
    url='/api/v1/integrations/orders/estado'
    assert client.patch(url,json={**body,'order_id':ids[0]},headers=headers).status_code==200
    assert client.patch(url,json={**body,'order_id':ids[1]},headers=headers).status_code==409
    assert client.patch(url,json={**body,'exit_series':'OTHER','order_id':ids[1]},headers=headers).status_code==200
    assert client.patch(url,json={**body,'exit_order_year':2025,'order_id':ids[2]},headers=headers).status_code==200
    invalid=client.patch(url,json={**body,'order_id':ids[2],'exit_company_code':2},headers=headers)
    assert invalid.status_code==422


def test_partial_robot_key_and_legacy_number_remain_compatible(monkeypatch):
    monkeypatch.setattr(settings,'integration_api_key','key-test')
    oid,_=create('WEB-KEY-PARTIAL')
    client=TestClient(app);headers={'X-Integration-Key':'key-test'};url='/api/v1/integrations/orders/estado'
    body={'order_id':oid,'estado_registro_exit':'REGISTRADO'}
    old=client.patch(url,json={**body,'nro_pedido_exit':'6008999'},headers=headers)
    assert old.status_code==200 and old.json()['order']['exit_order_year'] is None
    first=client.patch(url,json={**body,'exit_order_number':'6008999'},headers=headers)
    assert first.status_code==200,first.text
    second=client.patch(url,json={**body,'exit_company_code':0,'exit_order_year':2026,'exit_series':''},headers=headers)
    assert second.status_code==200 and second.json()['order']['exit_series']==''
    assert second.json()['order']['exit_order_number']=='6008999'


def test_manual_key_is_shared_by_details_and_unlink_clears_it():
    oid,_=create('WEB-KEY-MANUAL')
    operator=TestClient(app);operator.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'})
    key={'exit_company_code':0,'exit_order_year':2026,'exit_series':'MANUALKEY','exit_order_number':'900001'}
    path=f'/api/v1/store/orders/{oid}/registration'
    response=operator.patch(path,json={'state':'REGISTRADO',**key,'exit_registered_at':datetime.now(timezone.utc).isoformat()})
    assert response.status_code==200,response.text
    assert response.json()['exit_order_number']=='900001'
    assert response.json()['items'][0]['exit_series']=='MANUALKEY'
    pending=operator.patch(path,json={'state':'PENDIENTE'})
    assert pending.status_code==200,pending.text
    assert pending.json()['exit_order_number'] is None
    assert pending.json()['items'][0]['exit_order_year'] is None
