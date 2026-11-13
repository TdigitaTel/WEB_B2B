"""Incidencias logísticas: flujo auditable y ERP de solo lectura."""
import io
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import PurePath
from urllib.parse import quote
from zoneinfo import ZoneInfo
from zipfile import ZipFile,BadZipFile
from fastapi import APIRouter,Depends,HTTPException,Query,Response,UploadFile,File
from PIL import Image,UnidentifiedImageError
from sqlalchemy import select,func,or_,update
from sqlalchemy.orm import Session,load_only
from .auth import require_roles,audit
from .db import get_db
from .models import (User,OperatorAccess,IncidentType as Type,IncidentSequence as Sequence,
    LogisticsIncident as Incident,IncidentEvent as Event,IncidentAttachment as Attachment,IncidentEmail as Mail,Order,OrderItem)
from .operator_permissions import permissions_for,delegation_scope,can_operate_delegation
from .delegations import fetch_delegations
from .erp_db import fetch_catalog_articles,connect_sqlserver
from .incident_schemas import SaveType,CreateIncident,EditIncident,Action,TypeConfiguration
from .order_email_settings import email_address

router=APIRouter(prefix='/api/v1/store/incidents',tags=['incidents'])
operator=require_roles('ADMIN','OPERADOR_TIENDA')
PERMISSIONS=('incident_access','incident_supervise','incident_config')
LABELS={'SALE':'Venta / despacho','PURCHASE':'Compra / recepción','REPLENISHMENT':'Reposición','INVENTORY':'Toma de inventario','TRANSFER':'Intercambio entre delegaciones'}

def now():return datetime.now(timezone.utc)
def fail(message,status=422):raise HTTPException(status,message)
def require(user,db,key):
    if not permissions_for(user,db).get(key):fail('No tienes permiso para esta acción',403)
def any_access(user,db):
    if not any(permissions_for(user,db).get(key) for key in PERMISSIONS):fail('No tienes acceso a Incidencias',403)
def stores():
    try:return {row.id:row for row in fetch_delegations()}
    except Exception:fail('No se pudieron consultar las delegaciones de EXIT',503)
def scope_ids(user,db):
    values=delegation_scope(user,db)
    return None if values is None else [f'{company}:{code}' for company,code in values]
def allowed_origin(user,db,reference):
    company,code=reference.split(':',1)
    return can_operate_delegation(user,db,int(company),code)
def managed_processes(user,db):
    if user.role=='ADMIN':return None
    if not permissions_for(user,db).get('incident_supervise'):return set()
    access=db.get(OperatorAccess,user.id)
    if not access:return set()
    configured=set(db.scalars(select(Type.code)))
    if access.permissions.get('incident_all_processes') is True:return configured
    return configured.intersection(access.permissions.get('incident_process_codes',[]))
def supervises(user,db,row):
    codes=managed_processes(user,db)
    return codes is None or row.type_code in codes
def can_see(user,db,row):
    return row.creator_id==user.id or row.assignee_id==user.id or supervises(user,db,row)
def load(incident_id,user,db,lock=False):
    any_access(user,db)
    query=select(Incident).where(Incident.id==incident_id)
    row=db.scalar(query.with_for_update() if lock else query)
    if not row or not can_see(user,db,row):fail('La incidencia no existe o no está autorizada',404)
    return row

def defaults(code):
    names={'SALE':['Validación de delegación','Resolución logística','Confirmación del solicitante'],
        'PURCHASE':['Validación de recepción','Gestión de Compras','Confirmación del solicitante'],
        'REPLENISHMENT':['Validación de delegación','Aprovisionamiento','Confirmación del solicitante'],
        'INVENTORY':['Validación del recuento','Autorización del ajuste','Ejecución en EXIT','Confirmación del solicitante'],
        'TRANSFER':['Validación de origen','Confirmación de destino','Resolución de diferencias','Confirmación del solicitante']}
    steps=[]
    for index,name in enumerate(names[code]):
        kind='CONFIRM' if index==len(names[code])-1 else 'APPROVE' if code=='INVENTORY' and index==1 else 'EXECUTE' if code=='INVENTORY' and index==2 else 'WORK'
        steps.append({'name':name,'kind':kind,'scope':'ORIGIN' if code=='TRANSFER' and index==0 else 'DESTINATION' if code=='TRANSFER' and index==1 else 'GENERAL' if index==1 and code!='INVENTORY' else 'DELEGATION','require_document':kind=='EXECUTE'})
    return TypeConfiguration(code=code,name=LABELS[code],kind=code,steps=steps).model_dump()

