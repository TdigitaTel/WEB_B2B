import io
from copy import deepcopy
from uuid import uuid4
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import select,delete
from app.main import app
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.models import (User,OperatorAccess,IncidentType,IncidentSequence,LogisticsIncident,IncidentEvent,IncidentAttachment,IncidentEmail,OrderEmailSettings)
from app.auth import hash_password
from app.operator_permissions import MODULES

bootstrap();BASE='/api/v1/store/incidents'

def login(email):
    client=TestClient(app)
    assert client.post('/api/v1/auth/login',json={'email':email,'password':'123456'}).status_code==200
    return client

@pytest.fixture
def setup(monkeypatch):
    import app.incidents as module
    # Current branch's source lives in SQL Server; tests never connect to EXIT or SMTP.
    from app.seed import STORES
    from app.delegations import Delegation
    delegations=[Delegation(1,code,name,'',code,name) for code,name in [('01','A Coruña'),('02','Ferrol'),('00','Almeiras')]]
    monkeypatch.setattr(module,'fetch_delegations',lambda:delegations)
    monkeypatch.setattr(module,'stock_for',lambda codes,delegation:{code:10 for code in codes})
    accounts=[]
    with SessionLocal() as db:
        for model in (IncidentEmail,IncidentAttachment,IncidentEvent,LogisticsIncident,IncidentType,IncidentSequence):db.execute(delete(model))
        for prefix,delegation,permissions in [('creator','01',{'incident_create':True}),('worker','01',{'incident_work':True,'incident_approve':True}),('other','02',{'incident_create':True,'incident_work':True})]:
            email=f'incident-{prefix}-{uuid4().hex[:8]}@example.test';account=User(email=email,full_name=prefix,role='OPERADOR_TIENDA',password_hash=hash_password('123456'),company_code=1,delegation_code=delegation)
            db.add(account);db.flush();db.add(OperatorAccess(user_id=account.id,exit_code='INC-'+str(account.id),permissions=permissions));accounts.append((account.id,email))
        db.commit()
    admin=login('admin@bermudez.test');clients=[login(email) for _,email in accounts]
    yield admin,clients,accounts
    with SessionLocal() as db:
        for model in (IncidentEmail,IncidentAttachment,IncidentEvent,LogisticsIncident,IncidentType,IncidentSequence):db.execute(delete(model))
        for user_id,_ in accounts:
            db.get(User,user_id).active=False
        db.commit()


def configure(admin,accounts,kind='REPLENISHMENT',mode='OPTIONAL',scope='GENERAL'):
    result=admin.get(BASE+'/options');assert result.status_code==200,result.text
    saved=next(row for row in result.json()['types'] if row['configuration']['code']==kind)
    cfg=saved['configuration'];cfg['active']=True;cfg['file_mode']=mode
    for step in cfg['steps']:
        if step['kind']=='CONFIRM':continue
        step['scope']=scope;target={'user_id':accounts[1][0],'email':accounts[1][1]}
        if scope=='GENERAL':step['general']=target
        else:step['delegations']={'1:01':target}
    response=admin.put(BASE+'/types/'+kind,json=saved)
    assert response.status_code==200,response.text
    return response.json()


def data(kind='REPLENISHMENT'):
    return {'type_code':kind,'delegation_id':'1:01','destination_id':'1:02' if kind=='TRANSFER' else None,'document':'PED-123','reason':'Falta de material','description':'Necesitamos corregir esta diferencia','lines':[{'sku':'91463E','description':'Material de prueba','unit':'PZ','expected':10,'actual':5,'counted':5,'location':'A-01'}]}


def create(client,kind='REPLENISHMENT'):
    response=client.post(BASE,json=data(kind));assert response.status_code==201,response.text;return response.json()

def action(client,row,kind='ADVANCE',**extra):return client.post(BASE+'/'+row['id']+'/actions',json={'version':row['version'],'action':kind,'note':'Actuación comprobada',**extra})


