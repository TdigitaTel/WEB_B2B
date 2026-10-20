from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, parse_qs
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.main import app
from app.models import User, CustomerQrAccess

bootstrap()


def token(payload):
    return parse_qs(urlsplit(payload['url']).fragment)['qr'][0]


def test_qr_login_regeneration_revocation_and_isolation():
    operator=TestClient(app)
    assert operator.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'}).status_code==200
    customer=TestClient(app)
    customer.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'})
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email=='compras001@cliente.test'))
        code=user.erp_customer_code or user.customer.erp_id
        expected=user.public_id
    path='/api/v1/store/customer-access/qr'
    assert customer.post(path,json={'customer_code':code}).status_code==403
    qr=operator.post(path,json={'customer_code':code})
    assert qr.status_code==200,qr.text
    data=qr.json()
    assert data['image'].startswith('data:image/svg+xml;base64,')
    assert not urlsplit(data['url']).query
    assert 'no-store' in qr.headers['cache-control']
    first=token(data)
    with SessionLocal() as db:
        stored=db.scalar(select(CustomerQrAccess).where(CustomerQrAccess.user_id==user.id))
        assert first.split('.')[1] not in stored.secret_ciphertext
        assert stored.secret_hash != first.split('.')[1]
    visitor=TestClient(app)
    assert visitor.post('/api/v1/auth/qr',json={'token':first[:-1]+'!'}).status_code==401
    login=visitor.post('/api/v1/auth/qr',json={'token':first})
    assert login.status_code==200,login.text
    assert login.json()['user']['id']==expected
    assert visitor.get('/api/v1/account').status_code==200
    assert token(operator.post(path,json={'customer_code':code}).json())==first
    rotated=token(operator.post(path,json={'customer_code':code,'regenerate':True}).json())
    assert rotated!=first
    assert TestClient(app).post('/api/v1/auth/qr',json={'token':first}).status_code==401
    assert TestClient(app).post('/api/v1/auth/qr',json={'token':rotated}).status_code==200
    operator.post(path+'/revoke',json={'customer_code':code})
    assert TestClient(app).post('/api/v1/auth/qr',json={'token':rotated}).status_code==401


def test_qr_respects_disabled_expired_and_initial_password():
    operator=TestClient(app)
    operator.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'})
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email=='compras002@cliente.test'))
        code=user.erp_customer_code or user.customer.erp_id;uid=user.id
    data=operator.post('/api/v1/store/customer-access/qr',json={'customer_code':code}).json()
    access=token(data)
    with SessionLocal() as db:
        account=db.get(User,uid);account.must_change_password=True
        account.initial_password_expires_at=datetime.now(timezone.utc)+timedelta(hours=1)
        db.commit()
    visitor=TestClient(app)
    assert visitor.post('/api/v1/auth/qr',json={'token':access}).json()['user']['must_change_password'] is True
    assert visitor.get('/api/v1/orders').status_code==403
    with SessionLocal() as db:
        account=db.get(User,uid);account.must_change_password=False;account.initial_password_expires_at=None;account.active=False;db.commit()
    assert TestClient(app).post('/api/v1/auth/qr',json={'token':access}).status_code==401
    with SessionLocal() as db:
        db.get(User,uid).active=True
        record=db.scalar(select(CustomerQrAccess).where(CustomerQrAccess.user_id==uid));record.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
    assert TestClient(app).post('/api/v1/auth/qr',json={'token':access}).status_code==401
