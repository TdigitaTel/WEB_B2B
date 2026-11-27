"""Redistribution queue: saved sources only, atomic batches of at most 1,000 SKUs."""
from datetime import datetime, timezone
import hashlib
import json
import logging
import uuid
from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select
from .db import SessionLocal
from .models import RedistributionJob as Job, RedistributionBatch as Batch, ReplenishmentScenario as Scenario, ReplenishmentResult as Result
from .replenishment_engine import ConsumptionBasis, BASIS_LABELS
from .replenishment_source import DELEGATIONS, HARD_MAX_ARTICLES
from .replenishment_saved import current_calculations, calculate_redistribution

BATCH_SIZE=1000
logger=logging.getLogger(__name__)

class Selection(BaseModel):
    q:str=Field('',max_length=200)
    skus:list[str]=Field(default_factory=list,max_length=HARD_MAX_ARTICLES)
    area_id:int|None=Field(None,gt=0)
    family_id:int|None=Field(None,gt=0)
    subfamily_id:int|None=Field(None,gt=0)
    type_id:int|None=Field(None,gt=0)
    model_config={'extra':'forbid'}

class Request(BaseModel):
    reserve_days:int=Field(15,ge=1,le=365)
    consumption_basis:ConsumptionBasis='MEAN'
    filters:Selection=Field(default_factory=Selection)
    model_config={'extra':'forbid'}


def now():return datetime.now(timezone.utc)
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def snapshot(db):
    current=current_calculations(db)
    missing=[{'code':d,'name':name} for d,name in DELEGATIONS.items() if d not in current]
    if missing:raise HTTPException(409,{'message':'Faltan cálculos guardados. Calcula todas las delegaciones antes de redistribuir.','missing_delegations':missing})
    output=[]
    for code in DELEGATIONS:
        row=db.execute(select(Scenario.id,Scenario.version,Scenario.source_fingerprint).where(Scenario.id==current[code].scenario_id).with_for_update()).first()
        if not row:raise HTTPException(409,'Uno de los cálculos guardados ya no está disponible. Actualiza la lista.')
        output.append({'delegation':code,'scenario_id':row.id,'version':row.version,'fingerprint':row.source_fingerprint})
    return output


def validate_snapshot(db,expected):
    if snapshot(db)!=expected:raise HTTPException(409,'Los cálculos guardados han cambiado. Vuelve a calcular la redistribución con la nueva información.')


def selected_codes(db,expected,filters):
    selected=set()
    codes=list(dict.fromkeys(code.strip() for code in filters.skus if code.strip()))
    if any(len(code)>50 for code in codes):raise HTTPException(422,'Código de material demasiado largo')
    for item in expected:
        query=select(Result.sku).where(Result.scenario_id==item['scenario_id'],Result.delegation==item['delegation'])
        for key in ('area_id','family_id','subfamily_id','type_id'):
            value=getattr(filters,key)
            if value is not None:query=query.where(Result.payload[key].as_integer()==value)
        if filters.q.strip():
            term=filters.q.strip().lower()
            query=query.where(or_(Result.sku.ilike('%'+term.replace('!','!!').replace('%','!%').replace('_','!_')+'%',escape='!'),
                Result.payload['description'].as_string().ilike('%'+term.replace('!','!!').replace('%','!%').replace('_','!_')+'%',escape='!')))
        # Keep IN parameters bounded, also for SQLite tests and SQL Server-independent operation.
        groups=[codes[i:i+1000] for i in range(0,len(codes),1000)] if codes else [None]
        for group in groups:
            selected.update(db.scalars(query.where(Result.sku.in_(group)) if group is not None else query))
        if len(selected)>HARD_MAX_ARTICLES:raise HTTPException(422,'La selección supera 100.000 materiales. Acota los filtros.')
    return sorted(selected)


def enqueue(db,user,request):
    expected=snapshot(db)
    active=db.scalar(select(Job).where(Job.created_by==user.id,Job.status.in_(['QUEUED','RUNNING'])).order_by(Job.id.desc()))
    if active:
        if active.request==request.model_dump() and active.snapshot==expected:return active
        raise HTTPException(409,'Ya tienes una redistribución en curso. Espera a que termine antes de iniciar otra.')
    job=Job(created_by=user.id,request=request.model_dump(),snapshot=expected)
    db.add(job);db.flush()
    return job


def owned(db,job_id,token):
    job=db.scalar(select(Job).where(Job.id==job_id).with_for_update().execution_options(populate_existing=True))
    if not job or job.status!='RUNNING' or job.worker_token!=token:raise RuntimeError('La redistribución cambió de proceso responsable')
    return job