def type_rows(db):
    saved={row.code:row for row in db.scalars(select(Type).order_by(Type.code))}
    return [{'revision':saved[code].revision if code in saved else 0,'configuration':saved[code].configuration if code in saved else defaults(code)} for code in list(LABELS)+sorted(set(saved)-set(LABELS))]

def active_target(db,target,kind='WORK'):
    if not target:return None
    user=db.get(User,target['user_id'])
    if not user or not user.active or user.role not in {'ADMIN','OPERADOR_TIENDA'}:return None
    return user

def resolve(db,row,step):
    if step['kind']=='CONFIRM':
        user=db.get(User,row.creator_id)
        if not user or not user.active or user.role not in {'ADMIN','OPERADOR_TIENDA'}:fail('El solicitante ya no puede confirmar; un supervisor debe revisar la asignación',409)
        return user,user.email
    reference=row.destination_id if step['scope']=='DESTINATION' else row.delegation_id
    target=step.get('general') if step['scope']=='GENERAL' else step.get('delegations',{}).get(reference)
    account=active_target(db,target,step['kind'])
    if not account:
        target=step.get('substitute');account=active_target(db,target,step['kind'])
    if not account:fail(f'Configura un responsable habilitado para «{step["name"]}» y la delegación correspondiente',409)
    return account,target['email']

def event(db,row,user,action,**detail):
    db.add(Event(incident_id=row.id,actor_id=user.id,action=action,detail=detail))
    audit(db,user,'INCIDENT_'+action,'LOGISTICS_INCIDENT',row.id,{'number':row.number})

def file_mode(row):
    mode=row.workflow['file_mode']
    if mode=='FORBIDDEN':return mode
    if row.stage_index<0:return mode
    step=row.workflow['steps'][row.stage_index]
    return step['files'] if step['files']!='INHERIT' else 'OPTIONAL'

def files_required(db,row):
    if file_mode(row)!='REQUIRED':return
    query=select(func.count()).select_from(Attachment).where(Attachment.incident_id==row.id,Attachment.stage_index==row.stage_index)
    if row.stage_index>=0 and row.entered_at is not None:query=query.where(Attachment.created_at>=row.entered_at)
    if not db.scalar(query):fail('Esta etapa requiere al menos un archivo antes de avanzar',409)

def assign(db,row,index,user,note=''):
    step=row.workflow['steps'][index]
    target,address=resolve(db,row,step)
    row.stage_index=index;row.assignee_id=target.id;row.status='OPEN';row.entered_at=now();row.due_at=now()+timedelta(hours=step['hours']);row.assignment_version+=1
    queue_mail(db,row,address,target.id,step['name'])
    event(db,row,user,'ASSIGNED',stage=step['name'],assignee_id=target.id,assignee_name=target.full_name,note=note)

def queue_mail(db,row,address,user_id,stage):
    status='PENDING' if row.workflow.get('notify') else 'DISABLED'
    try:address=email_address(address)
    except ValueError:
        address=''
        if status!='DISABLED':status='NOT_CONFIGURED'
    db.add(Mail(incident_id=row.id,assignment_version=row.assignment_version,recipient_id=user_id,recipient=address,stage=stage,status=status))

def summary(row,db,names=None):
    stage=row.workflow['steps'][row.stage_index] if row.stage_index>=0 else None
    if names is None:names=dict(db.execute(select(User.id,User.full_name).where(User.id.in_([row.creator_id,row.assignee_id or row.creator_id]))).all())
    return {'id':row.id,'number':row.number,'type_code':row.type_code,'type_name':row.workflow['name'],'kind':row.workflow['kind'],
        'delegation_id':row.delegation_id,'delegation_name':row.delegation_name,'destination_id':row.destination_id,
        'document':row.document,'description':row.description,'reason':row.reason,'priority':row.priority,'needed_on':row.needed_on,
        'creator_id':row.creator_id,'creator_name':names.get(row.creator_id),'assignee_id':row.assignee_id,'assignee_name':names.get(row.assignee_id),
        'status':row.status,'stage_index':row.stage_index,'stage':stage['name'] if stage else 'Borrador','stage_kind':stage['kind'] if stage else None,
        'version':row.version,'created_at':row.created_at,'updated_at':row.updated_at,'entered_at':row.entered_at,'due_at':row.due_at,'resolution_document':row.resolution_document}

