from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import OrderEmailSettings, OperatorAccess, User
from app import order_email_settings as mail
from sqlalchemy import select
from app.bootstrap import main as bootstrap
bootstrap()
PATH='/api/v1/store/order-email-settings'


def login(email='operador@bermudez.test'):
    client=TestClient(app)
    assert client.post('/api/v1/auth/login',json={'email':email,'password':'123456'}).status_code==200
    return client


@pytest.fixture(autouse=True)
def clean():
    with SessionLocal() as db:
        row=db.get(OrderEmailSettings,1)
        if row:db.delete(row);db.commit()
    yield
    with SessionLocal() as db:
        row=db.get(OrderEmailSettings,1)
        if row:db.delete(row);db.commit()


def test_permissions_and_defaults():
    assert TestClient(app).get(PATH).status_code==401
    assert login('compras001@cliente.test').get(PATH).status_code==403
    client=login();data=client.get(PATH).json()
    assert data['sender_email']=='info@bermudezulloa.es'
    assert data['automatic_dispatch_available'] is True
    assert data['automatic_enabled'] is False
    assert data['password_configured'] is False
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email=='operador@bermudez.test'))
        previous=db.get(OperatorAccess,user.id)
        if previous:
            original=dict(previous.permissions);previous.permissions={**original,'settings':False}
        else:db.add(OperatorAccess(user_id=user.id,exit_code='mail-settings-test',permissions={'settings':False}))
        db.commit()
        try:
            assert client.get(PATH).status_code==403
            assert client.put(PATH,json={}).status_code==403
            assert client.post(PATH+'/test',json={'recipient':'test@example.test'}).status_code==403
        finally:
            row=db.get(OperatorAccess,user.id)
            if previous:row.permissions=original
            else:db.delete(row)
            db.commit()


def test_encrypted_password_retained_replaced_and_cleared():
    client=login()
    result=client.put(PATH,json={'password':'a-secret-password','smtp_host':'smtp.example.test'});assert result.status_code==200
    assert result.json()['password_configured'] is True
    assert 'a-secret-password' not in result.text
    assert 'password_ciphertext' not in result.text
    with SessionLocal() as db:
        encrypted=db.get(OrderEmailSettings,1).password_ciphertext
        assert 'a-secret-password' not in encrypted
        assert mail.cipher().decrypt(encrypted.encode()).decode()=='a-secret-password'
    assert client.put(PATH,json={'sender_name':'Nueva cuenta'}).status_code==200
    with SessionLocal() as db:assert db.get(OrderEmailSettings,1).password_ciphertext==encrypted
    assert client.put(PATH,json={'password':'replacement'}).status_code==200
    with SessionLocal() as db:assert mail.cipher().decrypt(db.get(OrderEmailSettings,1).password_ciphertext.encode()).decode()=='replacement'
    assert client.put(PATH,json={'clear_password':True,'password':'conflict'}).status_code==422
    assert client.put(PATH,json={'clear_password':True}).json()['password_configured'] is False


@pytest.mark.parametrize('data',[
    {'sender_email':'bad\nBcc: someone@example.test'}, {'reply_to':'invalid'},
    {'sender_name':'Header\r\ninjected'}, {'smtp_host':'https://smtp.example.test/path'},
    {'smtp_port':0},{'smtp_port':True},{'security':'NONE'},
    {'portal_url':'http://example.test'}, {'portal_url':'https://user:pass@example.test'},
    {'selected_states':['INTERNAL_ONLY']},{'enabled':True},
])
def test_invalid_configuration(data):
    assert login().put(PATH,json=data).status_code==422


def test_test_message_tls_ssl_and_safe_errors(monkeypatch):
    client=login()
    assert client.post(PATH+'/test',json={'recipient':'test@example.test'}).status_code==409
    assert client.put(PATH,json={'smtp_host':'smtp.example.test','password':'secret'}).status_code==200
    smtp=MagicMock();smtp.__enter__.return_value=smtp;smtp.send_message.return_value={}
    connect=MagicMock(return_value=smtp);monkeypatch.setattr(mail.smtplib,'SMTP',connect)
    result=client.post(PATH+'/test',json={'recipient':'receiver@example.test'});assert result.status_code==200
    smtp.starttls.assert_called_once();smtp.login.assert_called_once_with('info@bermudezulloa.es','secret')
    message=smtp.send_message.call_args.args[0]
    assert message['To']=='receiver@example.test'
    assert message['Reply-To']=='info@bermudezulloa.es'
    assert 'info@bermudezulloa.es' in message['From']
    assert 'secret' not in str(message)
    assert connect.call_args.kwargs['timeout']==15
    assert client.post(PATH+'/test',json={'recipient':'bad\nBcc: x@example.test'}).status_code==422
    smtp.reset_mock();ssl_connect=MagicMock(return_value=smtp);monkeypatch.setattr(mail.smtplib,'SMTP_SSL',ssl_connect)
    client.put(PATH,json={'smtp_host':'smtp.example.test','security':'SSL','smtp_port':465})
    assert client.post(PATH+'/test',json={'recipient':'receiver@example.test'}).status_code==200
    smtp.starttls.assert_not_called();assert ssl_connect.called
    smtp.send_message.side_effect=mail.smtplib.SMTPException('secret from remote server')
    failure=client.post(PATH+'/test',json={'recipient':'receiver@example.test'})
    assert failure.status_code==502 and 'secret' not in failure.text
    smtp.send_message.side_effect=None;smtp.send_message.return_value={'receiver@example.test':(550,b'no')}
    assert client.post(PATH+'/test',json={'recipient':'receiver@example.test'}).status_code==502


