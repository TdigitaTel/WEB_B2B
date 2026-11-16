import io
from copy import deepcopy
from datetime import datetime,timezone,timedelta
from uuid import uuid4
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import select,delete
from app.main import app
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.models import (User,OperatorAccess,IncidentType,IncidentSequence,LogisticsIncident,IncidentEvent,IncidentAttachment,IncidentEmail,OrderEmailSettings,IncidentFlowVersion,IncidentFlowChange)
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
        for model in (IncidentEmail,IncidentAttachment,IncidentEvent,LogisticsIncident,IncidentFlowChange,IncidentFlowVersion,IncidentType,IncidentSequence):db.execute(delete(model))
        for prefix,delegation,permissions in [('creator','01',{}),('worker','01',{}),('other','02',{})]:
            email=f'incident-{prefix}-{uuid4().hex[:8]}@example.test';account=User(email=email,full_name=prefix,role='OPERADOR_TIENDA',password_hash=hash_password('123456'),company_code=1,delegation_code=delegation)
            db.add(account);db.flush();db.add(OperatorAccess(user_id=account.id,exit_code='INC-'+str(account.id),permissions=permissions));accounts.append((account.id,email))
        db.commit()
    admin=login('admin@bermudez.test');clients=[login(email) for _,email in accounts]
    yield admin,clients,accounts
    with SessionLocal() as db:
        for model in (IncidentEmail,IncidentAttachment,IncidentEvent,LogisticsIncident,IncidentFlowChange,IncidentFlowVersion,IncidentType,IncidentSequence):db.execute(delete(model))
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
    assert action(other,current).status_code==404  # Unassigned users cannot authorize.
    # Assignment itself permits authorization, without a second global permission.
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
    saved['new_version']=True;saved['change_note']='Cambiar la validación sin alterar casos registrados'
    assert admin.put(BASE+'/types/REPLENISHMENT',json=saved).status_code==200
    current=action(creator,row,'SUBMIT').json();assert current['stage']=='Validación de delegación'
    current=action(worker,current,'RETURN').json();assert current['status']=='DRAFT' and current['assignee_id']==accounts[0][0]
    assert current['emails'][-1]['stage']=='Corregir registro'
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
    with SessionLocal() as db:
        access=db.get(OperatorAccess,accounts[0][0]);access.permissions={'delegation_ids':['1:02']};db.commit()
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
    assert login('operador@bermudez.test').get(BASE+'/options').status_code==200
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


def test_assignment_does_not_override_delegation_permissions(setup):
    admin,(creator,worker,other),accounts=setup
    saved=configure(admin,accounts,scope='DELEGATION')
    target={'user_id':accounts[2][0],'email':accounts[2][1]}
    saved['configuration']['steps'][0]['delegations']={'1:01':target}
    assert admin.put(BASE+'/types/REPLENISHMENT',json=saved).status_code==422
    row=create(creator)
    current=action(creator,row,'SUBMIT').json()
    assert action(admin,current,'REASSIGN',user_id=accounts[2][0],email=accounts[2][1]).status_code==403
    # An old or stale assignment cannot bypass current scope checks.
    with SessionLocal() as db:
        incident=db.get(LogisticsIncident,row['id']);incident.assignee_id=accounts[2][0];db.commit()
    assert other.get(BASE+'/'+row['id']).status_code==404
    assert other.get(BASE+'?box=ASSIGNED').json()['total']==0
    assert action(other,current).status_code==404


def test_management_is_scoped_to_configured_processes_and_can_be_revoked(setup):
    admin,(creator,worker,other),accounts=setup
    configure(admin,accounts);configure(admin,accounts,'INVENTORY')
    row=create(creator);inventory=create(creator,'INVENTORY')
    current=action(creator,row,'SUBMIT').json()
    with SessionLocal() as db:
        access=db.get(OperatorAccess,accounts[2][0])
        access.permissions={'incident_supervise':True,'incident_process_codes':['REPLENISHMENT']};db.commit()
    # Process management does not override delegated scope.
    assert other.get(BASE+'?box=ALL').json()['total']==0
    assert other.get(BASE+'/'+row['id']).status_code==404
    with SessionLocal() as db:
        access=db.get(OperatorAccess,accounts[2][0]);access.permissions={**access.permissions,'delegation_ids':['1:01']};db.commit()
    assert other.get(BASE+'?box=ALL').json()['total']==1
    assert other.get(BASE+'/'+inventory['id']).status_code==404
    assert other.get(BASE+'/'+row['id']).json()['can_reassign']
    assert action(other,current,'REASSIGN',user_id=accounts[2][0],email=accounts[2][1]).status_code==200
    with SessionLocal() as db:
        access=db.get(OperatorAccess,accounts[2][0]);access.permissions={'incident_supervise':True,'incident_all_processes':True,'delegation_ids':['1:01']};db.commit()
    assert other.get(BASE+'?box=ALL').json()['total']==2
    with SessionLocal() as db:
        access=db.get(OperatorAccess,accounts[2][0]);access.permissions={'incident_supervise':False,'incident_all_processes':True,'delegation_ids':['1:01']};db.commit()
    assert other.get(BASE+'/'+inventory['id']).status_code==404
    assert other.get(BASE+'/'+row['id']).json()['can_work']  # Assignment still authorizes this case.
    assert not other.get(BASE+'/'+row['id']).json()['can_reassign']


