"""Read-only, persistent procurement queue and paginated saved proposals."""
from datetime import datetime, timezone
import hashlib
import io
import json
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.orm import Session
from .db import get_db, SessionLocal
from .models import User
from .procurement_models import ProcurementJob as Job, ProcurementBatch as Batch, ProcurementResult as Result
from .replenishment import Filters, operator, enrich_source, selected_product_codes, module_settings, audit
from .replenishment_source import list_replenishment_codes, read_replenishment_source, read_procurement_terms
from .category_visibility import hidden_codes
from .procurement_engine import calculate

logger=logging.getLogger(__name__)
router=APIRouter(prefix='/api/v1/store/replenishment/procurement',tags=['procurement'],dependencies=[Depends(operator)])

class PurchaseFilters(Filters):
    brand:str=Field('',max_length=120)

class Request(BaseModel):
    model_config=ConfigDict(extra='forbid')
    filters:PurchaseFilters=Field(default_factory=PurchaseFilters)
    use_safety_stock:bool=True
    service_level:float=Field(95,ge=50,le=99.9,allow_inf_nan=False)


def payload(row):
    return {'id':row.public_id,'status':row.status,'phase':row.phase,'request':row.request,'created_at':row.created_at,
        'updated_at':row.updated_at,'total_articles':row.total_articles,'processed_articles':row.processed_articles,
        'total_batches':row.total_batches,'completed_batches':row.completed_batches,
        'progress':100 if row.status=='COMPLETED' else min(99,int(row.processed_articles*100/max(1,row.total_articles))),
        'summary':row.summary if row.status=='COMPLETED' else None,'error':row.error}


def get_job(db,public_id,user):
    row=db.scalar(select(Job).where(Job.public_id==public_id,Job.created_by==user.id))
    if not row:raise HTTPException(404,'Propuesta de compra no encontrada')
    return row

@router.post('/jobs',status_code=202)
def enqueue(body:Request,db:Session=Depends(get_db),user:User=Depends(operator)):
    # A purchase proposal always covers the whole network. Never accidentally buy for a subset.
    if body.filters.delegations!=['00','01','02','04','05']:
        raise HTTPException(422,'Aprovisionamiento debe incluir Almeiras y las cuatro delegaciones.')
    db.scalar(select(User).where(User.id==user.id).with_for_update())
    existing=db.scalar(select(Job).where(Job.created_by==user.id,Job.status.in_(['QUEUED','RUNNING'])).order_by(Job.id))
    if existing:
        if existing.request!=body.model_dump(mode='json'):raise HTTPException(409,'Ya tienes un cálculo de compra en curso. Espera a que termine antes de cambiar los filtros.')
        return payload(existing)
    row=Job(created_by=user.id,request=body.model_dump(mode='json'),summary={'consumption_method':'NET_PERIOD_V2'});db.add(row);db.flush()
    audit(db,user,'PROCUREMENT_QUEUED',row.public_id,{'request':row.request,'batch_size':1000});db.commit()
    return payload(row)

@router.get('/jobs/current')
def current(db:Session=Depends(get_db),user:User=Depends(operator)):
    last=db.scalar(select(Job).where(Job.created_by==user.id).order_by(Job.id.desc()).limit(1))
    completed=db.scalar(select(Job).where(Job.created_by==user.id,Job.status=='COMPLETED').order_by(Job.id.desc()).limit(1))
    return {'job':payload(last) if last else None,'latest_result':payload(completed) if completed else None}

@router.get('/jobs/{public_id}')
def status(public_id:str,db:Session=Depends(get_db),user:User=Depends(operator)):
    return payload(get_job(db,public_id,user))


def result_query(row,basis,q='',area_id=None,family_id=None,subfamily_id=None,type_id=None,brand='',only_buy=False):
    data=Result.payload
    query=select(Result).where(Result.job_id==row.id)
    for key,value in [('area_id',area_id),('family_id',family_id),('subfamily_id',subfamily_id),('type_id',type_id)]:
        if value is not None:query=query.where(data[key].as_integer()==value)
    if brand:query=query.where(data['brand_code'].as_string()==brand)
    if q.strip():
        text=q.strip().lower().replace('!','!!').replace('%','!%').replace('_','!_')
        query=query.where(or_(*(func.lower(column).like('%'+text+'%',escape='!') for column in (Result.sku,data['description'].as_string(),data['brand_name'].as_string()))))
    if only_buy:query=query.where(data['variants'][basis]['quantity'].as_float()>0)
    return query


def public_result(stored,basis):
    result=dict(stored.payload);result['proposal']=result['variants'][basis];return result


def cell_text(value):return ILLEGAL_CHARACTERS_RE.sub('',value)


def append(sheet,values):
    cells=[]
    for value in values:
        if isinstance(value,str):
            cell=WriteOnlyCell(sheet,value=cell_text(value));cell.data_type='s';cells.append(cell)
        else:cells.append(value)
    sheet.append(cells)


