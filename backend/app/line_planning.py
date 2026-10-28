"""Planificación web por línea; no escribe cantidades ni documentos en EXIT."""
from datetime import date, datetime, time, timedelta, timezone
import logging
from zoneinfo import ZoneInfo
from math import ceil, isfinite
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, AwareDatetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from .auth import audit, require_roles, current_user
from .db import get_db
from .models import Order, OrderItem, OrderLinePlanning, LinePlanningSettings, PickupSettings, User
from .operator_permissions import can_operate_delegation
from .exit_db import fetch_exit_orders_live
from .erp_db import connect_sqlserver

router=APIRouter(prefix='/api/v1/store',tags=['line-planning'])
public_router=APIRouter(prefix='/api/v1/orders',tags=['line-planning'])
operator=require_roles('OPERADOR_TIENDA','ADMIN')
TZ=ZoneInfo('Europe/Madrid')
logger=logging.getLogger(__name__)
Status=Literal['EN_STOCK','TRASLADO','PROVEEDOR','REVISAR']

class SettingsIn(BaseModel):
    transfer_days:int=Field(default=1,ge=1,le=90)

class ManualIn(BaseModel):
    line_key:str=Field(min_length=1,max_length=120)
    sku:str=Field(min_length=1,max_length=50)
    status:Status
    expected_at:AwareDatetime|None=None
    observation:str=Field(default='',max_length=1000)
    version:int=Field(ge=0)

@router.get('/line-planning-settings')
def settings(db:Session=Depends(get_db),user:User=Depends(operator)):
    row=db.get(LinePlanningSettings,1)
    return {'transfer_days':row.transfer_days if row else 1}

@router.patch('/line-planning-settings')
def save_settings(body:SettingsIn,db:Session=Depends(get_db),user:User=Depends(operator)):
    row=db.get(LinePlanningSettings,1)
    if row is None:row=LinePlanningSettings(id=1);db.add(row)
    row.transfer_days=body.transfer_days
    audit(db,user,'LINE_PLANNING_SETTINGS','SETTINGS','line-planning',body.model_dump())
    db.commit();return body.model_dump()

def windows(day,schedules):
    if not schedules or len(schedules)!=7:return []
    hours=schedules[day.weekday()]
    if not hours.get('enabled',True):return []
    return sorted((time.fromisoformat(hours[p+'_from']),time.fromisoformat(hours[p+'_to']))
        for p in ('morning','afternoon') if hours.get(p+'_from') and hours.get(p+'_to'))

def next_open(stamp,schedules):
    if not schedules or len(schedules)!=7 or not any(windows(date(2026,10,26)+timedelta(days=i),schedules) for i in range(7)):return None
    stamp=stamp.astimezone(TZ)
    for offset in range(370):
        day=stamp.date()+timedelta(days=offset)
        for opening,closing in windows(day,schedules):
            candidate=max(stamp,datetime.combine(day,opening,TZ))
            if candidate<datetime.combine(day,closing,TZ):return candidate
    return None

def transfer_date(stamp,days,schedules):
    current=stamp.astimezone(TZ);day=current.date()
    for _ in range(370):
        day+=timedelta(days=1)
        if windows(day,schedules):
            days-=1
            if days==0:return next_open(datetime.combine(day,current.timetz().replace(tzinfo=None),TZ),schedules)
    return None

def local_context(db,order):
    company,delegation=order.company_code,order.delegation_code
    lines=[{'line_key':str(item.id),'sku':item.sku,'description':item.description,'quantity':float(item.quantity),
            'pending':float(item.pending_quantity if item.pending_quantity is not None else max(0,item.quantity-(item.served_quantity or 0)))}
           for item in db.scalars(select(OrderItem).where(OrderItem.order_id==order.id).order_by(OrderItem.id))]
    return f'WEB:{order.public_id}',company,delegation,order.attention_deadline_at,lines

def resolve(db,user,order_id):
    order=db.scalar(select(Order).where(Order.public_id==order_id))
    if order:
        if not can_operate_delegation(user,db,order.company_code,order.delegation_code):raise HTTPException(404,'Pedido no encontrado')
        return local_context(db,order)
    try:records=fetch_exit_orders_live('web',exit_order_id=order_id)
    except Exception as exc:raise HTTPException(503,'No se pudo leer el pedido en EXIT') from exc
    records=[r for r in records if can_operate_delegation(user,db,r.company_code,r.store_code)]
    if len(records)!=1:raise HTTPException(404,'Pedido no encontrado o referencia ambigua')
    return external_context(db,records[0])