def test_permissions_workflow_assignment_closure_and_stale_edits(setup):
    admin,(creator,worker,other),accounts=setup
    assert creator.get('/api/v1/store/replenishment/options').status_code==403
    assert creator.get(BASE+'/options').status_code==200
    assert creator.put(BASE+'/types/SALE',json={}).status_code in (403,422)
    configure(admin,accounts)
    row=create(creator)
    assert row['number'].startswith('INC-') and row['status']=='DRAFT' and not row['emails']
    assert other.get(BASE+'/'+row['id']).status_code==404
    assert other.get(BASE+'?box=ALL').json()['total']==0
    assert action(worker,row,'SUBMIT').status_code==404
    response=action(creator,row,'SUBMIT');assert response.status_code==200,response.text
    current=response.json();assert current['assignee_id']==accounts[1][0] and current['emails'][0]['status']=='PENDING'
    assert worker.get(BASE+'?box=ASSIGNED').json()['total']==1
    assert action(creator,current).status_code==403
    assert action(worker,row).status_code==409
    # Ordinary comments cannot supersede the outstanding assignment email.
    current=action(worker,current,'COMMENT').json()
    result=action(worker,current);assert result.status_code==200,result.text;current=result.json()
    current=action(worker,current).json();assert current['assignee_id']==accounts[0][0] and current['stage_kind']=='CONFIRM'
    assert current['can_work'] is False  # Response belongs to the previous worker.
    current=creator.get(BASE+'/'+row['id']).json();assert current['can_work']
    closed=action(creator,current).json();assert closed['status']=='CLOSED' and closed['resolution_document']==''
    assert action(creator,closed).status_code==403
    assert len(closed['events'])>=7


@pytest.mark.parametrize('mode',['FORBIDDEN','OPTIONAL','REQUIRED'])
def test_attachment_configuration_scoping_and_required_file_gate(setup,mode):
    admin,(creator,worker,other),accounts=setup
    configure(admin,accounts,mode=mode)
    row=create(creator);path=BASE+'/'+row['id']
    pdf={'file':('recuento.pdf',b'%PDF-1.4\n1 0 obj\nendobj\n%%EOF','application/pdf')}
    if mode=='REQUIRED':assert action(creator,row,'SUBMIT').status_code==409
    uploaded=creator.post(path+'/files',params={'version':row['version']},files=pdf)
    if mode=='FORBIDDEN':
        assert uploaded.status_code==403
        assert action(creator,row,'SUBMIT').status_code==200
        return
    assert uploaded.status_code==201,uploaded.text
    row=uploaded.json();file_id=row['files'][0]['id']
    assert other.get(path+'/files/'+file_id).status_code==404
    response=creator.get(path+'/files/'+file_id)
    assert response.status_code==200 and response.headers['x-content-type-options']=='nosniff'
    assert 'attachment' in response.headers['content-disposition']
    assert creator.post(path+'/files',params={'version':row['version']},files={'file':('danger.pdf',b'<script>bad</script>','application/pdf')}).status_code==422
    assert creator.post(path+'/files',params={'version':row['version']},files={'file':('test.exe',b'bad','application/octet-stream')}).status_code==422
    assert creator.post(path+'/files',params={'version':row['version']},files={'file':('large.pdf',b'0'*(4*1024*1024+1),'application/pdf')}).status_code==413
    assert action(creator,row,'SUBMIT').status_code==200


def test_inventory_capture_authorization_and_execution_evidence(setup):
    admin,(creator,worker,other),accounts=setup
    configure(admin,accounts,'INVENTORY')
    row=create(creator,'INVENTORY')
    assert row['lines'][0]['system_stock']==10 and row['lines'][0]['counted']==5 and row['lines'][0]['delta']==-5
    assert row['lines'][0]['stock_source']=='EXIT'
    current=action(creator,row,'SUBMIT').json();current=action(worker,current).json()
    assert current['stage_kind']=='APPROVE'
    with SessionLocal() as db:
        access=db.get(OperatorAccess,accounts[1][0]);access.permissions={**access.permissions,'incident_approve':False};db.commit()
    assert action(worker,current).status_code==403
    with SessionLocal() as db:
        access=db.get(OperatorAccess,accounts[1][0]);access.permissions={**access.permissions,'incident_approve':True};db.commit()
    current=action(worker,current).json();assert current['stage_kind']=='EXECUTE'
    assert action(worker,current).status_code==422
    assert action(worker,current,document='AJ-2026-001').status_code==422
    result=action(worker,current,document='AJ-2026-001',verification_note='Comprobados el recuento y los movimientos posteriores en EXIT')
    assert result.status_code==200,result.text
    assert result.json()['resolution_document']=='AJ-2026-001'


