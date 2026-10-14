from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.main import app
from app.models import AuditEvent, User
from app.auth import verify_password
from app import customer_access

bootstrap()


def operator():
    client = TestClient(app)
    assert client.post('/api/v1/auth/login', json={'email':'operador@bermudez.test','password':'123456'}).status_code == 200
    return client


def fake_customer(code):
    return {'erp_id':code,'legal_name':f'Cliente {code}','trade_name':f'Cliente {code}','email':'cliente@example.test'}


def test_rollout_forces_change_and_disable_revokes_session(monkeypatch):
    monkeypatch.setattr(customer_access,'fetch_customer',fake_customer)
    client=operator()
    result=client.post('/api/v1/store/customer-access/enable',json={'customer_code':'NEW-001'})
    assert result.status_code == 200
    credentials=result.json()
    assert len(credentials['initial_password']) >= 12
    assert client.post('/api/v1/store/customer-access/enable',json={'customer_code':'NEW-001'}).status_code == 409
    customer=TestClient(app)
    login=customer.post('/api/v1/auth/login',json={'email':credentials['username'],'password':credentials['initial_password']})
    assert login.status_code == 200 and login.json()['user']['must_change_password']
    token=login.json()['access_token']
    assert customer.get('/api/v1/products').status_code == 403
    assert customer.post('/api/v1/orders',json={}).status_code == 403
    assert customer.get('/api/v1/account').status_code == 200
    assert customer.patch('/api/v1/account/password',json={'current_password':credentials['initial_password'],'new_password':'short12'}).status_code == 422
    assert customer.patch('/api/v1/account/password',json={'current_password':'wrong','new_password':'personal-password-2026'}).status_code == 400
    assert customer.patch('/api/v1/account/password',json={'current_password':credentials['initial_password'],'new_password':'personal-password-2026'}).status_code == 200
    assert not customer.get('/api/v1/account').json()['user']['must_change_password']
    assert customer.get('/api/v1/products?page_size=1').status_code == 200
    assert client.post('/api/v1/store/customer-access/disable',json={'customer_code':'NEW-001'}).status_code == 200
    assert customer.get('/api/v1/account',headers={'Authorization':'Bearer '+token}).status_code == 401
    assert customer.post('/api/v1/auth/login',json={'email':credentials['username'],'password':'personal-password-2026'}).status_code == 401
    reenabled=client.post('/api/v1/store/customer-access/enable',json={'customer_code':'NEW-001'}).json()
    assert reenabled['initial_password'] != credentials['initial_password']
    with SessionLocal() as db:
        account=db.scalar(select(User).where(User.erp_customer_code=='NEW-001'))
        assert account.must_change_password and verify_password(reenabled['initial_password'],account.password_hash)
        assert reenabled['initial_password'] not in account.password_hash
        assert all('password' not in str(event.metadata_json) for event in db.scalars(select(AuditEvent).where(AuditEvent.entity_id==account.public_id)))


def test_expired_initial_password_and_customer_cannot_administer(monkeypatch):
    monkeypatch.setattr(customer_access,'fetch_customer',fake_customer)
    credentials=operator().post('/api/v1/store/customer-access/enable',json={'customer_code':'NEW-002'}).json()
    customer=TestClient(app)
    assert customer.post('/api/v1/auth/login',json={'email':credentials['username'],'password':credentials['initial_password']}).status_code == 200
    assert customer.get('/api/v1/store/customer-access').status_code == 403
    with SessionLocal() as db:
        account=db.scalar(select(User).where(User.erp_customer_code=='NEW-002'))
        account.initial_password_expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
    assert customer.get('/api/v1/account').status_code == 401
    assert customer.post('/api/v1/auth/login',json={'email':credentials['username'],'password':credentials['initial_password']}).status_code == 401


def test_search_by_exit_code_and_name_is_bounded(monkeypatch):
    seen=[]
    def search(q,after,limit):
        seen.append((q,after,limit))
        return [fake_customer('00004')]
    monkeypatch.setattr(customer_access,'fetch_access_customers',search)
    response=operator().get('/api/v1/store/customer-access?q=Cliente')
    assert response.status_code == 200
    assert seen==[('Cliente','',51)]
    assert response.json()['items'][0]['enabled']