def detail(row,db,user):
    db.flush()
    files=[dict(record._mapping) for record in db.execute(select(Attachment.id,Attachment.filename,Attachment.size,Attachment.media_type,Attachment.uploaded_by,Attachment.stage_index,Attachment.created_at).where(Attachment.incident_id==row.id).order_by(Attachment.created_at,Attachment.id))]
    events=list(db.scalars(select(Event).where(Event.incident_id==row.id).order_by(Event.id)))
    names=dict(db.execute(select(User.id,User.full_name).where(User.id.in_({entry.actor_id for entry in events}))).all()) if events else {}
    mails=[{'id':entry.id,'stage':entry.stage,'status':entry.status,'attempts':entry.attempts,'diagnostic':entry.diagnostic,'created_at':entry.created_at,'updated_at':entry.updated_at} for entry in db.scalars(select(Mail).where(Mail.incident_id==row.id).order_by(Mail.id))]
    p=permissions_for(user,db);supervisor=supervises(user,db,row)
    current=row.workflow['steps'][row.stage_index] if row.stage_index>=0 else None
    work=row.assignee_id==user.id or supervisor
    if current and current['kind']=='CONFIRM':work=row.assignee_id==user.id and row.creator_id==user.id
    return {**summary(row,db),'lines':row.lines,'workflow':row.workflow,'file_mode':file_mode(row),'files':files,
        'events':[{'id':entry.id,'action':entry.action,'actor':names.get(entry.actor_id),'detail':entry.detail,'created_at':entry.created_at} for entry in events],
        'emails':mails,'can_submit':row.status=='DRAFT' and row.creator_id==user.id and p.get('incident_create',False),
        'can_work':row.status=='OPEN' and bool(work),'can_attach':(row.status=='DRAFT' and row.creator_id==user.id and p.get('incident_create') or row.status=='OPEN' and bool(work)) and file_mode(row)!='FORBIDDEN',
        'can_reassign':row.status=='OPEN' and bool(supervisor),'can_comment':row.status in {'DRAFT','OPEN'} and (row.creator_id==user.id or bool(work) or bool(supervisor))}

@router.get('/options')
def options(user:User=Depends(operator),db:Session=Depends(get_db)):
    any_access(user,db);p=permissions_for(user,db);delegations=stores();scope=scope_ids(user,db)
    people=[]
    if p.get('incident_config') or p.get('incident_supervise'):
        for account in db.scalars(select(User).where(User.active.is_(True),User.role.in_(['ADMIN','OPERADOR_TIENDA'])).order_by(User.full_name)):
            people.append({'id':account.id,'name':account.full_name,'email':account.email})
    return {'permissions':p,'user_id':user.id,'types':[item for item in type_rows(db) if p.get('incident_config') or item['revision']>0],'users':people,
        'delegations':[{'id':key,'name':row.name} for key,row in delegations.items() if scope is None or key in scope],
        'destinations':[{'id':key,'name':row.name} for key,row in delegations.items()]}

@router.put('/types/{code}')
def save_type(code:str,body:SaveType,user:User=Depends(operator),db:Session=Depends(get_db)):
    require(user,db,'incident_config');cfg=body.configuration
    if code!=cfg.code:fail('El código del tipo no coincide')
    if cfg.steps[-1].kind!='CONFIRM':fail('La última etapa debe ser la confirmación del solicitante')
    if any(step.kind=='CONFIRM' for step in cfg.steps[:-1]):fail('La confirmación del solicitante debe ser la última etapa')
    valid=stores()
    for step in cfg.steps:
        for reference in step.delegations:
            if reference not in valid:fail('Selecciona delegaciones válidas')
        if step.scope=='DESTINATION' and cfg.kind!='TRANSFER':fail('Destino solo está disponible para intercambios')
        targets=[*step.delegations.values(),*([step.general] if step.general else []),*([step.substitute] if step.substitute else [])]
        for target in targets:
            if not active_target(db,target.model_dump(),step.kind):fail('El responsable debe ser un usuario web activo')
        if cfg.active and step.kind!='CONFIRM' and not (step.general if step.scope=='GENERAL' else step.delegations or step.substitute):fail('Configura responsables antes de activar el flujo')
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    insert=pg_insert if db.bind.dialect.name=='postgresql' else sqlite_insert
    db.execute(insert(Type).values(code=code,revision=0,configuration=cfg.model_dump()).on_conflict_do_nothing(index_elements=['code']))
    row=db.scalar(select(Type).where(Type.code==code).with_for_update())
    if row.revision!=body.revision:fail('Otro usuario ha cambiado este flujo. Recarga antes de guardar',409)
    row.configuration=cfg.model_dump();row.revision+=1;audit(db,user,'INCIDENT_FLOW_SAVED','INCIDENT_TYPE',code);db.commit()
    return {'revision':row.revision,'configuration':row.configuration}

