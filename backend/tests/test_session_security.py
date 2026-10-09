from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db import SessionLocal
from app.models import AuthSession


def login(client):
    response = client.post('/api/v1/auth/login', json={'email':'operador@bermudez.test','password':'123456'})
    assert response.status_code == 200
    return response.json()['access_token']


def test_idle_session_expires_and_polling_does_not_extend_it():
    client = TestClient(app)
    token = login(client)
    import jwt
    from app.config import settings
    sid = jwt.decode(token, settings.jwt_secret, algorithms=['HS256'])['jti']
    with SessionLocal() as db:
        session = db.get(AuthSession, sid)
        session.last_activity_at = datetime.now(timezone.utc)-timedelta(seconds=45)
        db.commit()
        before = session.last_activity_at
    assert client.get('/api/v1/account').status_code == 200
    with SessionLocal() as db:
        assert db.get(AuthSession, sid).last_activity_at.replace(tzinfo=None) == before.replace(tzinfo=None)
    with SessionLocal() as db:
        session = db.get(AuthSession, sid)
        session.last_activity_at = datetime.now(timezone.utc)-timedelta(seconds=61)
        db.commit()
    assert client.get('/api/v1/account').status_code == 401
    assert client.post('/api/v1/auth/activity').status_code == 401


def test_activity_refresh_logout_revokes_bearer_and_no_cache():
    client = TestClient(app)
    token = login(client)
    response = client.post('/api/v1/auth/activity')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store, private'
    assert client.get('/api/v1/account').status_code == 200
    assert client.post('/api/v1/auth/logout').status_code == 200
    assert client.get('/api/v1/account', headers={'Authorization':'Bearer '+token}).status_code == 401
