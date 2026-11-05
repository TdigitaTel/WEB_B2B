from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import MagicMock
import pytest
from sqlalchemy import select, delete
from fastapi.testclient import TestClient
from app.main import app
from app import main, erp_db, order_email_events as events, order_pickups
from app.db import SessionLocal
from app.models import (Order, OrderItem, User, CustomerOrderEmailSetting as Choice,
                        OrderEmailCheckpoint as Checkpoint, OrderEmailDelivery as Delivery,
                        OrderEmailSettings, OrderTrackingLink)
from app.order_email_settings import cipher, MailConfiguration
from app.customer_order_email import destinations
from app.order_email_worker import deliver
from app.bootstrap import main as bootstrap
bootstrap()
PATH='/api/v1/account/order-emails'
CODE='CLI00001'


@pytest.fixture
def context(monkeypatch):
    customer={'erp_id':CODE,'legal_name':'Prueba','trade_name':'Prueba','email':'first@example.test',
              'email1':'first@example.test','email2':'second@example.test','web':'https://reference.example.test',
              'phone':'','billing_address':'','tax_id':'TEST','price_list':'','discount_pct':0}
    monkeypatch.setattr(main,'fetch_customer',lambda code:dict(customer,erp_id=code))
    client=TestClient(app)
    assert client.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'}).status_code==200
    with SessionLocal() as db:
        assert db.scalar(select(User).where(User.email=='compras001@cliente.test')).erp_customer_code==CODE
        db.execute(delete(Delivery));db.execute(delete(Checkpoint));db.execute(delete(Choice));db.execute(delete(OrderEmailSettings));db.commit()
    yield client,customer
    with SessionLocal() as db:
        db.execute(delete(Delivery));db.execute(delete(Checkpoint));db.execute(delete(Choice));db.execute(delete(OrderEmailSettings));db.commit()


def configure(db):
    db.add(OrderEmailSettings(id=1,configuration=MailConfiguration(automatic_enabled=True,smtp_host='smtp.example.test',username='sender@example.test',content={'show_link':False}).model_dump(),password_ciphertext=cipher().encrypt(b'test-password').decode()))
    db.commit()


def new_order(db,state='PENDIENTE'):
    user=db.scalar(select(User).where(User.email=='compras001@cliente.test'))
    order=Order(order_number='WEB-MAIL-'+uuid4().hex,user_id=user.id,customer_code=CODE,
                company_code=1,delegation_code='02',origen_pedido='B2B',estado_registro_exit=state)
    db.add(order);db.flush()
    db.add(OrderItem(order_id=order.id,sku='EMAIL-TEST',description='Material de prueba',quantity=1,unit='UD',unit_price=2,tax_rate=21,line_total=2))
    db.commit();return order


def latest(db):
    return db.scalar(select(Delivery).order_by(Delivery.id.desc()))


def test_live_fields_choices_and_reference_only(context):
    client,customer=context
    account=client.get('/api/v1/account').json()['customer']
    assert account['email1']==customer['email1'] and account['email2']==customer['email2']
    assert account['web']==customer['web']
    assert account['order_email_recipients']=={'email1_enabled':False,'email2_enabled':False}
    result=client.patch(PATH,json={'email1_enabled':True,'email2_enabled':False})
    assert result.status_code==200,result.text
    customer['email1']='updated@example.test';customer['email']=customer['email1']
    account=client.get('/api/v1/account').json()['customer']
    assert account['email1']=='updated@example.test'
    assert account['order_email_recipients']['email1_enabled'] is True
    assert destinations(account,account['order_email_recipients'])==[{'address':'updated@example.test','slots':['email1']}]
    assert client.patch(PATH,json={'email1_enabled':True,'email2_enabled':False,'customer_code':'OTHER'}).status_code==422
    assert client.patch(PATH,json={'email1_enabled':'false','email2_enabled':False}).status_code==422
    customer['email2']='not an email'
    assert client.patch(PATH,json={'email1_enabled':True,'email2_enabled':True}).status_code==422