def test_configurers_choose_active_operators_in_their_delegations(setup):
    admin,(creator,worker,other),accounts=setup
    with SessionLocal() as db:
        access=db.get(OperatorAccess,accounts[2][0]);access.permissions={'incident_config':True};db.commit()
    options=other.get(BASE+'/options').json()
    assert accounts[1][0] not in [person['id'] for person in options['users']]
    assert [row['id'] for row in options['delegations']]==['1:02']
    assert [row['id'] for row in options['destinations']]==['1:02']
    with SessionLocal() as db:
        access=db.get(OperatorAccess,accounts[2][0]);access.permissions={**access.permissions,'delegation_ids':['1:01']};db.commit()
    assert accounts[1][0] in [person['id'] for person in other.get(BASE+'/options').json()['users']]
    saved=configure(admin,accounts);row=create(creator)
    assert other.get(BASE+'/'+row['id']).status_code==404
    assert other.put(BASE+'/types/REPLENISHMENT',json=saved).status_code==200
    # Disabled users cannot be selected even by a configurer.
    with SessionLocal() as db:
        db.get(User,accounts[1][0]).active=False;db.commit()
    saved=other.get(BASE+'/options').json()['types']
    saved=next(item for item in saved if item['configuration']['code']=='REPLENISHMENT')
    assert other.put(BASE+'/types/REPLENISHMENT',json=saved).status_code==422


def test_scope_revocation_hides_case_files_and_stops_assignment_email(setup):
    import app.incident_mail as mail
    admin,(creator,worker,other),accounts=setup
    configure(admin,accounts)
    row=create(creator);path=BASE+'/'+row['id']
    uploaded=creator.post(path+'/files',params={'version':row['version']},files={'file':('a.pdf',b'%PDF-1.4\n%%EOF','application/pdf')}).json()
    current=action(creator,uploaded,'SUBMIT').json()
    file_id=uploaded['files'][0]['id']
    assert worker.get(path+'/files/'+file_id).status_code==200
    with SessionLocal() as db:
        user=db.get(User,accounts[1][0]);user.delegation_code='02';db.commit()
    assert worker.get(path).status_code==404
    assert worker.get(path+'/files/'+file_id).status_code==404
    assert action(worker,current).status_code==404
    assert worker.get(BASE+'?box=ASSIGNED').json()['total']==0
    with SessionLocal() as db:
        message=db.scalar(select(IncidentEmail).where(IncidentEmail.incident_id==row['id']))
        mail.deliver(db,message,lambda *args:pytest.fail('Do not send case data outside configured delegations'))
        assert message.status=='NOT_CONFIGURED' and 'delegación' in message.diagnostic['response']


def test_scoped_flow_edit_hides_and_preserves_other_delegation_assignments(setup):
    admin,(creator,worker,other),accounts=setup
    saved=configure(admin,accounts,scope='DELEGATION')
    for step in saved['configuration']['steps']:
        if step['kind']!='CONFIRM':step['delegations']['1:02']={'user_id':accounts[2][0],'email':accounts[2][1]}
    response=admin.put(BASE+'/types/REPLENISHMENT',json=saved);assert response.status_code==200,response.text
    with SessionLocal() as db:
        access=db.get(OperatorAccess,accounts[0][0]);access.permissions={'incident_config':True};db.commit()
    options=creator.get(BASE+'/options').json()
    flow=next(item for item in options['types'] if item['configuration']['code']=='REPLENISHMENT')
    assert flow['structure_locked']
    assert all('1:02' not in step['delegations'] for step in flow['configuration']['steps'])
    wrong=deepcopy(flow);wrong['configuration']['steps'][0]['delegations']['1:02']={'user_id':accounts[2][0],'email':accounts[2][1]}
    assert creator.put(BASE+'/types/REPLENISHMENT',json=wrong).status_code==403
    wrong=deepcopy(flow);wrong['configuration']['name']='Cambiar todo'
    assert creator.put(BASE+'/types/REPLENISHMENT',json=wrong).status_code==403
    flow['configuration']['steps'][0]['delegations']['1:01']['email']='delegacion@example.test'
    result=creator.put(BASE+'/types/REPLENISHMENT',json=flow)
    assert result.status_code==200,result.text
    assert '1:02' not in result.json()['configuration']['steps'][0]['delegations']
    with SessionLocal() as db:
        cfg=db.get(IncidentType,'REPLENISHMENT').configuration
        assert cfg['steps'][0]['delegations']['1:02']['user_id']==accounts[2][0]
        assert cfg['steps'][0]['delegations']['1:01']['email']=='delegacion@example.test'


