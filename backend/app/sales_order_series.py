"""EXIT PedV series and local, company-scoped delegation assignments. EXIT is read-only."""
import hashlib
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, false, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .auth import audit, require_roles
from .db import get_db
from .delegations import fetch_delegations
from .erp_db import connect_sqlserver
from .models import SalesOrderSeriesAssignment as Assignment, User
from .operator_permissions import can_operate_delegation, delegation_scope

DOCUMENT_TYPE='PedV'
logger=logging.getLogger(__name__)
router=APIRouter(prefix='/api/v1/store/sales-order-series',tags=['Series de pedidos'])
operator=require_roles('ADMIN','OPERADOR_TIENDA')


def fetch_sales_order_series():
    with connect_sqlserver() as connection, connection.cursor() as cursor:
        cursor.execute('''SELECT s.CodigoEmpresa AS company_code, s.serie AS series_code,
            s.TipoDocumento AS document_type, s.DescripcionSerie AS description
            FROM Series s WHERE s.TipoDocumento = %s ORDER BY s.CodigoEmpresa, s.serie''',(DOCUMENT_TYPE,))
        return [{'company_code':int(row['company_code']),
            'series_code':str(row['series_code'] if row['series_code'] is not None else '').strip(),
            'document_type':str(row['document_type']).strip(),
            'description':str(row['description'] or '').strip()} for row in cursor.fetchall()]


def exit_series():
    try:return fetch_sales_order_series()
    except Exception as exc:
        logger.exception('No se pudo consultar Series (CodigoEmpresa, serie, TipoDocumento, DescripcionSerie)')
        raise HTTPException(503,'No se pudieron consultar las series PedV de EXIT. Revisa la conexión y el registro de la API.') from exc


def exit_delegations():
    try:return fetch_delegations()
    except Exception as exc:
        logger.exception('No se pudieron consultar las delegaciones para asociar series')
        raise HTTPException(503,'No se pudieron consultar las delegaciones de EXIT. Las asociaciones guardadas siguen disponibles.') from exc


def authorize(db,user,company,delegation):
    if not can_operate_delegation(user,db,company,delegation):
        raise HTTPException(403,'No tienes acceso a esta empresa y delegación')


def assignment_payload(row):
    return {'id':row.id,'company_code':row.company_code,'delegation_code':row.delegation_code,
        'document_type':row.document_type,'series_code':row.series_code,'series_description':row.series_description,
        'delegation_name':row.delegation_name,'active':row.active,'version':row.version,
        'updated_at':row.updated_at.isoformat() if row.updated_at else None}


class AssignmentInput(BaseModel):
    company_code:int=Field(ge=0,le=2147483647)
    delegation_code:str=Field(pattern=r'^[0-9]{2}$')
    series_code:str=Field(max_length=100)
    active:bool=True

    @field_validator('series_code')
    @classmethod
    def trim_code(cls,value):return value.strip()


class StateInput(BaseModel):
    active:bool
    expected_version:int=Field(ge=1)


def lock_delegation(db,company,delegation):
    # No local delegation master: the transaction lock serializes switches between different rows.
    if db.bind.dialect.name=='postgresql':
        key=int.from_bytes(hashlib.sha256(f'series:{DOCUMENT_TYPE}:{company}:{delegation}'.encode()).digest()[:8],'big',signed=True)
        db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':key})


def validate_source(company,delegation,series):
    seat=next((row for row in exit_delegations() if row.company==company and row.code==delegation),None)
    if seat is None:raise HTTPException(422,'La delegación no pertenece a la empresa indicada en EXIT')
    selected=next((row for row in exit_series() if row['company_code']==company and row['series_code']==series and row['document_type']==DOCUMENT_TYPE),None)
    if selected is None:raise HTTPException(422,'La serie PedV no pertenece a la empresa indicada en EXIT')
    return seat.name,selected['description']


def apply_state(db,row,active):
    replaced=[]
    if active:
        others=db.scalars(select(Assignment).where(Assignment.company_code==row.company_code,
            Assignment.delegation_code==row.delegation_code,Assignment.document_type==DOCUMENT_TYPE,
            Assignment.active.is_(True),Assignment.id!=row.id).with_for_update()).all()
        for previous in others:
            previous.active=False;previous.version+=1;replaced.append(previous.id)
        # Release the partial unique index before activating a different (possibly older) row.
        db.flush()
    row.active=active;row.version+=1
    return replaced


def commit(db):
    try:db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409,'La configuración cambió durante el guardado. Actualiza las asociaciones y vuelve a intentarlo.') from exc


