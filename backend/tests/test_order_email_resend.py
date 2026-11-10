from contextlib import contextmanager
import smtplib
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.db import SessionLocal
from app.models import Order, User, OrderEmailSettings, OrderEmailDelivery, OperatorAccess
from app import order_email_worker as worker, order_email_resend as resend_module
from test_customer_order_email import context, configure, new_order, latest


def prepare(context,monkeypatch,automatic=True):
    customer,contacts=context
    assert customer.patch('/api/v1/account/order-emails',json={'email1_enabled':True,'email2_enabled':False}).status_code==200
    with SessionLocal() as db:
        configure(db)
        config=db.get(OrderEmailSettings,1);config.configuration={**config.configuration,'automatic_enabled':automatic};db.commit()
        order=new_order(db)
        actor=db.scalar(select(User).where(User.email=='operador@bermudez.test'))
        order.company_code=actor.company_code;order.delegation_code=actor.delegation_code
        db.commit();oid=order.public_id;orderid=order.id
    sent=[]
    monkeypatch.setattr(worker,'send_message',lambda config,password,message,phase:sent.append(message))
    operator=TestClient(app)
    assert operator.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'}).status_code==200
    return operator,f'/api/v1/store/orders/{oid}/email',orderid,sent


def test_manual_send_when_automatic_is_off_and_duplicate_is_blocked(context,monkeypatch):
    client,path,oid,sent=prepare(context,monkeypatch,automatic=False)
    status=client.get(path);assert status.status_code==200,status.text
    status=status.json();assert status['can_send'] is True and status['automatic_enabled'] is False
    assert status['recipient_count']==1
    response=client.post(path+'/resend',json={'expected_state_key':status['state_key']})
    assert response.status_code==200,response.text
    assert response.json()['status']=='SENT' and len(sent)==1
    assert str(sent[0]['To'])=='first@example.test'
    assert client.get(path).json()['can_send'] is False
    assert client.post(path+'/resend',json={'expected_state_key':status['state_key']}).status_code==409
    assert len(sent)==1
    with SessionLocal() as db:
        assert len(list(db.scalars(select(OrderEmailDelivery).where(OrderEmailDelivery.order_id==oid))))==1


def test_unconfigured_state_explains_why_and_never_sends(context,monkeypatch):
    client,path,_,sent=prepare(context,monkeypatch)
    with SessionLocal() as db:
        row=db.get(OrderEmailSettings,1);row.configuration={**row.configuration,'selected_states':[]};db.commit()
    status=client.get(path).json();assert status['can_send'] is False
    assert 'no está configurado' in status['reason'] and 'Pendiente' in status['reason']
    response=client.post(path+'/resend',json={'expected_state_key':status['state_key']})
    assert response.status_code==409 and 'no está configurado' in response.json()['detail']
    assert sent==[]


def test_missing_smtp_or_destinations_has_specific_explanation(context,monkeypatch):
    client,path,_,sent=prepare(context,monkeypatch)
    with SessionLocal() as db:
        db.get(OrderEmailSettings,1).password_ciphertext=None;db.commit()
    status=client.get(path).json();assert not status['can_send'] and 'servidor, usuario y contraseña' in status['reason']
    with SessionLocal() as db:
        db.get(OrderEmailSettings,1).password_ciphertext=worker.cipher().encrypt(b'password').decode();db.commit()
    context[0].patch('/api/v1/account/order-emails',json={'email1_enabled':False,'email2_enabled':False})
    status=client.get(path).json();assert not status['can_send'] and 'correos destino marcados' in status['reason']
    assert sent==[]


def test_state_is_rechecked_on_post_and_queue_entry_is_reused(context,monkeypatch):
    client,path,oid,sent=prepare(context,monkeypatch)
    status=client.get(path).json()
    with SessionLocal() as db:
        order=db.get(Order,oid);order.estado_registro_exit='REGISTRADO';db.commit()
    response=client.post(path+'/resend',json={'expected_state_key':status['state_key']})
    assert response.status_code==409 and 'ha cambiado' in response.json()['detail'] and not sent
    current=client.get(path).json();assert current['state_key']!=status['state_key']
    assert client.post(path+'/resend',json={'expected_state_key':current['state_key']}).status_code==200
    assert len(sent)==1
    with SessionLocal() as db:
        jobs=list(db.scalars(select(OrderEmailDelivery).where(OrderEmailDelivery.order_id==oid)))
        assert len(jobs)==2 and jobs[-1].status=='SENT','Manual sending reuses the automatic pending notice'