def test_destination_requires_explicit_access_and_all_delegations_remains_explicit(setup):
    admin,(creator,worker,other),accounts=setup
    configure(admin,accounts,'TRANSFER')
    assert creator.post(BASE,json=data('TRANSFER')).status_code==403
    with SessionLocal() as db:
        access=db.get(OperatorAccess,accounts[0][0]);access.permissions={'all_delegations':True};db.commit()
    assert {row['id'] for row in creator.get(BASE+'/options').json()['destinations']}=={'1:00','1:01','1:02'}
    assert creator.post(BASE,json=data('TRANSFER')).status_code==201


@pytest.mark.parametrize('activities',[
    ['EXECUTE'],['WORK','EXECUTE','CONFIRM'],['EXECUTE','APPROVE','WORK'],['CONFIRM','WORK']])
def test_configurer_controls_inventory_activities_order_and_closure(setup,activities,monkeypatch):
    admin,(creator,worker,other),accounts=setup
    flow=configure(admin,accounts,'INVENTORY')
    template=flow['configuration']['steps'][0]
    flow['configuration']['steps']=[{**deepcopy(template),'name':f'{index} {kind}','kind':kind,'scope':'GENERAL',
        'general':{'user_id':accounts[1][0],'email':accounts[1][1]},'delegations':{},'substitute':None,
        'require_document':False,'require_stock_verification':False} for index,kind in enumerate(activities)]
    response=admin.put(BASE+'/types/INVENTORY',json=flow)
    assert response.status_code==200,response.text
    row=create(creator,'INVENTORY')
    current=action(creator,row,'SUBMIT').json()
    assert current['assignee_id']==accounts[1][0]
    import app.incidents as module
    monkeypatch.setattr(module,'stock_for',lambda *args:pytest.fail('Optional verification must not query EXIT'))
    for index,kind in enumerate(activities):
        current=worker.get(BASE+'/'+row['id']).json()
        assert current['stage_kind']==kind and current['can_work']
        response=action(worker,current)
        assert response.status_code==200,response.text
        current=response.json()
        if kind=='CONFIRM' or index==len(activities)-1:
            assert current['status']=='CLOSED'
            assert len(current['emails'])==index+1
            break
        assert current['status']=='OPEN'
    assert action(creator,current).status_code==403


def test_any_activity_can_be_assigned_to_requester_without_changing_flow_snapshot(setup):
    admin,(creator,worker,other),accounts=setup
    flow=configure(admin,accounts)
    flow['configuration']['steps']=flow['configuration']['steps'][:1]
    flow['configuration']['steps'][0].update({'scope':'REQUESTER','general':None})
    response=admin.put(BASE+'/types/REPLENISHMENT',json=flow)
    assert response.status_code==200,response.text
    row=create(creator);current=action(creator,row,'SUBMIT').json()
    assert current['assignee_id']==accounts[0][0] and current['can_work']
    assert action(worker,current).status_code==404
    assert action(creator,current).json()['status']=='CLOSED'


def test_legacy_close_and_inventory_verification_keep_their_original_behavior(setup):
    from app.incident_flow import normalize,requester,stock_verification
    admin,(creator,worker,other),accounts=setup
    configure(admin,accounts,'INVENTORY')
    row=create(creator,'INVENTORY')
    with SessionLocal() as db:
        item=db.get(LogisticsIncident,row['id']);legacy=deepcopy(item.workflow)
        for step in legacy['steps']:
            step.pop('require_stock_verification',None)
            if step['kind']=='CONFIRM':step['scope']='DELEGATION'
        legacy['steps'][2]['require_document']=False
        item.workflow=legacy;db.commit()
    assert requester(legacy['steps'][-1])
    assert stock_verification(legacy,legacy['steps'][2])
    assert normalize(legacy)['steps'][-1]['scope']=='REQUESTER'
    current=action(creator,row,'SUBMIT').json()
    current=action(worker,current).json();current=action(worker,current).json()
    assert current['stage_kind']=='EXECUTE'
    assert action(worker,current,verification_note='Revisado').status_code==422
    assert action(worker,current,document='AJ-123').status_code==422
    current=action(worker,current,document='AJ-123',verification_note='Comprobado en EXIT').json()
    assert current['assignee_id']==accounts[0][0]


