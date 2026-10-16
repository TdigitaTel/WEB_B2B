from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo
import pytest
from pydantic import ValidationError
from app.pickup import immediate_available
from app.schemas import OpeningDay, PickupSettingsIn
from app.bootstrap import main as bootstrap
bootstrap()


def test_opening_shifts_and_preparation_deadline():
    days=[dict(morning_from='08:00',morning_to='13:00',afternoon_from='16:00',afternoon_to='19:00') for _ in range(7)]
    days[6]={}
    db=SimpleNamespace(get=lambda *args: SimpleNamespace(preparation_minutes=60,schedules={'1:00':days}))
    def available(hour,minute=0,day=16):
        return immediate_available(db,1,'00',datetime(2026,10,day,hour,minute,tzinfo=ZoneInfo('Europe/Madrid')))
    assert available(12)
    assert not available(12,1)
    assert not available(14)
    assert available(16)
    assert not available(18,1)
    assert not available(7)
    assert not available(10,day=18)
    assert not immediate_available(db,1,'01')


def test_invalid_shifts_and_missing_configuration():
    assert not immediate_available(SimpleNamespace(get=lambda *args:None),1,'00')
    for values in [dict(morning_from='08:00'),dict(morning_from='13:00',morning_to='08:00'),dict(morning_from='08:00',morning_to='17:00',afternoon_from='16:00',afternoon_to='19:00')]:
        with pytest.raises(ValidationError): OpeningDay(**values)
    with pytest.raises(ValidationError): PickupSettingsIn(preparation_minutes=60,schedules={'1:00':[]})


def test_customer_cannot_edit_hours_and_immediate_is_checked_on_submit():
    from fastapi.testclient import TestClient
    from app.main import app
    client=TestClient(app)
    assert client.get('/api/v1/pickup-availability?company=1&delegation=00').status_code==401
    client.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'})
    assert client.patch('/api/v1/pickup-settings',json={'preparation_minutes':30,'schedules':{}}).status_code==403
    store=client.get('/api/v1/stores').json()[0]
    response=client.post('/api/v1/orders',json={'company_code':store['company_code'],'delegation_code':store['code']})
    assert response.status_code==409
    assert 'inmediata' in response.json()['detail']


def test_next_business_day_after_friday_closing():
    from app.pickup import next_open_date, scheduled_date_open
    days=[dict(morning_from='08:00',morning_to='13:00',afternoon_from='16:00',afternoon_to='19:00') for _ in range(5)]+[{},{}]
    db=SimpleNamespace(get=lambda *args: SimpleNamespace(preparation_minutes=60,schedules={'1:00':days}))
    now=datetime(2026,10,16,18,1,tzinfo=ZoneInfo('Europe/Madrid'))
    assert not immediate_available(db,1,'00',now)
    assert next_open_date(db,1,'00',now).isoformat()=='2026-10-19'
    assert not scheduled_date_open(db,1,'00',now.date().replace(day=17))
    assert scheduled_date_open(db,1,'00',now.date().replace(day=19))


def test_day_unchecked_and_empty_hours_mean_no_service():
    from app.pickup import next_open_date, scheduled_date_open
    days=[dict(enabled=True,morning_from='08:00',morning_to='13:00',afternoon_from='',afternoon_to='') for _ in range(7)]
    now=datetime(2026,10,16,10,0,tzinfo=ZoneInfo('Europe/Madrid'))
    days[4]['enabled']=False
    days[5]=dict(enabled=True,morning_from='',morning_to='',afternoon_from='',afternoon_to='')
    db=SimpleNamespace(get=lambda *args:SimpleNamespace(preparation_minutes=60,schedules={'1:00':days}))
    assert not immediate_available(db,1,'00',now)
    assert not scheduled_date_open(db,1,'00',now.date())
    assert not scheduled_date_open(db,1,'00',now.date().replace(day=17))
    assert next_open_date(db,1,'00',now).isoformat()=='2026-10-18'