def test_uncertain_requires_explicit_retry_and_smtp_error_is_sanitized(context,monkeypatch):
    client,path,oid,sent=prepare(context,monkeypatch)
    with SessionLocal() as db:
        latest(db).status='UNCERTAIN';db.commit()
    status=client.get(path).json();assert status['requires_confirmation']
    assert client.post(path+'/resend',json={'expected_state_key':status['state_key']}).status_code==409
    assert sent==[]
    def fail(config,password,message,phase):
        phase[0]='AUTH';raise smtplib.SMTPAuthenticationError(535,b'Credentials rejected: test-password first@example.test')
    monkeypatch.setattr(worker,'send_message',fail)
    result=client.post(path+'/resend',json={'expected_state_key':status['state_key'],'confirm_uncertain':True})
    assert result.status_code==502,result.text
    assert '535' in result.json()['detail'] and 'AUTH' in result.json()['detail']
    assert 'test-password' not in result.text and 'first@example.test' not in result.text
    assert client.get(path).json()['status']=='RETRY'


def test_customer_outside_delegation_and_busy_worker_are_blocked(context,monkeypatch):
    client,path,oid,sent=prepare(context,monkeypatch)
    assert context[0].get(path).status_code==403
    assert context[0].post(path+'/resend',json={'expected_state_key':'PENDIENTE'}).status_code==403
    @contextmanager
    def busy():yield False
    monkeypatch.setattr(resend_module,'delivery_lock',busy)
    assert client.post(path+'/resend',json={'expected_state_key':'PENDIENTE'}).status_code==409
    assert sent==[]
    with SessionLocal() as db:
        order=db.get(Order,oid);order.company_code=123456;order.delegation_code='FORBIDDEN';db.commit()
    assert client.get(path).status_code==404


def test_history_keeps_sanitized_failed_attempt_after_success(context,monkeypatch):
    client,path,oid,sent=prepare(context,monkeypatch)
    current=client.get(path).json()
    def fail(config,password,message,phase):
        phase[0]='AUTH';raise smtplib.SMTPAuthenticationError(535,b'test-password first@example.test AUTH rejected')
    monkeypatch.setattr(worker,'send_message',fail)
    assert client.post(path+'/resend',json={'expected_state_key':current['state_key']}).status_code==502
    monkeypatch.setattr(worker,'send_message',lambda config,password,message,phase:sent.append(message))
    assert client.post(path+'/resend',json={'expected_state_key':current['state_key']}).status_code==200
    history=client.get(path+'/history')
    assert history.status_code==200,history.text
    assert 'no-store' in history.headers['cache-control']
    data=history.json()
    assert data['deliveries'][0]['status']=='SENT'
    assert data['deliveries'][0]['attempts']==2
    assert data['deliveries'][0]['completed_slots']==['email1']
    assert any(row['status']=='SENT' and row['mode']=='MANUAL' for row in data['events'])
    failure=next(row for row in data['events'] if row['status']=='RETRY')
    assert failure['diagnostic']['smtp_code']==535
    assert failure['diagnostic']['phase']=='AUTH'
    assert 'test-password' not in history.text and 'first@example.test' not in history.text
    assert 'tracking_token_ciphertext' not in history.text and 'payload' not in history.text
    # No provider access is needed to read a previously saved result.
    monkeypatch.setattr(resend_module,'inspect',lambda *args:(_ for _ in ()).throw(RuntimeError('EXIT offline')))
    assert client.get(path+'/history').status_code==200
    assert len(sent)==1


def test_history_logs_unselected_state_without_generating_email(context,monkeypatch):
    client,path,oid,sent=prepare(context,monkeypatch)
    with SessionLocal() as db:
        config=db.get(OrderEmailSettings,1);config.configuration={**config.configuration,'selected_states':[]}
        order=db.get(Order,oid);order.estado_registro_exit='REGISTRADO';db.commit()
    history=client.get(path+'/history').json()
    skipped=next(row for row in history['events'] if row['status']=='SKIPPED')
    assert 'no está configurado' in skipped['reason']
    assert skipped['state_label']=='En procesamiento'
    assert len(history['deliveries'])==1 and sent==[]
    assert context[0].get(path+'/history').status_code==403
    with SessionLocal() as db:
        order=db.get(Order,oid);order.company_code=123456;order.delegation_code='FORBIDDEN';db.commit()
    assert client.get(path+'/history').status_code==404


def test_history_get_is_read_only_and_limit_is_validated(context,monkeypatch):
    from app.models import AuditEvent
    client,path,oid,sent=prepare(context,monkeypatch)
    with SessionLocal() as db:
        before=len(list(db.scalars(select(AuditEvent).where(AuditEvent.action=='ORDER_EMAIL_LOG'))))
    for _ in range(3):assert client.get(path+'/history?limit=1').status_code==200
    assert client.get(path+'/history?limit=101').status_code==422
    with SessionLocal() as db:
        assert len(list(db.scalars(select(AuditEvent).where(AuditEvent.action=='ORDER_EMAIL_LOG'))))==before
    assert sent==[]