def external_context(db,record):
    if len({item.line_number for item in record.lines})!=len(record.lines):raise HTTPException(409,'EXIT devuelve números de línea duplicados')
    if any(not item.line_number for item in record.lines):raise HTTPException(409,'EXIT no proporciona el número de línea; no se puede guardar un ajuste seguro')
    lines=[{'line_key':item.line_number,'sku':item.sku,'description':item.description,'quantity':float(item.quantity),
            'pending':float(item.pending_quantity if item.pending_quantity is not None else max(0,item.quantity-(item.served_quantity or 0)))} for item in record.lines]
    local=db.scalar(select(Order).where(Order.nro_pedido_exit==record.exit_order_id,Order.company_code==record.company_code,Order.delegation_code==record.store_code))
    return f'EXIT:{record.company_code}:{record.exit_order_id}',record.company_code,record.store_code,local.attention_deadline_at if local else None,lines

def source(codes):
    stocks={};days={}
    with connect_sqlserver() as connection,connection.cursor() as cursor:
        for offset in range(0,len(codes),500):
            batch=codes[offset:offset+500];marks=','.join(['%s']*len(batch))
            cursor.execute(f'SELECT codigoarticulo AS sku,diasreposicion AS days FROM dbo.articulos WHERE CodigoEmpresa=1 AND codigoarticulo IN ({marks})',tuple(batch))
            for row in cursor.fetchall():
                code=str(row['sku']).strip()
                if code in days:raise ValueError('Artículo duplicado en EXIT')
                value=float(row['days']) if row['days'] is not None else None
                days[code]=ceil(value) if value is not None and isfinite(value) and value>=0 else None
            cursor.execute(f'SELECT CodigoArticulo AS sku,IdDelegacion AS delegation,UnidadSaldo AS stock,PendienteServir AS outgoing FROM dbo.VIS_EX_StockVentasDelegacion WHERE CodigoArticulo IN ({marks})',tuple(batch))
            for row in cursor.fetchall():
                key=(str(row['sku']).strip(),str(row['delegation']).strip())
                if key in stocks:raise ValueError('Stock duplicado por artículo y delegación')
                value=float(row['stock'] or 0)-float(row['outgoing'] or 0)
                if not isfinite(value):raise ValueError('Stock inválido')
                stocks[key]=max(0,value)
    return stocks,days

def payload(db,key,lines):
    saved=db.get(OrderLinePlanning,key);data=saved.lines if saved else {}
    return {'lines':[{**line,**(data.get(line['line_key'],{}) if data.get(line['line_key'],{}).get('sku')==line['sku'] else {})} for line in lines],
            'version':data.get('_version',0)}

@router.get('/orders/line-planning')
def read(order_id:str=Query(max_length=100),db:Session=Depends(get_db),user:User=Depends(operator)):
    key,_,_,_,lines=resolve(db,user,order_id)
    return payload(db,key,lines)

def proposal(db,context):
    key,company,delegation,deadline,lines=context
    if len(lines)>2000:raise HTTPException(422,'El pedido supera 2.000 líneas')
    config=db.get(PickupSettings,1);schedules=(config.schedules or {}).get(f'{company}:{delegation}') if config else None
    now=datetime.now(TZ)
    base=max(now,deadline.replace(tzinfo=timezone.utc) if deadline and deadline.tzinfo is None else deadline or now)
    warning=None
    try:
        if company!=1:raise ValueError('Stock configurado únicamente para empresa 1')
        stocks,days=source(list(dict.fromkeys(line['sku'] for line in lines if line['pending']>0)))
    except Exception:
        logger.exception('No se pudieron consultar las fuentes de planificación por línea para %s',key)
        stocks,days={},{};warning='No se pudo validar el stock o el plazo en EXIT. Revisa las líneas pendientes.'
    saved=db.get(OrderLinePlanning,key)
    data=dict(saved.lines) if saved else {}
    transfer=settings(db,None)['transfer_days']
    for line in lines:
        if line['pending']<=0:continue
        old=data.get(line['line_key'],{})
        if old.get('manual') and old.get('sku')==line['sku']:continue
        sku=line['sku'];needed=line['pending'];local=stocks.get((sku,delegation),0)
        status='REVISAR';expected=None;note='Pendiente de revisión'
        if not warning:
            if local>=needed:
                status='EN_STOCK';expected=deadline;note='En stock'
                stocks[(sku,delegation)]=local-needed
            else:
                others=[(code,value) for (article,code),value in stocks.items() if article==sku and code!=delegation and value>=needed-local]
                if others:
                    code,value=sorted(others)[0];status='TRASLADO';expected=transfer_date(base,transfer,schedules);note=f'Movimiento entre delegaciones · origen {code}'
                    stocks[(sku,code)]=value-(needed-local);stocks[(sku,delegation)]=0
                elif days.get(sku) is not None:
                    status='PROVEEDOR';expected=next_open(base+timedelta(days=days[sku]),schedules);note=f'En gestión proveedor · plazo EXIT {days[sku]} días naturales'
                else:note='Sin stock suficiente; falta diasreposicion en EXIT'
        if expected is None:status='REVISAR';note+=' · revisar fecha/horario de atención' if not warning else ' · consulta EXIT no disponible'
        data[line['line_key']]={'sku':sku,'status':status,'expected_at':expected.isoformat() if expected else None,'observation':note,'manual':False,'calculated_at':now.isoformat(),'local_available':local}
    return data,warning