def test_return_correction_flow_snapshot_and_delegation_routing(setup):
    admin,(creator,worker,other),accounts=setup
    saved=configure(admin,accounts,scope='DELEGATION')
    row=create(creator)
    saved['configuration']['steps'][0]['name']='Una etapa nueva'
    assert admin.put(BASE+'/types/REPLENISHMENT',json=saved).status_code==200
    current=action(creator,row,'SUBMIT').json();assert current['stage']=='Validación de delegación'
    current=action(worker,current,'RETURN').json();assert current['status']=='DRAFT' and current['assignee_id']==accounts[0][0]
    assert current['emails'][-1]['stage']=='Corregir borrador'
    correction={**data(),'version':current['version'],'description':'Cantidad corregida'}
    correction['lines'][0]['expected']=15
    response=creator.put(BASE+'/'+row['id'],json=correction);assert response.status_code==200,response.text
    corrected=response.json();assert corrected['lines'][0]['expected']==15
    assert corrected['workflow']['steps'][0]['name']=='Validación de delegación'
    history=next(event for event in corrected['events'] if event['action']=='CORRECTED')
    assert history['detail']['previous']['lines'][0]['expected']==10
    assert history['detail']['changes']['lines'][0]['expected']==15
    response=other.post(BASE,json={**data(),'delegation_id':'1:01'});assert response.status_code==403


def test_incident_email_worker_status_retries_and_no_stale_sends(setup,monkeypatch):
    import app.incident_mail as mail
    from app.order_email_settings import MailConfiguration,cipher
    admin,(creator,worker,other),accounts=setup
    configure(admin,accounts);row=create(creator);current=action(creator,row,'SUBMIT').json()
    fake=type('SMTP',(),{'password_ciphertext':cipher().encrypt(b'not-a-real-password').decode()})()
    config=MailConfiguration(smtp_host='smtp.example.test',username='test',automatic_enabled=False)
    monkeypatch.setattr(mail,'configuration',lambda db:(fake,config))
    sent=[]
    with SessionLocal() as db:
        job=db.scalar(select(IncidentEmail).where(IncidentEmail.incident_id==row['id']))
        mail.deliver(db,job,lambda config,password,message,phase:sent.append(message))
        assert job.status=='SENT' and len(sent)==1 and '#incident='+row['id'] in sent[0].get_content()
    assert action(worker,current,'RESEND_EMAIL',note='').status_code==409
    assert action(worker,current,'RESEND_EMAIL',note='Destinatario confirma que no lo recibió').status_code==200
    current=worker.get(BASE+'/'+row['id']).json();current=action(worker,current).json()
    with SessionLocal() as db:
        stale=db.scalars(select(IncidentEmail).where(IncidentEmail.incident_id==row['id']).order_by(IncidentEmail.id)).first()
        mail.deliver(db,stale,lambda *args:pytest.fail('Do not send an obsolete assignment'))
        assert stale.status=='SUPERSEDED'


def test_stage_required_files_and_transfer_origin_destination(setup):
    admin,(creator,worker,other),accounts=setup
    saved=configure(admin,accounts,'TRANSFER')
    cfg=saved['configuration']
    cfg['steps'][0]['scope']='ORIGIN';cfg['steps'][0]['general']=None;cfg['steps'][0]['delegations']={'1:01':{'user_id':accounts[1][0],'email':accounts[1][1]}}
    cfg['steps'][1]['scope']='DESTINATION';cfg['steps'][1]['general']=None;cfg['steps'][1]['delegations']={'1:02':{'user_id':accounts[2][0],'email':accounts[2][1]}};cfg['steps'][1]['files']='REQUIRED'
    response=admin.put(BASE+'/types/TRANSFER',json=saved);assert response.status_code==200,response.text
    row=create(creator,'TRANSFER');current=action(creator,row,'SUBMIT').json()
    assert current['assignee_id']==accounts[1][0]
    current=action(worker,current).json();assert current['assignee_id']==accounts[2][0]
    assert action(other,current).status_code==409
    response=other.post(BASE+'/'+row['id']+'/files',params={'version':current['version']},files={'file':('recepcion.pdf',b'%PDF-1.4\n%%EOF','application/pdf')})
    assert response.status_code==201,response.text
    assert action(other,response.json()).status_code==200