def initialize(job_id,token):
    with SessionLocal() as db:
        job=owned(db,job_id,token)
        if job.initialized:return
        job.phase='Identificando materiales con los filtros seleccionados';db.commit()
        job=owned(db,job_id,token);validate_snapshot(db,job.snapshot)
        codes=selected_codes(db,job.snapshot,Selection.model_validate(job.request['filters']))
        job.total_articles=len(codes);job.total_batches=(len(codes)+999)//1000
        db.add_all([Batch(job_id=job.id,number=i//1000+1,codes=codes[i:i+1000]) for i in range(0,len(codes),1000)])
        job.initialized=True;job.phase=f'Preparados {len(codes):,} materiales en {job.total_batches} bloques';db.commit()


def process_batch(job_id,token):
    with SessionLocal() as db:
        job=owned(db,job_id,token);validate_snapshot(db,job.snapshot)
        batch=db.scalar(select(Batch).where(Batch.job_id==job.id,Batch.fingerprint.is_(None)).order_by(Batch.number).limit(1))
        if not batch:return False
        if batch.attempts>=3:raise ValueError('El bloque se interrumpió tres veces. Revisa el registro del servidor antes de volver a calcular.')
        batch.attempts+=1;job.phase=f'Procesando bloque {batch.number} de {job.total_batches} · hasta 1.000 materiales';db.commit()
        # Registry/scenario locks are held only for this block, not for the whole calculation.
        job=owned(db,job_id,token);validate_snapshot(db,job.snapshot)
        proposal=calculate_redistribution(db,job.request['consumption_basis'],batch.codes,reserve_days=job.request.get('reserve_days'))
        # Details are fetched only on demand, never as part of table pagination.
        details=[move.pop('calculation_detail',None) for move in proposal['movements']]
        batch.result={key:proposal[key] for key in ('movements','unmet_needs','material_warnings')}|{'movement_details':details}
        batch.fingerprint=digest(batch.result)
        job.summary={key:job.summary.get(key,0)+value for key,value in proposal['summary'].items()}
        job.processed_articles+=len(batch.codes);job.completed_batches+=1
        job.phase=f'Guardados {job.processed_articles:,} de {job.total_articles:,} materiales'
        # Result and progress commit together: reclaiming a RUNNING job never duplicates a block.
        db.commit()
    return True


def publish(job_id,token):
    with SessionLocal() as db:
        job=owned(db,job_id,token);validate_snapshot(db,job.snapshot)
        if job.completed_batches!=job.total_batches or job.processed_articles!=job.total_articles:raise ValueError('Faltan bloques; no se publicará la propuesta parcial')
        # Empty material selection still returns the source metadata and a valid empty workbook.
        proposal=calculate_redistribution(db,job.request['consumption_basis'],[],reserve_days=job.request.get('reserve_days'))
        job.summary={key:job.summary.get(key,0) for key in proposal['summary']}
        metadata={key:proposal[key] for key in ('calculations','warnings','read_only_exit','reserve_days','consumption_basis','consumption_basis_label')}
        metadata.update(summary=job.summary,filters=job.request['filters'],analyzed_materials=job.total_articles)
        signatures=list(db.scalars(select(Batch.fingerprint).where(Batch.job_id==job.id).order_by(Batch.number)))
        if any(value is None for value in signatures):raise ValueError('Faltan resultados de bloques')
        metadata['fingerprint']=digest({'request':job.request,'snapshot':job.snapshot,'blocks':signatures,'summary':job.summary})
        job.result_metadata=metadata;job.status='COMPLETED';job.phase='Redistribución completa y guardada';job.finished_at=now()
        # Bound persistent storage: preserve the last two successful proposals per operator.
        old_ids=list(db.scalars(select(Job.id).where(Job.created_by==job.created_by,Job.status=='COMPLETED',Job.id!=job.id).order_by(Job.id.desc()).offset(1)))
        if old_ids:
            db.execute(delete(Batch).where(Batch.job_id.in_(old_ids)));db.execute(delete(Job).where(Job.id.in_(old_ids)))
        db.commit()


def process_one_unlocked():
    """Called under the replenishment worker's global advisory lock."""
    with SessionLocal() as db:
        job=db.scalar(select(Job).where(Job.status.in_(['QUEUED','RUNNING'])).order_by(Job.id).with_for_update().limit(1))
        if not job:return False
        token=str(uuid.uuid4());job.worker_token=token;job.status='RUNNING';job.started_at=job.started_at or now();job_id=job.id;db.commit()
    try:
        initialize(job_id,token)
        while process_batch(job_id,token):pass
        publish(job_id,token)
    except Exception as exc:
        logger.exception('Error de redistribución %s',job_id)
        with SessionLocal() as db:
            job=owned(db,job_id,token);job.status='FAILED';job.finished_at=now();job.phase='Redistribución interrumpida; no se ha publicado un resultado parcial'
            job.error=str(exc.detail) if isinstance(exc,HTTPException) and isinstance(exc.detail,str) else str(exc) if isinstance(exc,ValueError) else 'No se pudo completar la redistribución. Revisa el registro del servidor; los cálculos guardados se conservan.'
            db.commit()
    return True


def public(job):
    return {'id':job.public_id,'status':job.status,'phase':job.phase,'error':job.error,'filters':job.request['filters'],
        'reserve_days':job.request.get('reserve_days'),'consumption_basis':job.request['consumption_basis'],'selection_ready':job.initialized,'batch_size':BATCH_SIZE,'total_articles':job.total_articles,
        'processed_articles':job.processed_articles,'total_batches':job.total_batches,'completed_batches':job.completed_batches,
        'progress':100 if job.status=='COMPLETED' else min(99,int(job.processed_articles*100/max(1,job.total_articles))),
        'result':job.result_metadata if job.status=='COMPLETED' else None}


def get_job(db,public_id,user):
    job=db.scalar(select(Job).where(Job.public_id==public_id,Job.created_by==user.id))
    if not job:raise HTTPException(404,'Redistribución no encontrada')
    return job


def entries(db,job,kind):
    for number,rows in db.execute(select(Batch.number,Batch.result[kind]).where(Batch.job_id==job.id).order_by(Batch.number).execution_options(yield_per=1)):
        for index,row in enumerate(rows or []):
            yield {**row,'detail_id':f'{number}-{index}'} if kind=='movements' else row


def result_page(db,job,page=1,page_size=100,q=''):
    if job.status!='COMPLETED':raise HTTPException(409,'La redistribución todavía no está completa')
    validate_snapshot(db,job.snapshot)
    term=q.strip().lower();offset=(page-1)*page_size;movements=[];count=0
    for movement in entries(db,job,'movements'):
        if term and term not in ' '.join(str(movement[key]) for key in ('sku','description','from_delegation','to_delegation')).lower():continue
        if offset<=count<offset+page_size:movements.append(movement)
        count+=1
    from itertools import islice
    return {**job.result_metadata,'movements':movements,'movement_total':count,'page':page,'page_size':page_size,
        'unmet_needs':list(islice(entries(db,job,'unmet_needs'),100)),
        'material_warnings':list(islice(entries(db,job,'material_warnings'),100))}


def movement_detail(db,job,detail_id):
    import re
    if job.status!='COMPLETED':raise HTTPException(409,'La redistribución todavía no está completa')
    if not re.fullmatch(r'[1-9][0-9]{0,7}-(0|[1-9][0-9]{0,7})',detail_id):raise HTTPException(404,'Movimiento no encontrado')
    validate_snapshot(db,job.snapshot)
    number,index=map(int,detail_id.split('-'))
    batch=db.execute(select(Batch.result['movements'],Batch.result['movement_details']).where(Batch.job_id==job.id,Batch.number==number)).first()
    if not batch or index>=len(batch[0] or []):raise HTTPException(404,'Movimiento no encontrado')
    move=batch[0][index];detail=(batch[1] or [])[index] if index<len(batch[1] or []) else None
    reconstructed=False
    if not detail:
        # Compatibility for proposals created before details were persisted.
        # Reconstruct ONE material from the same frozen calculation, never EXIT.
        proposal=calculate_redistribution(db,job.request['consumption_basis'],[move['sku']],reserve_days=job.request.get('reserve_days'))
        match=next((row for row in proposal['movements'] if all(row[key]==move[key] for key in ('sku','from_delegation','to_delegation','kind','quantity'))),None)
        if not match:raise HTTPException(409,'No se puede verificar el detalle de esta propuesta antigua. Vuelve a calcular la redistribución.')
        detail=match.get('calculation_detail');reconstructed=True
    if not detail:raise HTTPException(409,'Esta propuesta no contiene el detalle. Vuelve a calcular la redistribución.')
    return {'movement':move,'detail':detail,'reconstructed':reconstructed,'consumption_basis':job.request['consumption_basis'],
        'consumption_basis_label':BASIS_LABELS[job.request['consumption_basis']],'fingerprint':job.result_metadata['fingerprint']}
