from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.models import Order
from app.db import SessionLocal
from app.pickup import pickup_slots, pickup_slot_ready_at, assign_attention_deadline
from app.schemas import OrderCreate

MADRID=ZoneInfo('Europe/Madrid')

def configured(minutes=60):
    days=[dict(enabled=True,morning_from='08:00',morning_to='13:00',afternoon_from='16:00',afternoon_to='19:00') for _ in range(7)]
    days[5]=dict(enabled=True,morning_from='08:00',morning_to='11:00',afternoon_from='',afternoon_to='')
    days[6]={'enabled':False}
    config=SimpleNamespace(preparation_minutes=minutes,schedules={'0:00':days})
    return SimpleNamespace(get=lambda *args:config),config


def test_slots_follow_selected_weekday_breaks_and_preparation():
    db,config=configured()
    saturday=date(2026,11,7)
    slots=pickup_slots(db,0,'00',saturday)
    assert [(slot['start'],slot['end']) for slot in slots]==[('08:00','09:00'),('09:00','10:00'),('10:00','11:00')]
    assert slots[0]['ready_at'].endswith('09:00:00+01:00')
    assert pickup_slots(db,0,'00',saturday+timedelta(days=1))==[]
    weekday=pickup_slots(db,0,'00',saturday-timedelta(days=1))
    assert not any(slot['start']=='13:00' or slot['start']=='14:00' for slot in weekday)
    config.preparation_minutes=90
    slots=pickup_slots(db,0,'00',saturday)
    assert slots[0]['start']=='09:00' and '09:30:00' in slots[0]['ready_at']
    with pytest.raises(HTTPException):pickup_slot_ready_at(db,0,'00',saturday,'08:00','09:00')
    with pytest.raises(HTTPException):pickup_slot_ready_at(db,0,'00',saturday,'11:00','12:00')


def test_saved_window_deadline_and_schema_validation():
    db,_=configured()
    order=SimpleNamespace(company_code=0,delegation_code='00',pickup_date=date(2026,11,7),pickup_slot_start='10:00',pickup_slot_end='11:00')
    assign_attention_deadline(order,db)
    assert order.attention_deadline_at.astimezone(MADRID).strftime('%H:%M')=='10:00'
    for payload in ({'pickup_slot_start':'10:00'},{'pickup_date':'2026-11-07','pickup_slot_start':'11:00','pickup_slot_end':'10:00'},{'pickup_date':'2026-11-07','pickup_slot_start':'99:00','pickup_slot_end':'10:00'}):
        with pytest.raises(ValueError):OrderCreate(**payload)


def login(email):
    c=TestClient(app)
    assert c.post('/api/v1/auth/login',json={'email':email,'password':'123456'}).status_code==200
    return c


@pytest.mark.usefixtures('operator_with_almeiras_access')
def test_window_is_persisted_and_calendar_uses_collection_day_not_creation(pickup_schedule,classified_catalog):
    customer=login('compras001@cliente.test');operator=login('operador@bermudez.test')
    store=customer.get('/api/v1/stores').json()[0]
    day=datetime.now(MADRID).date()+timedelta(days=1)
    preview=customer.get('/api/v1/pickup-availability',params={'company':store['company_code'],'delegation':store['code'],'scheduled_date':day.isoformat()}).json()
    slot=preview['pickup_slots'][-1]
    product=customer.get('/api/v1/products?page_size=1').json()['items'][0]
    customer.post('/api/v1/cart/items',json={'product_id':product['id'],'quantity':1})
    body={'company_code':store['company_code'],'delegation_code':store['code'],'pickup_date':day.isoformat(),'pickup_slot_start':slot['start'],'pickup_slot_end':slot['end']}
    created=customer.post('/api/v1/orders',json=body)
    assert created.status_code==201,created.text
    order=created.json();oid=order['id']
    assert order['pickup_slot_start']==slot['start'] and order['pickup_slot_end']==slot['end']
    assert datetime.fromisoformat(order['attention_deadline_at']).astimezone(MADRID)==datetime.fromisoformat(slot['ready_at'])
    with SessionLocal() as db:
        saved=db.scalar(select(Order).where(Order.public_id==oid))
        saved.created_at=datetime(2020,1,1,tzinfo=MADRID);db.commit()
    query={'day':day.isoformat(),'delegation':f"{store['company_code']}:{store['code']}"}
    result=operator.get('/api/v1/store/order-calendar',params=query)
    assert result.status_code==200,result.text
    assert oid in [row['id'] for row in result.json()['orders']]
    assert customer.get('/api/v1/store/order-calendar',params=query).status_code==403
    assert oid not in [row['id'] for row in operator.get('/api/v1/store/order-calendar',params={**query,'delegation':'99'}).json()['orders']]
    assert oid not in [row['id'] for row in operator.get('/api/v1/store/order-calendar',params={**query,'day':(day+timedelta(days=1)).isoformat()}).json()['orders']]
    newslot=preview['pickup_slots'][0]
    revised=operator.patch(f'/api/v1/store/orders/{oid}/pickup',json={'pickup_date':day.isoformat(),'pickup_slot_start':newslot['start'],'pickup_slot_end':newslot['end']})
    assert revised.status_code==200,revised.text
    assert revised.json()['pickup_slot_start']==newslot['start']
    rejected=operator.patch(f'/api/v1/store/orders/{oid}/pickup',json={'pickup_date':day.isoformat(),'pickup_slot_start':'23:00','pickup_slot_end':'23:59'})
    assert rejected.status_code==422
    assert customer.get(f'/api/v1/orders/{oid}').json()['pickup_slot_start']==newslot['start']