@pytest.mark.parametrize('phase,exception,code',[
    ('CONNECT', mail.socket.gaierror(-2,'DNS unavailable'), 'HOST_NOT_FOUND'),
    ('CONNECT', ConnectionRefusedError('Connection refused'), 'CONNECTION_REFUSED'),
    ('CONNECT', TimeoutError('timed out'), 'TIMEOUT'),
    ('TLS', mail.ssl.SSLCertVerificationError('invalid certificate'), 'CERTIFICATE_INVALID'),
    ('TLS', mail.ssl.SSLError('wrong TLS version'), 'TLS_FAILED'),
    ('TLS', mail.smtplib.SMTPNotSupportedError('STARTTLS missing'), 'STARTTLS_UNAVAILABLE'),
    ('AUTH', mail.smtplib.SMTPNotSupportedError('AUTH missing'), 'AUTH_UNAVAILABLE'),
    ('AUTH', mail.smtplib.SMTPAuthenticationError(535,b'5.7.139 Authentication unsuccessful'), 'AUTH_REJECTED'),
    ('SEND', mail.smtplib.SMTPSenderRefused(550,b'5.7.60 SendAs denied','sender@example.test'), 'SENDER_REJECTED'),
    ('SEND', mail.smtplib.SMTPRecipientsRefused({'receiver@example.test':(550,b'5.1.1 Mailbox not found')}), 'RECIPIENT_REJECTED'),
    ('SEND', mail.smtplib.SMTPDataError(554,b'Message rejected'), 'MESSAGE_REJECTED'),
])
def test_smtp_diagnosis_exposes_library_response_and_records_safe_log(monkeypatch,caplog,phase,exception,code):
    from app.models import AuditEvent
    client=login();client.put(PATH,json={'smtp_host':'smtp.example.test','password':'private-credential'})
    smtp=MagicMock();smtp.__enter__.return_value=smtp;smtp.send_message.return_value={}
    connect=MagicMock(return_value=smtp);monkeypatch.setattr(mail.smtplib,'SMTP',connect)
    if phase=='CONNECT':connect.side_effect=exception
    elif phase=='TLS':smtp.starttls.side_effect=exception
    elif phase=='AUTH':smtp.login.side_effect=exception
    else:smtp.send_message.side_effect=exception
    result=client.post(PATH+'/test',json={'recipient':'receiver@example.test'})
    assert result.status_code==502 and result.headers['X-Mail-Error']==code
    detail=result.json()['detail'];assert f'Fase: {phase}' in detail and type(exception).__name__ in detail
    assert 'Referencia ' in detail and 'Respuesta:' in detail
    assert 'private-credential' not in detail+caplog.text
    assert 'receiver@example.test' not in detail+caplog.text
    with SessionLocal() as db:
        event=db.scalar(select(AuditEvent).where(AuditEvent.action=='ORDER_EMAIL_TEST_FAILED').order_by(AuditEvent.id.desc()))
        assert event.metadata_json['code']==code and event.metadata_json['phase']==phase
        assert event.metadata_json['reference'] in detail and event.metadata_json['response'] in detail
    if phase in {'CONNECT','TLS','AUTH'}:smtp.send_message.assert_not_called()


def test_library_response_redacts_password_encoded_auth_and_addresses():
    import base64,json
    password='very-private-password';username='b2b@example.test'
    config=mail.MailConfiguration(username=username,sender_email=username)
    encoded=base64.b64encode(('\0'+username+'\0'+password).encode()).decode()
    response=f'5.7.139 Authentication unsuccessful {password} {encoded} {username} receiver@example.test token=private-token'
    error=mail.smtplib.SMTPAuthenticationError(535,response.encode())
    log=mail.smtp_diagnostic(error,'AUTH',config,password,'receiver@example.test')
    value=json.dumps(log)
    assert log['smtp_code']==535 and '5.7.139 Authentication unsuccessful' in value
    for secret in [password,encoded,username,'receiver@example.test','private-token']:
        assert secret not in value
    assert len(log['response'])<=1500


def test_available_and_editor_states_match_workflow_and_upgrade_saved_configuration():
    from app.order_email_texts import STATES
    expected={'PENDIENTE','EN_PREPARACION','PENDIENTE_RECOGIDA_PARCIAL','PENDIENTE_RECOGIDA_TOTAL','ENTREGADO_PARCIAL','ENTREGADO_TOTAL','FACTURADO'}
    with SessionLocal() as db:
        saved=mail.MailConfiguration(smtp_host='smtp.example.test',username='b2b@example.test').model_dump()
        saved['selected_states']=list(expected)+['ELIMINADO_EN_EXIT']
        db.add(OrderEmailSettings(id=1,configuration=saved,password_ciphertext='preserved-cipher'));db.commit()
    result=login().get(PATH)
    assert result.status_code==200,result.text
    data=result.json()
    assert set(data['available_states'])==set(data['content_states'])==set(data['content_suggestions'])==expected
    assert data['available_states']['PENDIENTE']=='Pendiente'
    assert data['available_states']['EN_PREPARACION']=='En procesamiento'
    assert set(data['selected_states'])==expected
    assert data['smtp_host']=='smtp.example.test' and data['password_configured'] is True
    assert 'ELIMINADO_EN_EXIT' not in STATES
    assert login().get(PATH+'/preview?state=ELIMINADO_EN_EXIT').status_code==422