def test_permissions(context):
    client,customer=context
    assert TestClient(app).patch(PATH,json={}).status_code==401
    with SessionLocal() as db:
        parent=db.scalar(select(User).where(User.email=='compras001@cliente.test'))
        parent.can_manage_preferences=False;db.commit()
    try:
        assert client.patch(PATH,json={'email1_enabled':True,'email2_enabled':False}).status_code==403
    finally:
        with SessionLocal() as db:
            db.scalar(select(User).where(User.email=='compras001@cliente.test')).can_manage_preferences=True;db.commit()
    operator=TestClient(app);operator.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'})
    assert operator.patch(PATH,json={'email1_enabled':True,'email2_enabled':False}).status_code==403


def test_transactional_queue_no_history_no_duplicates_and_complete_materials(context):
    client,_=context
    with SessionLocal() as db:
        configure(db);existing=new_order(db)
        oid=existing.id
    assert client.patch(PATH,json={'email1_enabled':True,'email2_enabled':True}).status_code==200
    with SessionLocal() as db:
        assert latest(db) is None,'Selecting destinations must not send the existing order'
        order=db.get(Order,oid);order.estado_registro_exit='REGISTRADO';db.commit()
        job=latest(db);assert job.state=='EN_PREPARACION'
        count=len(list(db.scalars(select(Delivery))))
        order.notes='Only a note';db.commit()
        assert len(list(db.scalars(select(Delivery))))==count
        order.estado_registro_exit='FACTURADO';db.flush();db.rollback()
        assert len(list(db.scalars(select(Delivery))))==count,'Rollback must also roll back notifications'
        new_order(db)
        assert latest(db).payload['items'][0]['description']=='Material de prueba'


def test_destination_read_at_send_and_individual_private_messages(context):
    client,customer=context
    client.patch(PATH,json={'email1_enabled':True,'email2_enabled':True})
    with SessionLocal() as db:
        configure(db);new_order(db)
        customer['email1']='current@example.test';customer['email']='current@example.test'
        sent=[]
        deliver(db,latest(db),lambda code:customer,lambda config,password,message,phase:sent.append(message))
        assert [str(message['To']) for message in sent]==['current@example.test','second@example.test']
        assert all(message.get('Cc') is None for message in sent)
        assert latest(db).status=='SENT'
        assert 'compras001@cliente.test' not in str(sent)


def test_deduplicate_addresses_and_disable_at_send(context):
    client,customer=context
    client.patch(PATH,json={'email1_enabled':True,'email2_enabled':True})
    with SessionLocal() as db:
        configure(db);new_order(db);customer['email2']=customer['email1'].upper();sent=[]
        deliver(db,latest(db),lambda code:customer,lambda *args:sent.append(args))
        assert len(sent)==1
        new_order(db);choice=db.get(Choice,CODE);choice.email1_enabled=choice.email2_enabled=False;db.commit()
        deliver(db,latest(db),lambda code:pytest.fail('Must not even read contacts'),lambda *args:pytest.fail('Must not send'))
        assert latest(db).status=='CANCELLED'


def test_retry_does_not_resend_successful_recipient_and_ambiguous_send_stops(context):
    client,customer=context
    client.patch(PATH,json={'email1_enabled':True,'email2_enabled':True})
    with SessionLocal() as db:
        configure(db);new_order(db);sent=[]
        def fail_second(config,password,message,phase):
            if sent: raise ConnectionRefusedError('No connection')
            sent.append(str(message['To']))
        job=latest(db);deliver(db,job,lambda code:customer,fail_second)
        assert job.status=='RETRY' and job.completed_slots==['email1']
        deliver(db,job,lambda code:customer,lambda c,p,m,phase:sent.append(str(m['To'])))
        assert sent==[customer['email1'],customer['email2']]
        new_order(db);job=latest(db)
        def uncertain(c,p,m,phase):
            phase[0]='SEND';raise TimeoutError('No SMTP acceptance reply')
        deliver(db,job,lambda code:customer,uncertain)
        assert job.status=='UNCERTAIN'
        assert 'test-password' not in str(job.diagnostic)


