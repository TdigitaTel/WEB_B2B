from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from app.main import create_order, pickup_settings, update_pickup_settings
from app.models import PickupSettings, User
from app.schemas import OrderCreate, PickupSettingsIn
from app.db import SessionLocal
from app.bootstrap import main as bootstrap
bootstrap()


def test_pickup_settings_persist_and_server_date(monkeypatch):
    monkeypatch.setattr('app.main.audit', lambda *args: None)
    with SessionLocal() as db:
        user=User(id=1)
        result=update_pickup_settings(PickupSettingsIn(preparation_minutes=45),user,db)
        assert result['preparation_minutes']==45
        assert result['minimum_date']==(datetime.now(ZoneInfo('Europe/Madrid')).date()+timedelta(days=1)).isoformat()
        assert db.get(PickupSettings,1).preparation_minutes==45
        db.delete(db.get(PickupSettings,1));db.commit()
    with pytest.raises(ValidationError):
        PickupSettingsIn(preparation_minutes=0)


def test_programmed_pickup_rejects_today_before_order_creation():
    today=datetime.now(ZoneInfo('Europe/Madrid')).date()
    with pytest.raises(HTTPException) as error:
        create_order(OrderCreate(pickup_date=today),User(),None)
    assert error.value.status_code==422