def test_email_delivery_and_no_silent_password_reset(monkeypatch):
    monkeypatch.setattr(customer_access,'fetch_customer',fake_customer)
    from app.config import settings
    monkeypatch.setattr(settings,'smtp_host','smtp.example.test')
    monkeypatch.setattr(settings,'smtp_sender','no-reply@example.test')
    smtp=MagicMock();smtp.__enter__.return_value=smtp;smtp.send_message.return_value={}
    monkeypatch.setattr(customer_access.smtplib,'SMTP',lambda *args,**kwargs:smtp)
    client=operator();credentials=client.post('/api/v1/store/customer-access/enable',json={'customer_code':'NEW-003'}).json()
    payload={'customer_code':'NEW-003','recipient':'destino@example.test','initial_password':credentials['initial_password']}
    assert client.post('/api/v1/store/customer-access/email',json=payload).status_code == 200
    smtp.starttls.assert_called_once()
    message=smtp.send_message.call_args.args[0]
    assert message['To']=='destino@example.test' and credentials['initial_password'] in message.get_content()
    assert client.post('/api/v1/store/customer-access/email',json={**payload,'initial_password':'not-valid'}).status_code == 409
    assert client.post('/api/v1/store/customer-access/email',json={**payload,'recipient':'evil\nBcc: other@example.test'}).status_code == 422
    monkeypatch.setattr(settings,'smtp_host','')
    assert client.post('/api/v1/store/customer-access/email',json=payload).status_code == 503


def test_startup_preserves_disabled_demo_and_changed_password():
    from app.seed import ensure_demo_access
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email=='pumaresdavid@gmail.com'))
        previous_hash,previous_active=user.password_hash,user.active
        user.active=False;db.commit()
        ensure_demo_access(db)
        assert not user.active and user.password_hash==previous_hash
        user.active=previous_active;db.commit()


def test_initial_password_reveal_regenerate_and_clear(monkeypatch):
    monkeypatch.setattr(customer_access,'fetch_customer',fake_customer)
    client=operator()
    credentials=client.post('/api/v1/store/customer-access/enable',json={'customer_code':'NEW-REVEAL'}).json()
    body={'customer_code':'NEW-REVEAL'}
    revealed=client.post('/api/v1/store/customer-access/initial',json=body)
    assert revealed.status_code==200
    assert revealed.json()['credentials']['initial_password']==credentials['initial_password']
    with SessionLocal() as db:
        account=db.scalar(select(User).where(User.erp_customer_code=='NEW-REVEAL'))
        assert account.initial_password_ciphertext and credentials['initial_password'] not in account.initial_password_ciphertext
        account.email='existing-email@example.test'
        db.commit()
    customer=TestClient(app)
    assert customer.post('/api/v1/auth/login',json={'email':'NEW-REVEAL','password':credentials['initial_password']}).status_code==200
    assert customer.post('/api/v1/store/customer-access/initial',json=body).status_code==403
    regenerated=client.post('/api/v1/store/customer-access/regenerate',json=body).json()
    assert regenerated['initial_password']!=credentials['initial_password']
    assert customer.post('/api/v1/auth/login',json={'email':'NEW-REVEAL','password':credentials['initial_password']}).status_code==401
    assert customer.post('/api/v1/auth/login',json={'email':'NEW-REVEAL','password':regenerated['initial_password']}).status_code==200
    assert customer.patch('/api/v1/account/password',json={'current_password':regenerated['initial_password'],'new_password':'personal-safe-password-2026'}).status_code==200
    assert client.post('/api/v1/store/customer-access/initial',json=body).json()['credentials'] is None
    assert client.post('/api/v1/store/customer-access/regenerate',json=body).status_code==409
    with SessionLocal() as db:
        account=db.scalar(select(User).where(User.erp_customer_code=='NEW-REVEAL'))
        assert account.initial_password_ciphertext is None


def test_legacy_and_expired_initial_password_are_not_revealed(monkeypatch):
    monkeypatch.setattr(customer_access,'fetch_customer',fake_customer)
    client=operator();body={'customer_code':'NEW-LEGACY-KEY'}
    client.post('/api/v1/store/customer-access/enable',json=body)
    with SessionLocal() as db:
        account=db.scalar(select(User).where(User.erp_customer_code==body['customer_code']))
        account.initial_password_ciphertext=None;db.commit()
    assert client.post('/api/v1/store/customer-access/initial',json=body).json()['credentials'] is None
    assert client.post('/api/v1/store/customer-access/regenerate',json=body).status_code==200
    with SessionLocal() as db:
        account=db.scalar(select(User).where(User.erp_customer_code==body['customer_code']))
        account.initial_password_expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
    assert client.post('/api/v1/store/customer-access/initial',json=body).json()['credentials'] is None
    with SessionLocal() as db:
        account=db.scalar(select(User).where(User.erp_customer_code==body['customer_code']))
        assert account.initial_password_ciphertext is None