def published(row):
    if row.status!='COMPLETED':raise HTTPException(409,'La propuesta todavía no está completa. Consulta su progreso.')

@router.get('/jobs/{public_id}/results')
def results(public_id:str,basis:str=Query('MEAN',pattern='^(MEAN|MEDIAN|MODE)$'),q:str=Query('',max_length=200),
    area_id:int|None=None,family_id:int|None=None,subfamily_id:int|None=None,type_id:int|None=None,
    brand:str=Query('',max_length=120),only_buy:bool=False,page:int=Query(1,ge=1),page_size:int=Query(50,ge=1,le=100),
    db:Session=Depends(get_db),user:User=Depends(operator)):
    job=get_job(db,public_id,user);published(job)
    query=result_query(job,basis,q,area_id,family_id,subfamily_id,type_id,brand,only_buy)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    brands=db.execute(select(Result.payload['brand_code'].as_string(),Result.payload['brand_name'].as_string()).where(Result.job_id==job.id).distinct()).all()
    rows=db.scalars(query.order_by(Result.sku).offset((page-1)*page_size).limit(page_size)).all()
    return {'items':[public_result(row,basis) for row in rows],'total':total,
        'brands':[{'code':code or '', 'name':name or code or 'Sin marca'} for code,name in sorted(brands,key=lambda pair:str(pair[1] or pair[0] or ''))]}