@router.get('/materials')
def materials(q:str=Query('',max_length=200),user:User=Depends(operator),db:Session=Depends(get_db)):
    any_access(user,db)
    try:rows,total=fetch_catalog_articles(q,1,20,management=True)
    except Exception:fail('No se pudo consultar la maestra de materiales de EXIT',503)
    return {'items':[{'sku':row['article_code'],'description':row['description'],'unit':row.get('unit','')} for row in rows]}

@router.get('/documents')
def documents(delegation_id:str,q:str=Query('',max_length=100),user:User=Depends(operator),db:Session=Depends(get_db)):
    require(user,db,'incident_create')
    if delegation_id not in stores() or not allowed_origin(user,db,delegation_id):fail('Delegación no autorizada',403)
    company,code=delegation_id.split(':',1)
    rows=list(db.scalars(select(Order).where(Order.company_code==int(company),Order.delegation_code==code,Order.deleted_at.is_(None),Order.reconciliation_hidden_at.is_(None),or_(Order.order_number.contains(q,autoescape=True),Order.nro_pedido_exit.contains(q,autoescape=True))).order_by(Order.id.desc()).limit(15)))
    by_order={row.id:[] for row in rows}
    for line in db.scalars(select(OrderItem).where(OrderItem.order_id.in_(by_order),OrderItem.exit_removed_at.is_(None),OrderItem.deleted_at.is_(None))):
        by_order[line.order_id].append({'sku':line.sku,'description':line.description,'unit':line.unit,'expected':float(line.quantity)})
    return {'items':[{'reference':row.order_number,'exit_number':row.nro_pedido_exit,'lines':by_order[row.id]} for row in rows]}


def stock_for(skus,delegation_id):
    company,delegation=delegation_id.split(':',1)
    with connect_sqlserver() as connection,connection.cursor() as cursor:
        cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",('dbo','VIS_EX_StockVentasDelegacion'))
        has_company=any(str(record['COLUMN_NAME']).casefold()=='codigoempresa' for record in cursor.fetchall())
        if not has_company and int(company)!=1:fail('No se puede identificar de forma segura la empresa del stock',503)
        marks=','.join(['%s']*len(skus))
        cursor.execute(f'SELECT CodigoArticulo AS sku, UnidadSaldo AS stock FROM dbo.VIS_EX_StockVentasDelegacion WHERE IdDelegacion=%s AND CodigoArticulo IN ({marks})'+(' AND CodigoEmpresa=%s' if has_company else ''),tuple([delegation,*skus,*([int(company)] if has_company else [])]))
        rows=cursor.fetchall()
    result={}
    for entry in rows:
        sku=str(entry['sku']).strip()
        if sku in result:fail('EXIT devuelve varias posiciones para este material; revisa su ubicación',409)
        value=float(entry['stock'])
        if not (-1e9<=value<=1e9):fail('EXIT devolvió un stock inválido',503)
        result[sku]=value
    return result

@router.get('/stock')
def stock(sku:str=Query(min_length=1,max_length=100),delegation_id:str=Query(max_length=80),user:User=Depends(operator),db:Session=Depends(get_db)):
    require(user,db,'incident_create')
    if delegation_id not in stores() or not allowed_origin(user,db,delegation_id):fail('Delegación no autorizada',403)
    try:values=stock_for([sku],delegation_id)
    except HTTPException:raise
    except Exception:fail('No se pudo consultar el stock de EXIT. Puedes registrar un valor manual, indicando su origen',503)
    if sku not in values:fail('No hay una posición de stock inequívoca para este material',404)
    return {'sku':sku,'stock':values[sku],'captured_at':now()}


