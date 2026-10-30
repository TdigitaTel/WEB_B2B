import pytest
from fastapi.testclient import TestClient
from app import main as module
from app.db import SessionLocal
from app.models import ScreenRefreshSettings
from app.bootstrap import main as bootstrap
bootstrap()


def login(email):
    client=TestClient(module.app)
    assert client.post('/api/v1/auth/login',json={'email':email,'password':'123456'}).status_code==200
    return client


def test_default_persisted_interval_and_permissions():
    anonymous=TestClient(module.app)
    with SessionLocal() as db:
        row=db.get(ScreenRefreshSettings,1)
        if row: db.delete(row);db.commit()
    assert anonymous.get('/api/v1/screen-refresh-settings').json()=={'interval_seconds':5}
    path='/api/v1/store/screen-refresh-settings'
    assert anonymous.patch(path,json={'interval_seconds':30}).status_code==401
    assert login('compras001@cliente.test').patch(path,json={'interval_seconds':30}).status_code==403
    operator=login('operador@bermudez.test')
    try:
        assert operator.patch(path,json={'interval_seconds':30}).json()=={'interval_seconds':30}
        with SessionLocal() as db:
            assert db.get(ScreenRefreshSettings,1).interval_seconds==30
        assert TestClient(module.app).get('/api/v1/screen-refresh-settings').json()=={'interval_seconds':30}
        for invalid in (0,4,301,-1,5.5,'5',True,None):
            assert operator.patch(path,json={'interval_seconds':invalid}).status_code==422
        assert anonymous.get('/api/v1/screen-refresh-settings').json()=={'interval_seconds':30}
    finally:
        operator.patch(path,json={'interval_seconds':5})