def test_off_global_or_no_flags_never_enqueues(context):
    client,_=context
    with SessionLocal() as db:
        configure(db);new_order(db);assert latest(db) is None
    client.patch(PATH,json={'email1_enabled':True,'email2_enabled':False})
    with SessionLocal() as db:
        config=db.get(OrderEmailSettings,1);config.configuration={**config.configuration,'automatic_enabled':False};db.commit()
        new_order(db);assert latest(db) is None


def test_preparation_summary_changes_trigger_notice_without_raw_state_change(context,monkeypatch):
    client,_=context
    client.patch(PATH,json={'email1_enabled':True,'email2_enabled':False})
    with SessionLocal() as db:
        configure(db);order=new_order(db,'REGISTRADO')
        monkeypatch.setattr(order_pickups,'summary',lambda *args:{'state':'PENDIENTE_RECOGIDA_TOTAL','total_materials':1,'prepared_materials':1,'delivered_materials':0})
        order.pickup_managed_at=datetime.now(timezone.utc);db.commit()
        assert latest(db).state=='PENDIENTE_RECOGIDA_TOTAL'


def test_sqlserver_uses_email1_email2_web_and_no_cached_address(monkeypatch):
    connection=MagicMock();connection.__enter__.return_value=connection
    cursor=connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value=[{'COLUMN_NAME':name} for name in ['CodigoCliente','RazonSocial','Email1','Email2','Web']]
    cursor.fetchone.return_value={'code':'00004','legal_name':'Prueba','email':'one@example.test','email2':'two@example.test','web':'www.example.test'}
    monkeypatch.setattr(erp_db,'connect_sqlserver',lambda:connection)
    result=erp_db.fetch_customer('00004')
    query,params=cursor.execute.call_args.args
    assert 'c.[Email1] AS [email]' in query and 'c.[Email2] AS [email2]' in query and 'c.[Web] AS [web]' in query
    assert params==('00004',)
    assert result['email1']=='one@example.test' and result['email2']=='two@example.test'
    cursor.fetchone.return_value={**cursor.fetchone.return_value,'email':'updated@example.test'}
    assert erp_db.fetch_customer('00004')['email1']=='updated@example.test'


def test_reactivation_cancels_old_queued_messages(context):
    client,_=context
    client.patch(PATH,json={'email1_enabled':True,'email2_enabled':False})
    with SessionLocal() as db:
        configure(db);order=new_order(db);job_id=latest(db).id
    client.patch(PATH,json={'email1_enabled':False,'email2_enabled':False})
    client.patch(PATH,json={'email1_enabled':True,'email2_enabled':False})
    with SessionLocal() as db:
        assert db.get(Delivery,job_id).status=='CANCELLED'
        assert len(list(db.scalars(select(Delivery))))==1


def test_global_activation_starts_from_current_state(context):
    client,_=context
    client.patch(PATH,json={'email1_enabled':True,'email2_enabled':False})
    with SessionLocal() as db:
        configure(db);new_order(db);old_id=latest(db).id
        config=db.get(OrderEmailSettings,1);config.configuration={**config.configuration,'automatic_enabled':False};db.commit()
    operator=TestClient(app);operator.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'})
    response=operator.put('/api/v1/store/order-email-settings',json={'automatic_enabled':True,'smtp_host':'smtp.example.test'})
    assert response.status_code==200,response.text
    with SessionLocal() as db:
        assert db.get(Delivery,old_id).status=='CANCELLED'
        assert len(list(db.scalars(select(Delivery))))==1