def test_registered_draft_seals_version_but_allows_renaming(setup):
    admin,(creator,worker,other),accounts=setup
    saved=configure(admin,accounts)
    assert saved['flow_version']==1 and not saved['in_use']
    saved['configuration']['steps'][0]['name']='Revisar solicitud'
    saved=admin.put(BASE+'/types/REPLENISHMENT',json=saved).json()
    assert saved['flow_version']==1
    row=create(creator)
    saved['configuration']['steps'][0]['hours']=72
    blocked=admin.put(BASE+'/types/REPLENISHMENT',json=saved)
    assert blocked.status_code==409 and 'nueva versión' in blocked.text
    assert admin.delete(BASE+'/types/REPLENISHMENT',params={'revision':saved['revision']}).status_code==409
    renamed=admin.patch(BASE+'/types/REPLENISHMENT/name',json={'revision':saved['revision'],'name':'Aprovisionamiento'}).json()
    assert renamed['flow_version']==1 and renamed['in_use'] and renamed['has_incidents']
    current=creator.get(BASE+'/'+row['id']).json()
    assert current['type_name']=='Aprovisionamiento' and current['flow_version']==1
    assert current['workflow']==row['workflow']
    assert admin.patch(BASE+'/types/REPLENISHMENT/name',json={'revision':saved['revision'],'name':'Antiguo'}).status_code==409
    assert creator.patch(BASE+'/types/REPLENISHMENT/name',json={'revision':renamed['revision'],'name':'Sin permiso'}).status_code==403
    history=admin.get(BASE+'/types/REPLENISHMENT/history').json()
    assert [entry['action'] for entry in history['changes']]==['RENAMED','EDITED','CREATED']
    assert history['changes'][0]['actor'] and history['changes'][0]['created_at']
    assert history['versions'][0]['in_use']


def test_explicit_new_version_preserves_old_cases_and_assignments(setup):
    admin,(creator,worker,other),accounts=setup
    saved=configure(admin,accounts);old=create(creator)
    saved['new_version']=True;saved['configuration']['steps'][0]['name']='Nueva revisión'
    assert admin.put(BASE+'/types/REPLENISHMENT',json=saved).status_code==422
    saved['change_note']='Separar validación de solicitud'
    response=admin.put(BASE+'/types/REPLENISHMENT',json=saved)
    assert response.status_code==200,response.text
    second=response.json();assert second['flow_version']==2 and not second['in_use'] and second['has_incidents']
    second['configuration']['steps'][0]['hours']=96
    second=admin.put(BASE+'/types/REPLENISHMENT',json=second).json()
    assert second['flow_version']==2
    new=create(creator);assert new['flow_version']==2 and new['workflow']['steps'][0]['hours']==96
    unchanged=creator.get(BASE+'/'+old['id']).json()
    assert unchanged['flow_version']==1 and unchanged['workflow']==old['workflow']
    opened=action(creator,old,'SUBMIT').json()
    assert opened['flow_version']==1 and opened['stage']!=new['workflow']['steps'][0]['name']
    visible=worker.get(BASE+'?box=ALL&status=OPEN').json()['items']
    assert len(visible)==1 and visible[0]['flow_version']==1
    assert visible[0]['flow_steps'][0]['state']=='CURRENT'
    assert all(step['state']=='PENDING' for step in visible[0]['flow_steps'][1:])
    assert other.get(BASE+'?box=ALL&status=OPEN').json()['total']==0
    history=admin.get(BASE+'/types/REPLENISHMENT/history').json()
    assert [entry['number'] for entry in history['versions']]==[2,1]
    assert history['versions'][0]['note']==saved['change_note']
    second['configuration']['notify']=False
    assert admin.put(BASE+'/types/REPLENISHMENT',json=second).status_code==409