def collect_lines(body,config):
    kind=config['kind']
    if len({line.sku.strip() for line in body.lines})!=len(body.lines):fail('No repitas el mismo material en la incidencia')
    lines=[{**line.model_dump(mode='json'),'sku':line.sku.strip()} for line in body.lines]
    if any(not line['sku'] for line in lines):fail('Indica el código de cada material')
    if kind=='INVENTORY':
        live=[line.sku.strip() for line in body.lines if not line.manual_stock]
        try:stocks=stock_for(live,body.delegation_id) if live else {}
        except HTTPException:raise
        except Exception:fail('No se pudo capturar el stock de EXIT. Reintenta o registra un valor manual con justificación',503)
        for line in lines:
            if line['counted'] is None or not line['location'].strip():fail('En inventario indica cantidad contada y ubicación para cada material')
            if line['manual_stock']:
                if line['system_stock'] is None or not line['manual_reason'].strip():fail('El stock manual necesita una cantidad y una justificación')
            else:
                if line['sku'].strip() not in stocks:fail('No existe una posición de stock inequívoca para '+line['sku'])
                line['system_stock']=stocks[line['sku'].strip()]
            line['counted_at']=line['counted_at'] or now().isoformat()
            if datetime.fromisoformat(line['counted_at']).astimezone(timezone.utc)>now()+timedelta(minutes=5):fail('La fecha del recuento no puede estar en el futuro')
            line['stock_captured_at']=now().isoformat();line['stock_source']='MANUAL' if line['manual_stock'] else 'EXIT'
            line['delta']=line['counted']-line['system_stock']
    if kind!='INVENTORY' and any(line['expected'] is None or line['expected']<=0 for line in lines):fail('Indica la cantidad esperada o necesaria de cada material')
    return lines

@router.post('',status_code=201)
def create(body:CreateIncident,user:User=Depends(operator),db:Session=Depends(get_db)):
    require(user,db,'incident_create');delegations=stores()
    if body.delegation_id not in delegations or not allowed_origin(user,db,body.delegation_id):fail('Delegación no autorizada',403)
    config=next((item['configuration'] for item in type_rows(db) if item['configuration']['code']==body.type_code),None)
    if not config or not config['active']:fail('Activa y configura este tipo de incidencia antes de usarlo',409)
    kind=config['kind']
    if body.reason not in config['reasons']:fail('Selecciona un motivo configurado para este tipo')
    if kind!='INVENTORY' and not body.document.strip():fail('Indica el número del documento relacionado')
    if kind=='TRANSFER' and (body.destination_id not in delegations or body.destination_id==body.delegation_id):fail('Selecciona una delegación de destino diferente')
    lines=collect_lines(body,config)
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    insert=pg_insert if db.bind.dialect.name=='postgresql' else sqlite_insert
    year=now().astimezone(ZoneInfo('Europe/Madrid')).year
    db.execute(insert(Sequence).values(year=year,value=0).on_conflict_do_nothing(index_elements=['year']))
    value=db.scalar(update(Sequence).where(Sequence.year==year).values(value=Sequence.value+1).returning(Sequence.value))
    row=Incident(number=f'INC-{year}-{value:06d}',type_code=body.type_code,delegation_id=body.delegation_id,delegation_name=delegations[body.delegation_id].name,
        destination_id=body.destination_id if kind=='TRANSFER' else None,document=body.document.strip(),reason=body.reason,description=body.description.strip(),priority=body.priority,needed_on=body.needed_on,creator_id=user.id,workflow=deepcopy(config),lines=lines,updated_at=now())
    db.add(row);db.flush();event(db,row,user,'CREATED');db.commit()
    return detail(row,db,user)