@router.get('/jobs/{public_id}/export.xlsx')
def export(public_id:str,basis:str=Query('MEAN',pattern='^(MEAN|MEDIAN|MODE)$'),q:str=Query('',max_length=200),
    area_id:int|None=None,family_id:int|None=None,subfamily_id:int|None=None,type_id:int|None=None,
    brand:str=Query('',max_length=120),only_buy:bool=False,db:Session=Depends(get_db),user:User=Depends(operator)):
    job=get_job(db,public_id,user);published(job)
    book=Workbook(write_only=True);sheet=book.create_sheet('Compra sugerida')
    append(sheet,['Propuesta de compra · '+basis]);append(sheet,['Filtros de cálculo',cell_text(json.dumps(job.request,ensure_ascii=False))])
    append(sheet,['Filtros de consulta',cell_text(json.dumps(dict(q=q,area_id=area_id,family_id=family_id,subfamily_id=subfamily_id,type_id=type_id,brand=brand,only_buy=only_buy),ensure_ascii=False))])
    append(sheet,['No genera pedidos ni modifica EXIT. Red completa: Almeiras + cuatro delegaciones.'])
    append(sheet,['Objetivo = consumo diario × (días de cobertura + plazo de entrega) + seguridad. Compra = max(0, objetivo − (stock + entradas − salidas)).'])
    append(sheet,['Entradas pendientes sin fecha: verificar llegada y compensación de traspasos internos. EX_multiplo es de despacho: validar el formato de compra con proveedor.'])
    append(sheet,['Código','Descripción','Marca','Familia','Subfamilia','Tipo','Unidad','Stock red','Stock Almeiras','Entradas','Salidas','Disponible',
        'Referencia mensual guardada (30 días en NET_PERIOD_V2)','Base diaria','Desviación diaria','Cobertura EXIT (días)','Entrega EXIT (días)','Seguridad','Objetivo','Compra base','Con múltiplo EXIT','Múltiplo EXIT','Flag','Avisos','Datos EXIT','Ventas del periodo','Devoluciones del periodo','Neto del periodo','Días analizados','Método de consumo'])
    query=result_query(job,basis,q,area_id,family_id,subfamily_id,type_id,brand,only_buy)
    for stored in db.scalars(query.order_by(Result.sku).execution_options(yield_per=100)):
        row=stored.payload;p=row['variants'][basis]
        values=[row['sku'],row['description'],row.get('brand_name'),row.get('family'),row.get('subfamily'),row.get('type'),row.get('unit_type'),
            row['stock'],row['central_stock'],row['incoming'],row['outgoing'],row['inventory_position'],row['monthly_mean'],p['daily_reference'],row['daily_std'],
            row['coverage_days'],row['lead_days'],p['safety_stock'],p['target_stock'],p['quantity'],p['quantity_with_multiple'],row.get('exit_multiple'),
            row['exceptionality']['level'],'; '.join(row['notes']),row['captured_at'],row.get('gross_sales'),row.get('returns'),row['gross_sales']-row['returns'] if row.get('gross_sales') is not None and row.get('returns') is not None else None,row['observed_days'],row.get('consumption_method','MONTHLY_NORMALIZED_V1')]
        append(sheet,[cell_text(value) if isinstance(value,str) else value for value in values])
    stream=io.BytesIO();book.save(stream)
    return Response(stream.getvalue(),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="aprovisionamiento.xlsx"'})


def owned(db,jid,token):
    row=db.scalar(select(Job).where(Job.id==jid).with_for_update().execution_options(populate_existing=True))
    if not row or row.status!='RUNNING' or row.worker_token!=token:raise ValueError('Se perdió la propiedad del cálculo de compra')
    return row


def process_job(jid,token):
    try:
        with SessionLocal() as db:
            job=owned(db,jid,token);request=Request.model_validate(job.request)
            if not job.initialized:
                job.phase='Seleccionando materiales';db.commit()
                selected=selected_product_codes(db,request.filters);limit=module_settings(db)['article_limit']
                codes=list_replenishment_codes(selected,limit,hidden_codes(db) if selected is None else [])
                if request.filters.brand.strip():
                    brand=request.filters.brand.strip().casefold();chosen=[]
                    for offset in range(0,len(codes),1000):
                        metadata=read_procurement_terms(codes[offset:offset+1000])
                        chosen.extend(code for code,value in metadata.items() if brand in (value['brand_code']+' '+value['brand_name']).casefold())
                    codes=chosen
                job=owned(db,jid,token)
                for index in range(0,len(codes),1000):db.add(Batch(job_id=jid,number=index//1000+1,codes=codes[index:index+1000]))
                job.total_articles=len(codes);job.total_batches=(len(codes)+999)//1000;job.initialized=True;db.commit()
        while True:
            with SessionLocal() as db:
                job=owned(db,jid,token)
                batch=db.scalar(select(Batch).where(Batch.job_id==jid,Batch.fingerprint.is_(None)).order_by(Batch.number).limit(1))
                if batch is None:break
                if batch.attempts>=3:raise ValueError('El mismo bloque de compra se interrumpió tres veces; revisa los registros y la memoria.')
                method=job.summary.get('consumption_method','MONTHLY_NORMALIZED_V1')
                batch.attempts+=1;codes=list(batch.codes);bid=batch.id
                job.phase=f'Consultando y calculando bloque {batch.number} de {job.total_batches}';db.commit()
            source=read_replenishment_source(request.filters.date_from,request.filters.date_to,codes,1000)
            source['consumption_method']=method
            if {a['sku'] for a in source['articles']}!=set(codes) or len(source['articles'])!=len(codes):raise ValueError('La selección cambió en EXIT; vuelve a calcular.')
            metadata=read_procurement_terms(codes)
            for article in source['articles']:article.update(metadata[article['sku']])
            with SessionLocal() as db:enrich_source(db,source)
            rows=calculate(source,request.use_safety_stock,request.service_level)
            with SessionLocal() as db:
                job=owned(db,jid,token);batch=db.get(Batch,bid)
                db.execute(insert(Result),[{'job_id':jid,'sku':row['sku'],'payload':row} for row in rows])
                batch.source=source;batch.fingerprint=hashlib.sha256(json.dumps(source,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                job.processed_articles+=len(codes);job.completed_batches+=1
                summary=dict(job.summary)
                for basis in ('MEAN','MEDIAN','MODE'):
                    summary[basis]={key:summary.get(basis,{}).get(key,0)+sum(row['variants'][basis]['status']==status for row in rows) for key,status in [('buy','BUY'),('review','REVIEW'),('covered','COVERED')]}
                job.summary=summary;db.commit()
        with SessionLocal() as db:
            job=owned(db,jid,token)
            if job.processed_articles!=job.total_articles or job.completed_batches!=job.total_batches:raise ValueError('Faltan bloques de compra; no se publicará un resultado parcial.')
            job.status='COMPLETED';job.phase='Propuesta de compra completa';job.error=None
            # Retain two successful snapshots per operator; failed calculations cannot delete the previous result.
            old=list(db.scalars(select(Job.id).where(Job.created_by==job.created_by,Job.status=='COMPLETED',Job.id!=jid).order_by(Job.id.desc()).offset(1)))
            if old:
                db.execute(delete(Result).where(Result.job_id.in_(old)));db.execute(delete(Batch).where(Batch.job_id.in_(old)));db.execute(delete(Job).where(Job.id.in_(old)))
            db.commit()
    except Exception as exc:
        logger.exception('Error calculando aprovisionamiento %s',jid)
        with SessionLocal() as db:
            job=owned(db,jid,token);job.status='FAILED';job.phase='Cálculo sin completar; se conserva la propuesta anterior'
            job.error=str(exc) if isinstance(exc,ValueError) else 'No se pudo consultar o calcular la compra. Revisa los registros del proceso de reposición y la conexión con EXIT.';db.commit()


def process_one():
    from .replenishment_worker import worker_lock
    with worker_lock() as acquired:
        if not acquired:return False
        with SessionLocal() as db:
            job=db.scalar(select(Job).where(Job.status.in_(['QUEUED','RUNNING'])).order_by(Job.id).with_for_update().limit(1))
            if job is None:return False
            token=str(uuid.uuid4());job.status='RUNNING';job.worker_token=token;job.phase='Iniciando cálculo de compra';jid=job.id;db.commit()
        process_job(jid,token);return True