def test_unused_process_deletion_preserves_history_and_reserves_code(setup):
    admin,(creator,worker,other),accounts=setup
    saved=configure(admin,accounts)
    assert creator.delete(BASE+'/types/REPLENISHMENT',params={'revision':saved['revision']}).status_code==403
    assert admin.delete(BASE+'/types/REPLENISHMENT',params={'revision':saved['revision']+1}).status_code==409
    result=admin.delete(BASE+'/types/REPLENISHMENT',params={'revision':saved['revision']})
    assert result.status_code==200,result.text
    assert not any(item['configuration']['code']=='REPLENISHMENT' for item in admin.get(BASE+'/options').json()['types'])
    assert creator.post(BASE,json=data()).status_code==409
    assert admin.get(BASE+'/types/REPLENISHMENT/history').json()['changes'][0]['action']=='DELETED'
    assert admin.get(BASE+'/types/REPLENISHMENT/history').json()['deleted']
    saved['revision']+=1
    assert admin.put(BASE+'/types/REPLENISHMENT',json=saved).status_code==409


def test_completed_incidence_still_prevents_process_deletion(setup):
    admin,(creator,worker,other),accounts=setup
    saved=configure(admin,accounts)
    saved['configuration']['steps']=[{**saved['configuration']['steps'][0],'kind':'CONFIRM','scope':'REQUESTER'}]
    saved=admin.put(BASE+'/types/REPLENISHMENT',json=saved).json()
    row=action(creator,create(creator),'SUBMIT').json()
    assert action(creator,row).json()['status']=='CLOSED'
    assert admin.delete(BASE+'/types/REPLENISHMENT',params={'revision':saved['revision']}).status_code==409
    assert admin.get(BASE+'/types/REPLENISHMENT/history').json()['versions'][0]['in_use']


def test_legacy_versions_are_reconstructed_once_without_changing_rules(setup):
    admin,(creator,worker,other),accounts=setup
    configure(admin,accounts);first=create(creator);second=create(creator)
    from app.incident_versions import migrate
    with SessionLocal() as db:
        source=db.get(IncidentType,'REPLENISHMENT')
        cfg=deepcopy(source.configuration);cfg.pop('_flow_version')
        cfg['steps'][0]['hours']=96;source.configuration=cfg
        for index,value in enumerate((first,second)):
            case=db.get(LogisticsIncident,value['id']);workflow=deepcopy(case.workflow);workflow.pop('_flow_version')
            if value==second:workflow['steps'][0]['hours']=96
            case.workflow=workflow
            case.created_at=datetime(2026,11,13,tzinfo=timezone.utc)+timedelta(minutes=index)
        db.execute(delete(IncidentFlowChange));db.execute(delete(IncidentFlowVersion));db.commit()
        engine=db.bind
    migrate(engine);migrate(engine)
    history=admin.get(BASE+'/types/REPLENISHMENT/history').json()
    assert history['current_version']==2 and len(history['versions'])==2 and len(history['changes'])==1
    assert all(entry['legacy'] and entry['created_by'] is None for entry in history['versions'])
    assert creator.get(BASE+'/'+first['id']).json()['flow_version']==1
    assert creator.get(BASE+'/'+second['id']).json()['flow_version']==2
    assert creator.get(BASE+'/'+first['id']).json()['workflow']['steps']==first['workflow']['steps']


def test_personal_inboxes_include_registered_incidents_and_pending_assignments(setup):
    admin,(creator,worker,other),accounts=setup
    configure(admin,accounts)
    row=create(creator)
    assert row['stage']=='Pendiente de envío' and row['can_submit']
    def ids(client,box,status='ACTIVE'):
        result=client.get(BASE,params={'box':box,'status':status})
        assert result.status_code==200,result.text
        return {item['id'] for item in result.json()['items']}
    assert ids(creator,'MINE')=={row['id']}
    assert ids(creator,'ASSIGNED')=={row['id']}
    assert ids(worker,'ASSIGNED')==set()
    # Supervising a process does not make somebody else its creator or current assignee.
    assert row['id'] in ids(admin,'ALL')
    assert ids(admin,'MINE')==set() and ids(admin,'ASSIGNED')==set()
    assert not admin.get(BASE+'/'+row['id']).json()['can_submit']
    current=action(creator,row,'SUBMIT').json()
    assert current['status']=='OPEN' and not current['can_submit']
    assert ids(worker,'ASSIGNED')=={row['id']}
    assert ids(creator,'ASSIGNED')==set() and ids(creator,'MINE')=={row['id']}
    current=action(worker,current,'RETURN').json()
    assert ids(creator,'ASSIGNED')=={row['id']}
    assert creator.get(BASE+'/'+row['id']).json()['can_submit']
    current=action(creator,current,'SUBMIT').json()
    current=action(worker,current).json();current=action(worker,current).json()
    closed=action(creator,current).json();assert closed['status']=='CLOSED'
    assert ids(creator,'ASSIGNED')==set()
    assert ids(creator,'MINE','ALL')=={row['id']}
    assert ids(other,'MINE','ALL')==set()