@router.get('')
def listing(box:str=Query('MINE',pattern='^(MINE|ASSIGNED|ALL)$'),status:str=Query('ACTIVE',pattern='^(ACTIVE|DRAFT|OPEN|CLOSED|REJECTED|ALL)$'),q:str=Query('',max_length=160),delegation_id:str=Query('',max_length=80),type_code:str=Query('',max_length=40),page:int=Query(1,ge=1),user:User=Depends(operator),db:Session=Depends(get_db)):
    any_access(user,db);codes=managed_processes(user,db)
    conditions=[Incident.creator_id==user.id,Incident.assignee_id==user.id]
    if codes is None:conditions.append(Incident.id.is_not(None))
    elif codes:conditions.append(Incident.type_code.in_(codes))
    query=select(Incident).where(or_(*conditions))
    if box=='MINE':query=query.where(Incident.creator_id==user.id)
    elif box=='ASSIGNED':query=query.where(Incident.assignee_id==user.id,Incident.status=='OPEN')
    if status=='ACTIVE':query=query.where(Incident.status.in_(['DRAFT','OPEN']))
    elif status!='ALL':query=query.where(Incident.status==status)
    if q:query=query.where(or_(Incident.number.contains(q,autoescape=True),Incident.document.contains(q,autoescape=True)))
    if delegation_id:query=query.where(Incident.delegation_id==delegation_id)
    if type_code:query=query.where(Incident.type_code==type_code)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    rows=list(db.scalars(query.order_by(Incident.updated_at.desc(),Incident.id).offset((page-1)*30).limit(30)))
    ids={value for row in rows for value in (row.creator_id,row.assignee_id) if value}
    names=dict(db.execute(select(User.id,User.full_name).where(User.id.in_(ids))).all()) if ids else {}
    return {'items':[summary(row,db,names) for row in rows],'total':total,'page_size':30}

@router.get('/{incident_id}')
def read(incident_id:str,user:User=Depends(operator),db:Session=Depends(get_db)):return detail(load(incident_id,user,db),db,user)

@router.post('/{incident_id}/actions')
def action(incident_id:str,body:Action,user:User=Depends(operator),db:Session=Depends(get_db)):
    row=load(incident_id,user,db,True)
    if row.version!=body.version:fail('La incidencia ha cambiado. Recarga antes de continuar',409)
    allowed=detail(row,db,user);name=body.action
    if name=='COMMENT':
        if not allowed['can_comment']:fail('No puedes comentar esta incidencia',403)
        if not body.note.strip():fail('Escribe el comentario')
        event(db,row,user,'COMMENT',note=body.note)
    elif name=='SUBMIT':
        if not allowed['can_submit']:fail('Solo el solicitante puede enviar su borrador',403)
        for step in row.workflow['steps']:resolve(db,row,step)
        files_required(db,row);assign(db,row,0,user)
    elif name=='REASSIGN':
        if not allowed['can_reassign']:fail('Solo un supervisor autorizado puede reasignar',403)
        if not body.note.strip():fail('Indica el motivo de la reasignación')
        step=row.workflow['steps'][row.stage_index]
        if step['kind']=='CONFIRM' and body.user_id!=row.creator_id:fail('La confirmación final corresponde al solicitante')
        target={'user_id':body.user_id,'email':body.email}
        account=active_target(db,target,step['kind'])
        if not account:fail('Selecciona un usuario web activo como responsable')
        try:address=email_address(body.email)
        except ValueError:fail('Indica un correo válido')
        row.assignee_id=account.id;row.assignment_version+=1;row.entered_at=now();row.due_at=now()+timedelta(hours=step['hours']);queue_mail(db,row,address,account.id,step['name']);event(db,row,user,'REASSIGNED',assignee_id=account.id,assignee_name=account.full_name,note=body.note)
    elif name=='RESEND_EMAIL':
        if not (allowed['can_work'] or allowed['can_reassign'] or allowed['can_submit']):fail('No puedes reenviar este aviso',403)
        mail=db.scalar(select(Mail).where(Mail.incident_id==row.id,Mail.assignment_version==row.assignment_version).order_by(Mail.id.desc()).limit(1))
        if not mail or mail.status=='DISABLED':fail('El correo no está habilitado para este flujo',409)
        if mail.status in {'SENT','UNCERTAIN','SENDING'} and not body.note.strip():fail('Comprueba el envío anterior y escribe el motivo antes de reenviar',409)
        if mail.status=='SENDING':fail('Ya hay un envío en curso',409)
        mail.status='PENDING';mail.attempts=0;mail.next_attempt_at=None;mail.diagnostic=None;event(db,row,user,'EMAIL_RETRY',note=body.note)
    else:
        if not allowed['can_work']:fail('La incidencia no está en tu posición o no tienes permiso para esta etapa',403)
        step=row.workflow['steps'][row.stage_index]
        if not body.note.strip():fail('Describe la actuación realizada')
        if name=='REJECT':row.status='REJECTED';row.assignee_id=None;row.due_at=None;event(db,row,user,'REJECTED',note=body.note)
        elif name=='RETURN':
            if row.stage_index==0:
                row.status='DRAFT';row.stage_index=-1;row.assignee_id=row.creator_id;row.due_at=None;row.assignment_version+=1
                creator=db.get(User,row.creator_id);queue_mail(db,row,creator.email,creator.id,'Corregir borrador')
            else:assign(db,row,row.stage_index-1,user,body.note)
            event(db,row,user,'RETURNED',note=body.note)
        elif name=='ADVANCE':
            files_required(db,row)
            if (step.get('require_document') or step['kind']=='EXECUTE') and not body.document.strip():fail('Indica el documento de resolución o ajuste realizado en EXIT')
            if step['kind']=='EXECUTE' and row.workflow['kind']=='INVENTORY' and not body.verification_note.strip():fail('Confirma la revisión del stock actual y los movimientos posteriores al recuento')
            if body.document.strip():row.resolution_document=body.document.strip()
            verification={}
            if step['kind']=='EXECUTE' and row.workflow['kind']=='INVENTORY':
                if body.verification_source=='EXIT':
                    try:verification=stock_for([line['sku'] for line in row.lines],row.delegation_id)
                    except Exception:fail('No se pudo verificar el stock actual. Reintenta o registra una comprobación manual justificada',503)
                    if any(line['sku'] not in verification for line in row.lines):fail('No se pudo identificar el stock actual de todos los materiales',409)
                else:verification={'source':'MANUAL','note':body.verification_note}
            event(db,row,user,'COMPLETED_STAGE',stage=step['name'],note=body.note,document=body.document,verification_note=body.verification_note,verification_source=body.verification_source if step['kind']=='EXECUTE' and row.workflow['kind']=='INVENTORY' else None,stock_verified=verification,verified_at=now().isoformat() if step['kind']=='EXECUTE' and row.workflow['kind']=='INVENTORY' else None)
            if row.stage_index==len(row.workflow['steps'])-1:row.status='CLOSED';row.assignee_id=None;row.due_at=None;event(db,row,user,'CLOSED',note=body.note)
            else:assign(db,row,row.stage_index+1,user)
    row.version+=1;row.updated_at=now();db.commit();return detail(row,db,user)

