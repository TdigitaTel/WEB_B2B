"""Local links to EXIT's composite delegation/warehouse keys. Never writes to EXIT."""
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
from .models import DelegationWarehouse as Link, User
from .operator_permissions import can_operate_delegation, delegation_scope

router=APIRouter(prefix='/api/v1/store/delegation-warehouses',tags=['Delegaciones y almacenes'])
reader=require_roles('ADMIN','OPERADOR_TIENDA')
manager=require_roles('ADMIN')
logger=logging.getLogger(__name__)


def fetch_warehouses():
    with connect_sqlserver() as connection:
        cursor=connection.cursor()
        cursor.execute('''SELECT CodigoEmpresa AS company_code, CodigoAlmacen AS code,
            Almacen AS name FROM dbo.almacenes ORDER BY CodigoEmpresa, CodigoAlmacen''')
        return [{'company_code':int(row['company_code']),'code':str(row['code'] or '').strip(),
                 'name':str(row['name'] or '').strip()} for row in cursor.fetchall() if str(row['code'] or '').strip()]


def source():
    try:return fetch_delegations(),fetch_warehouses()
    except Exception as exc:
        logger.exception('Error consultando delegaciones y almacenes de EXIT')
        raise HTTPException(503,'No se pudieron consultar las delegaciones y almacenes de EXIT. Las relaciones guardadas se conservan.') from exc


def payload(row):
    return {key:getattr(row,key) for key in ('company_code','delegation_code','warehouse_code','delegation_name',
        'warehouse_name','is_primary','active','use_for_stock','version')}


def lock(db,company,delegation):
    if db.bind.dialect.name=='postgresql':
        key=int.from_bytes(hashlib.sha256(f'warehouses:{company}:{delegation}'.encode()).digest()[:8],'big',signed=True)
        db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':key})


def commit(db):
    try:db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409,'La relación cambió durante el guardado. Actualiza la lista y vuelve a intentarlo.') from exc


def synchronize(db,seats,warehouses):
    names={(w['company_code'],w['code']):w['name'] for w in warehouses}
    for seat in sorted(seats,key=lambda row:(row.company,row.code)):
        lock(db,seat.company,seat.code)
        rows=db.scalars(select(Link).where(Link.company_code==seat.company,Link.delegation_code==seat.code).with_for_update()).all()
        for row in rows:
            name=names.get((seat.company,row.warehouse_code),row.warehouse_name)
            primary=row.warehouse_code==seat.warehouse_code
            if (row.delegation_name,row.warehouse_name,row.is_primary)!=(seat.name,name,primary):
                row.delegation_name=seat.name;row.warehouse_name=name;row.version+=1
        # Release an old primary before inserting/promoting its replacement.
        for row in rows:
            if row.warehouse_code!=seat.warehouse_code:row.is_primary=False
        db.flush()
        if seat.warehouse_code:
            row=next((row for row in rows if row.warehouse_code==seat.warehouse_code),None)
            if row is not None:row.is_primary=True
            if row is None:
                db.add(Link(company_code=seat.company,delegation_code=seat.code,warehouse_code=seat.warehouse_code,
                    delegation_name=seat.name,warehouse_name=names.get((seat.company,seat.warehouse_code),seat.warehouse_name),
                    is_primary=True,active=True,use_for_stock=True,version=1))
    db.flush()


def scoped_query(db,user):
    query=select(Link)
    scope=delegation_scope(user,db)
    if scope is not None:
        keys=[and_(Link.company_code==int(company),Link.delegation_code==code) for company,code in scope if company.isdigit()]
        query=query.where(or_(*keys) if keys else false())
    return query


@router.get('/options')
def options(db:Session=Depends(get_db),user:User=Depends(reader)):
    seats,warehouses=source()
    seats=[seat for seat in seats if can_operate_delegation(user,db,seat.company,seat.code)]
    companies={seat.company for seat in seats}
    return {'can_edit':user.role=='ADMIN','delegations':[{'company_code':s.company,'code':s.code,'name':s.name,
        'primary_warehouse_code':s.warehouse_code} for s in seats],
        'warehouses':[w for w in warehouses if w['company_code'] in companies]}


@router.get('/assignments')
def assignments(company_code:int|None=Query(None,ge=0),delegation_code:str|None=Query(None,max_length=40),
        stock_only:bool=False,db:Session=Depends(get_db),user:User=Depends(reader)):
    query=scoped_query(db,user)
    if company_code is not None:query=query.where(Link.company_code==company_code)
    if delegation_code is not None:query=query.where(Link.delegation_code==delegation_code)
    if stock_only:query=query.where(Link.active.is_(True),Link.use_for_stock.is_(True))
    return [payload(row) for row in db.scalars(query.order_by(Link.company_code,Link.delegation_code,Link.is_primary.desc(),Link.warehouse_code))]


@router.post('/sync')
def sync(db:Session=Depends(get_db),user:User=Depends(manager)):
    seats,warehouses=source()
    synchronize(db,seats,warehouses)
    audit(db,user,'DELEGATION_WAREHOUSES_SYNCED','DELEGATION_WAREHOUSES','EXIT',{'delegations':len(seats)})
    commit(db)
    return {'delegations':len(seats)}


class LinkInput(BaseModel):
    company_code:int=Field(ge=0,le=2147483647)
    delegation_code:str=Field(min_length=1,max_length=40)
    warehouse_code:str=Field(min_length=1,max_length=40)
    active:bool=True
    use_for_stock:bool=True
    expected_version:int|None=Field(None,ge=1)

    @field_validator('delegation_code','warehouse_code')
    @classmethod
    def trim(cls,value):
        value=value.strip()
        if not value:raise ValueError('Indica un código')
        return value


@router.put('/assignments')
def save(body:LinkInput,db:Session=Depends(get_db),user:User=Depends(manager)):
    seats,warehouses=source()
    seat=next((s for s in seats if (s.company,s.code)==(body.company_code,body.delegation_code)),None)
    if seat is None:raise HTTPException(422,'La delegación no pertenece a esa empresa en EXIT')
    warehouse=next((w for w in warehouses if (w['company_code'],w['code'])==(body.company_code,body.warehouse_code)),None)
    if warehouse is None:raise HTTPException(422,'Selecciona un almacén de la misma empresa existente en EXIT')
    # Validate the user's version before source synchronization increments any version.
    lock(db,seat.company,seat.code)
    row=db.get(Link,(seat.company,seat.code,body.warehouse_code),with_for_update=True)
    if row is not None and row.version!=body.expected_version:
        raise HTTPException(409,'Otra persona modificó esta relación. Actualiza la lista.')
    if row is None and body.expected_version is not None:
        raise HTTPException(409,'La relación ya no existe. Actualiza la lista.')
    previous=payload(row) if row else None
    synchronize(db,[seat],warehouses)
    row=db.get(Link,(seat.company,seat.code,body.warehouse_code))
    if row is None:
        row=Link(company_code=seat.company,delegation_code=seat.code,warehouse_code=body.warehouse_code,
            delegation_name=seat.name,warehouse_name=warehouse['name'],is_primary=False,version=0)
        db.add(row)
    row.active=body.active;row.use_for_stock=body.use_for_stock;row.updated_by=user.id;row.version+=1
    audit(db,user,'DELEGATION_WAREHOUSE_SAVED','DELEGATION_WAREHOUSE',f'{seat.id}:{row.warehouse_code}',
        {'previous':previous,'active':body.active,'use_for_stock':body.use_for_stock})
    commit(db);return payload(row)
