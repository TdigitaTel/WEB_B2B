import pytest
pytestmark = pytest.mark.usefixtures("operator_with_almeiras_access")
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.db import SessionLocal
from app.main import app
from app.models import Order, PickupSettings, OrderStatusHistory
from app.pickup import assign_attention_deadline, scheduled_ready_at
from app.bootstrap import main as bootstrap

bootstrap()
MADRID = ZoneInfo('Europe/Madrid')


def configured(minutes=60):
    config = SimpleNamespace(preparation_minutes=minutes, schedules={'0:00': [dict(enabled=True, morning_from='08:00',morning_to='13:00',afternoon_from='16:00',afternoon_to='19:00') for _ in range(7)]})
    return SimpleNamespace(get=lambda *args:config), config


def test_immediate_deadline_respects_midday_and_closing():
    db, config = configured()
    order = SimpleNamespace(company_code=0, delegation_code='00', pickup_date=None)
    assign_attention_deadline(order, db, now=datetime(2026,10,21,10,15,tzinfo=MADRID))
    assert order.attention_deadline_at == datetime(2026,10,21,9,15,tzinfo=timezone.utc)
    assert order.preparation_minutes_snapshot == 60
    assign_attention_deadline(order, db, now=datetime(2026,10,21,13,0,tzinfo=MADRID))
    assert order.attention_deadline_at.astimezone(MADRID).strftime('%H:%M') == '17:00'
    with pytest.raises(HTTPException):
        assign_attention_deadline(order, db, now=datetime(2026,10,21,18,1,tzinfo=MADRID))
    assign_attention_deadline(order, db, operator_override=True, now=datetime(2026,10,21,18,1,tzinfo=MADRID))
    assert order.attention_deadline_at.astimezone(MADRID).strftime('%H:%M') == '19:01'


@pytest.mark.parametrize('day,utc_hour',[(date(2026,10,23),7),(date(2026,10,26),8)])
def test_scheduled_opening_plus_parameter_and_daylight_saving(day, utc_hour):
    db, config = configured()
    order = SimpleNamespace(company_code=0, delegation_code='00', pickup_date=day)
    assign_attention_deadline(order, db)
    assert order.attention_deadline_at.hour == utc_hour
    assert order.attention_deadline_at.astimezone(MADRID).strftime('%H:%M') == '09:00'
    config.preparation_minutes = 90
    assert order.preparation_minutes_snapshot == 60  # El compromiso anterior no se modifica.
    assert scheduled_ready_at(db,0,'00',day).strftime('%H:%M') == '09:30'
    config.schedules['0:00'][day.weekday()] = {'enabled':False}
    assert scheduled_ready_at(db,0,'00',day) is None


def login(email):
    client = TestClient(app)
    assert client.post('/api/v1/auth/login',json={'email':email,'password':'123456'}).status_code == 200
    return client


def test_deadline_is_persisted_previewed_and_recalculated_by_operator(pickup_schedule, classified_catalog):
    customer = login('compras001@cliente.test')
    operator = login('operador@bermudez.test')
    store = customer.get('/api/v1/stores').json()[0]
    day = datetime.now(MADRID).date()+timedelta(days=1)
    query = {'company':store['company_code'],'delegation':store['code'],'scheduled_date':day.isoformat()}
    preview = customer.get('/api/v1/pickup-availability',params=query).json()
    assert datetime.fromisoformat(preview['scheduled_ready_at']).hour == 9
    product = customer.get('/api/v1/products?page_size=1').json()['items'][0]
    customer.post('/api/v1/cart/items',json={'product_id':product['id'],'quantity':1})
    result = customer.post('/api/v1/orders',json={'company_code':store['company_code'],'delegation_code':store['code'],'pickup_date':day.isoformat()})
    assert result.status_code == 201, result.text
    order = result.json()
    assert datetime.fromisoformat(order['server_now']).tzinfo is not None
    deadline = datetime.fromisoformat(order['attention_deadline_at']).astimezone(MADRID)
    assert deadline.date() == day and deadline.hour == 9
    assert order['preparation_minutes_snapshot'] == 60
    with SessionLocal() as db:
        saved = db.scalar(select(Order).where(Order.public_id==order['id']))
        assert saved.attention_deadline_at is not None and saved.preparation_minutes_snapshot == 60
        config = db.get(PickupSettings,1);config.preparation_minutes=90;db.commit()
    unchanged = customer.get(f"/api/v1/orders/{order['id']}").json()
    assert unchanged['preparation_minutes_snapshot'] == 60
    assert datetime.fromisoformat(unchanged['attention_deadline_at']).hour == datetime.fromisoformat(order['attention_deadline_at']).hour
    revised = operator.patch(f"/api/v1/store/orders/{order['id']}/pickup",json={'pickup_date':(day+timedelta(days=1)).isoformat()})
    assert revised.status_code == 200, revised.text
    new_deadline = datetime.fromisoformat(revised.json()['attention_deadline_at']).astimezone(MADRID)
    assert new_deadline.date() == day+timedelta(days=1) and new_deadline.strftime('%H:%M') == '09:30'
    assert revised.json()['preparation_minutes_snapshot'] == 90
    with SessionLocal() as db:
        event = db.scalar(select(OrderStatusHistory).where(OrderStatusHistory.order_id==saved.id, OrderStatusHistory.note.contains('Límite de atención')))
        assert event is not None and '09:30' in event.note


def test_draft_receives_deadline_only_when_submitted(pickup_schedule, classified_catalog):
    client = login('compras001@cliente.test')
    store = client.get('/api/v1/stores').json()[0]
    day = datetime.now(MADRID).date()+timedelta(days=1)
    product = client.get('/api/v1/products?page_size=1').json()['items'][0]
    client.post('/api/v1/cart/items',json={'product_id':product['id'],'quantity':1})
    draft = client.post('/api/v1/orders',json={'company_code':store['company_code'],'delegation_code':store['code'],'pickup_date':day.isoformat(),'draft':True}).json()
    assert draft['attention_deadline_at'] is None
    result = client.post(f"/api/v1/orders/{draft['id']}/submit")
    assert result.status_code == 200, result.text
    assert datetime.fromisoformat(result.json()['attention_deadline_at']).astimezone(MADRID).hour == 9