@router.post('/{incident_id}/files',status_code=201)
async def upload(incident_id:str,version:int=Query(ge=1),file:UploadFile=File(...),user:User=Depends(operator),db:Session=Depends(get_db)):
    row=load(incident_id,user,db,True)
    if row.version!=version:fail('La incidencia ha cambiado. Recarga antes de adjuntar',409)
    if not detail(row,db,user)['can_attach']:fail('No se admiten archivos en esta posición o no tienes permiso',403)
    count=db.scalar(select(func.count()).select_from(Attachment).where(Attachment.incident_id==row.id))
    if count>=row.workflow['max_files']:fail('Se alcanzó el máximo de archivos configurado para esta incidencia')
    limit=row.workflow['max_file_mb']*1024*1024
    data=await file.read(limit+1);await file.close()
    if len(data)>limit:fail('El archivo supera el tamaño configurado',413)
    filename=PurePath((file.filename or 'archivo').replace('\\','/')).name
    filename=''.join(c for c in filename if ord(c)>=32 and ord(c)!=127)[:180]
    ext=filename.rsplit('.',1)[-1].lower();ext='jpg' if ext=='jpeg' else ext
    if ext not in row.workflow['extensions']:fail('Este formato de archivo no está permitido')
    media={'jpg':'image/jpeg','png':'image/png','webp':'image/webp','pdf':'application/pdf','xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}[ext]
    try:
        if ext in {'jpg','png','webp'}:
            with Image.open(io.BytesIO(data)) as picture:
                if picture.format!={'jpg':'JPEG','png':'PNG','webp':'WEBP'}[ext] or picture.width*picture.height>20_000_000:raise ValueError()
                picture.verify()
        elif ext=='pdf':
            if not data.startswith(b'%PDF-') or b'%%EOF' not in data[-2048:]:raise ValueError()
        else:
            with ZipFile(io.BytesIO(data)) as archive:
                entries=archive.infolist();names={entry.filename for entry in entries}
                if len(entries)>2000 or sum(entry.file_size for entry in entries)>50*1024*1024 or not {'[Content_Types].xml','xl/workbook.xml'}<=names:raise ValueError()
                if any('vbaproject' in name.lower() or name.lower().endswith(('.exe','.js','.bat','.com')) for name in names):raise ValueError()
    except (ValueError,OSError,BadZipFile,UnidentifiedImageError,Image.DecompressionBombError):fail('El contenido no corresponde a un archivo válido del formato indicado')
    item=Attachment(incident_id=row.id,uploaded_by=user.id,stage_index=row.stage_index,filename=filename,media_type=media,size=len(data),content=data,created_at=now())
    db.add(item);db.flush();event(db,row,user,'FILE_ADDED',filename=filename,file_id=item.id,size=len(data));row.version+=1;row.updated_at=now();db.commit()
    return detail(row,db,user)

@router.get('/{incident_id}/files/{file_id}')
def download(incident_id:str,file_id:str,user:User=Depends(operator),db:Session=Depends(get_db)):
    load(incident_id,user,db)
    file=db.scalar(select(Attachment).where(Attachment.id==file_id,Attachment.incident_id==incident_id))
    if not file:fail('El archivo no existe',404)
    return Response(file.content,media_type=file.media_type,headers={'Content-Disposition':f"attachment; filename=archivo; filename*=UTF-8''{quote(file.filename,safe='')}",'X-Content-Type-Options':'nosniff','Content-Security-Policy':'sandbox','Cache-Control':'private, no-store'})


@router.put('/{incident_id}')
def edit(incident_id:str,body:EditIncident,user:User=Depends(operator),db:Session=Depends(get_db)):
    require(user,db,'incident_create');row=load(incident_id,user,db,True)
    if row.status!='DRAFT' or row.creator_id!=user.id:fail('Solo el solicitante puede corregir su borrador',403)
    if row.version!=body.version:fail('La incidencia ha cambiado. Recarga antes de corregir',409)
    if body.type_code!=row.type_code or body.delegation_id!=row.delegation_id:fail('El tipo y la delegación de una incidencia registrada no pueden cambiar')
    if body.reason not in row.workflow['reasons']:fail('Selecciona un motivo del flujo registrado')
    if row.workflow['kind']!='INVENTORY' and not body.document.strip():fail('Indica el documento relacionado')
    if row.workflow['kind']=='TRANSFER' and (body.destination_id not in stores() or body.destination_id==row.delegation_id):fail('Selecciona un destino diferente')
    if not allowed_origin(user,db,row.delegation_id):fail('Ya no tienes acceso a esa delegación',403)
    previous={'document':row.document,'description':row.description,'reason':row.reason,'priority':row.priority,'needed_on':row.needed_on.isoformat() if row.needed_on else None,'destination_id':row.destination_id,'lines':deepcopy(row.lines)}
    row.document=body.document.strip();row.description=body.description.strip();row.reason=body.reason;row.priority=body.priority;row.needed_on=body.needed_on
    row.destination_id=body.destination_id if row.workflow['kind']=='TRANSFER' else None;row.lines=collect_lines(body,row.workflow)
    row.version+=1;row.updated_at=now();event(db,row,user,'CORRECTED',previous=previous,changes={'document':row.document,'description':row.description,'reason':row.reason,'priority':row.priority,'needed_on':row.needed_on.isoformat() if row.needed_on else None,'destination_id':row.destination_id,'lines':row.lines});db.commit();return detail(row,db,user)


@router.get('/{incident_id}/stock')
def current_stock(incident_id:str,user:User=Depends(operator),db:Session=Depends(get_db)):
    row=load(incident_id,user,db)
    if row.workflow['kind']!='INVENTORY':fail('Esta incidencia no es de inventario')
    try:values=stock_for([line['sku'] for line in row.lines],row.delegation_id)
    except HTTPException:raise
    except Exception:fail('No se pudo consultar el stock actual de EXIT',503)
    return {'values':values,'captured_at':now()}