def preview(db,context):
    key,_,_,_,lines=context
    existing=payload(db,key,lines)
    if all(line['pending']<=0 or line.get('status') for line in existing['lines']):return existing
    data,warning=proposal(db,context)
    return {'lines':[{**line,**data.get(line['line_key'],{})} for line in lines],'version':existing['version'],'warning':warning}


@router.get('/orders/line-planning/preview')
def operator_preview(order_id:str=Query(max_length=100),db:Session=Depends(get_db),user:User=Depends(operator)):
    return preview(db,resolve(db,user,order_id))


@public_router.get('/{order_id:path}/line-planning')
def customer_preview(order_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    from .main import customer_order,customer_for,customer_code_for
    if order_id.startswith('exit:'):
        customer_for(user,db);code=customer_code_for(user,db)
        if user.own_orders_only:raise HTTPException(404,'Pedido no encontrado')
        try:records=fetch_exit_orders_live('web',exit_order_id=order_id[5:])
        except Exception as exc:raise HTTPException(503,'No se pudo consultar el pedido') from exc
        records=[record for record in records if record.customer_code==code]
        if len(records)!=1:raise HTTPException(404,'Pedido no encontrado')
        return preview(db,external_context(db,records[0]))
    # Apply the same customer and subuser ownership restrictions as order detail.
    order=customer_order(order_id,user,db)
    return preview(db,local_context(db,order))


@router.post('/orders/line-planning/calculate')
def calculate(order_id:str=Query(max_length=100),db:Session=Depends(get_db),user:User=Depends(operator)):
    context=resolve(db,user,order_id);key,_,_,_,lines=context
    row=db.scalar(select(OrderLinePlanning).where(OrderLinePlanning.order_key==key).with_for_update())
    if row is None:row=OrderLinePlanning(order_key=key,lines={});db.add(row);db.flush()
    data,warning=proposal(db,context)
    data['_version']=data.get('_version',0)+1;row.lines=data
    audit(db,user,'ORDER_LINE_PLAN_CALCULATED','ORDER',key,{'warning':warning,'lines':len(lines)})
    db.commit();return {**payload(db,key,lines),'warning':warning}

@router.patch('/orders/line-planning')
def manual(body:ManualIn,order_id:str=Query(max_length=100),db:Session=Depends(get_db),user:User=Depends(operator)):
    key,_,_,_,lines=resolve(db,user,order_id)
    if not any(line['line_key']==body.line_key and line['sku']==body.sku for line in lines):raise HTTPException(409,'La línea cambió; actualiza el pedido')
    row=db.scalar(select(OrderLinePlanning).where(OrderLinePlanning.order_key==key).with_for_update())
    if row is None:row=OrderLinePlanning(order_key=key,lines={});db.add(row)
    data=dict(row.lines)
    if data.get('_version',0)!=body.version:raise HTTPException(409,'Otro operador cambió la planificación. Vuelve a abrirla')
    previous=data.get(body.line_key)
    data[body.line_key]={**(previous or {}),'sku':body.sku,'status':body.status,'expected_at':body.expected_at.isoformat() if body.expected_at else None,'observation':body.observation,'manual':True}
    data['_version']=body.version+1;row.lines=data
    audit(db,user,'ORDER_LINE_PLAN_MANUAL','ORDER',key,{'line':body.line_key,'previous':previous,'new':data[body.line_key]})
    db.commit();return payload(db,key,lines)