@router.get('/options')
def options(db:Session=Depends(get_db),user:User=Depends(operator)):
    seats=[row for row in exit_delegations() if can_operate_delegation(user,db,row.company,row.code)]
    companies={row.company for row in seats}
    series=[row for row in exit_series() if row['company_code'] in companies]
    return {'document_type':DOCUMENT_TYPE,'series':series,
        'delegations':[{'company_code':row.company,'code':row.code,'name':row.name} for row in seats]}


@router.get('/assignments')
def assignments(company_code:int|None=Query(None,ge=0),delegation_code:str|None=Query(None,pattern=r'^[0-9]{2}$'),
        db:Session=Depends(get_db),user:User=Depends(operator)):
    query=select(Assignment).where(Assignment.document_type==DOCUMENT_TYPE)
    scope=delegation_scope(user,db)
    if scope is not None:
        allowed=[and_(Assignment.company_code==int(company),Assignment.delegation_code==delegation) for company,delegation in scope if company.isdigit()]
        query=query.where(or_(*allowed) if allowed else false())
    if company_code is not None:query=query.where(Assignment.company_code==company_code)
    if delegation_code is not None:query=query.where(Assignment.delegation_code==delegation_code)
    return [assignment_payload(row) for row in db.scalars(query.order_by(Assignment.company_code,Assignment.delegation_code,Assignment.series_code))]


@router.put('/assignments')
def save_assignment(body:AssignmentInput,db:Session=Depends(get_db),user:User=Depends(operator)):
    authorize(db,user,body.company_code,body.delegation_code)
    name,description=validate_source(body.company_code,body.delegation_code,body.series_code)
    lock_delegation(db,body.company_code,body.delegation_code)
    row=db.scalar(select(Assignment).where(Assignment.company_code==body.company_code,
        Assignment.delegation_code==body.delegation_code,Assignment.document_type==DOCUMENT_TYPE,
        Assignment.series_code==body.series_code).with_for_update())
    previous=assignment_payload(row) if row else None
    if row is None:
        row=Assignment(company_code=body.company_code,delegation_code=body.delegation_code,
            document_type=DOCUMENT_TYPE,series_code=body.series_code,active=False,version=0)
        db.add(row);db.flush()
    row.delegation_name=name;row.series_description=description;row.updated_by=user.id
    replaced=apply_state(db,row,body.active)
    audit(db,user,'SALES_ORDER_SERIES_SAVED','SALES_ORDER_SERIES',str(row.id),
        {'previous':previous,'company_code':row.company_code,'delegation_code':row.delegation_code,
         'series_code':row.series_code,'active':body.active,'deactivated_ids':replaced})
    commit(db);return assignment_payload(row)


@router.patch('/assignments/{assignment_id}')
def change_state(assignment_id:int,body:StateInput,db:Session=Depends(get_db),user:User=Depends(operator)):
    row=db.get(Assignment,assignment_id)
    if row is None:raise HTTPException(404,'Asociación no encontrada')
    authorize(db,user,row.company_code,row.delegation_code)
    source=validate_source(row.company_code,row.delegation_code,row.series_code) if body.active else None
    lock_delegation(db,row.company_code,row.delegation_code)
    db.refresh(row,with_for_update=True)
    if row.version!=body.expected_version:raise HTTPException(409,'Otra persona modificó esta asociación. Actualiza la lista.')
    previous=assignment_payload(row)
    if source:row.delegation_name,row.series_description=source
    replaced=apply_state(db,row,body.active);row.updated_by=user.id
    audit(db,user,'SALES_ORDER_SERIES_STATE_CHANGED','SALES_ORDER_SERIES',str(row.id),
        {'previous':previous,'active':body.active,'deactivated_ids':replaced})
    commit(db);return assignment_payload(row)


def resolve_active_series(db,company,delegation):
    rows=db.scalars(select(Assignment).where(Assignment.company_code==company,
        Assignment.delegation_code==delegation,Assignment.document_type==DOCUMENT_TYPE,Assignment.active.is_(True)).limit(2)).all()
    if not rows:raise HTTPException(404,'No hay una serie PedV activa para esta empresa y delegación')
    if len(rows)>1:raise HTTPException(409,'Hay más de una serie activa. Revisa las asociaciones antes de continuar.')
    return assignment_payload(rows[0])


@router.get('/active')
def active_series(company_code:int=Query(...,ge=0,le=2147483647),delegation_code:str=Query(...,pattern=r'^[0-9]{2}$'),
        db:Session=Depends(get_db),user:User=Depends(operator)):
    authorize(db,user,company_code,delegation_code)
    return resolve_active_series(db,company_code,delegation_code)