def test_unconfigured_routing_and_configuration_permission(setup):
    admin,(creator,worker,other),accounts=setup
    payload=data()
    assert creator.post(BASE,json=payload).status_code==409
    saved=configure(admin,accounts,scope='DELEGATION')
    assert creator.put(BASE+'/types/REPLENISHMENT',json=saved).status_code==403
    assert login('operador@bermudez.test').get(BASE+'/options').status_code==403
    # An enabled flow may deliberately cover one delegation, but another cannot enter it.
    other_payload={**payload,'delegation_id':'1:02'}
    response=other.post(BASE,json=other_payload);assert response.status_code==201,response.text
    assert action(other,response.json(),'SUBMIT').status_code==409
    duplicate=deepcopy(saved);duplicate['configuration']['file_mode']='FORBIDDEN';duplicate['configuration']['steps'][0]['files']='REQUIRED'
    assert admin.put(BASE+'/types/REPLENISHMENT',json=duplicate).status_code==422


def test_manual_inventory_and_missing_mail_configuration_are_explicit(setup,monkeypatch):
    import app.incident_mail as mail
    admin,(creator,worker,other),accounts=setup
    configure(admin,accounts,'INVENTORY')
    body=data('INVENTORY');body['lines'][0].update({'manual_stock':True,'system_stock':10,'manual_reason':''})
    assert creator.post(BASE,json=body).status_code==422
    body['lines'][0]['manual_reason']='Stock anotado en el terminal antes de la caída de conexión'
    response=creator.post(BASE,json=body);assert response.status_code==201,response.text
    row=response.json();assert row['lines'][0]['stock_source']=='MANUAL' and row['lines'][0]['delta']==-5
    action(creator,row,'SUBMIT')
    monkeypatch.setattr(mail,'configuration',lambda db:(None,None))
    with SessionLocal() as db:
        job=db.scalar(select(IncidentEmail).where(IncidentEmail.incident_id==row['id']))
        mail.deliver(db,job,lambda *a:pytest.fail('SMTP must not run without configuration'))
        assert job.status=='NOT_CONFIGURED' and job.attempts==0
    assert worker.get(BASE+'/'+row['id']).json()['emails'][0]['status']=='NOT_CONFIGURED'


def test_order_lookup_loads_existing_lines_and_respects_delegation(setup):
    from app.models import Order,OrderItem
    from datetime import datetime,timezone
    admin,(creator,worker,other),accounts=setup
    reference='INC-LOOKUP-'+uuid4().hex[:12]
    with SessionLocal() as db:
        order=Order(order_number=reference,company_code=1,delegation_code='01')
        db.add(order);db.flush()
        for sku,removed in [('VALID',False),('REMOVED',True)]:
            db.add(OrderItem(order_id=order.id,sku=sku,description='Material '+sku,unit='PZ',quantity=10,unit_price=1,tax_rate=21,line_total=10,exit_removed_at=datetime.now(timezone.utc) if removed else None))
        db.commit()
    response=creator.get(BASE+'/documents',params={'delegation_id':'1:01','q':reference})
    assert response.status_code==200,response.text
    assert [line['sku'] for line in response.json()['items'][0]['lines']]==['VALID']
    assert other.get(BASE+'/documents',params={'delegation_id':'1:01','q':reference}).status_code==403


def test_uncertain_mail_is_not_retried_automatically(setup,monkeypatch):
    import app.incident_mail as mail
    from app.order_email_settings import MailConfiguration,cipher
    admin,(creator,worker,other),accounts=setup
    configure(admin,accounts);row=create(creator);action(creator,row,'SUBMIT')
    fake=type('SMTP',(),{'password_ciphertext':cipher().encrypt(b'fake-password').decode()})()
    monkeypatch.setattr(mail,'configuration',lambda db:(fake,MailConfiguration(smtp_host='smtp.example.test',username='test')))
    def uncertain(config,password,message,phase):
        phase[0]='SEND';raise TimeoutError('Respuesta SMTP no recibida')
    with SessionLocal() as db:
        job=db.scalar(select(IncidentEmail).where(IncidentEmail.incident_id==row['id']))
        mail.deliver(db,job,uncertain)
        assert job.status=='UNCERTAIN' and job.attempts==1
        monkeypatch.setattr(mail,'send_message',lambda *args:pytest.fail('Uncertain delivery must be reviewed, not automatically resent'))
        mail.run_pending(db)
        db.refresh(job);assert job.status=='UNCERTAIN' and job.attempts==1
