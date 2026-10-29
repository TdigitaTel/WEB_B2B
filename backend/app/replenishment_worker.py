"""Persistent, serialized replenishment queue. Run in its own container, never in the API."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import logging
import time
import uuid
from sqlalchemy import insert, select, text
from .db import SessionLocal, engine
from .models import ReplenishmentJob as Job, ReplenishmentBatch as Batch, ReplenishmentScenario as Scenario, ReplenishmentResult as Result
from .replenishment import RunInput, enrich_source, selected_product_codes
from .replenishment_engine import prepare_context, calculate_article, annotate_central, summarize
from .replenishment_source import list_replenishment_codes, read_replenishment_source

logger=logging.getLogger(__name__)
BATCH_SIZE=1000
LOCK_KEY=724130291


def now():return datetime.now(timezone.utc)


def digest(value):
    checksum=hashlib.sha256()
    for part in json.JSONEncoder(sort_keys=True,ensure_ascii=False).iterencode(value):checksum.update(part.encode())
    return checksum.hexdigest()


class LostClaim(Exception):pass


def owned(db,job_id,token):
    job=db.scalar(select(Job).where(Job.id==job_id).with_for_update().execution_options(populate_existing=True))
    if job.status!='RUNNING' or job.worker_token!=token:raise LostClaim()
    return job


@contextmanager
def worker_lock():
    # A session advisory lock prevents simultaneous workers, including during a rolling deployment.
    # The dedicated connection is held for the entire job and released automatically on process death.
    if engine.dialect.name!='postgresql':
        yield True
        return
    with engine.connect() as connection:
        acquired=connection.scalar(text('SELECT pg_try_advisory_lock(:key)'),{'key':LOCK_KEY})
        connection.commit()
        try:yield acquired
        finally:
            if acquired:
                connection.execute(text('SELECT pg_advisory_unlock(:key)'),{'key':LOCK_KEY})
                connection.commit()


def initialize(job_id,token):
    with SessionLocal() as db:
        job=owned(db,job_id,token)
        if job.scenario_id:return
        request=RunInput.model_validate(job.request)
        job.phase='Identificando los artículos seleccionados en EXIT';db.commit()
        selected=selected_product_codes(db,request.filters)
        codes=list_replenishment_codes(selected,job.article_limit)
        job=owned(db,job_id,token)
        source={'batched':True,'source_articles':len(codes),'articles':[], 'sales':[], 'stocks':[],
            'captured_at':now().isoformat(),'extraction_started_at':job.started_at.isoformat(),
            'article_limit':job.article_limit,'company':1,'sales_delegations':['00','01','02','04','05'],
            'start':request.filters.date_from.isoformat(),'end':request.filters.date_to.isoformat()}
        scenario=Scenario(created_by=job.created_by,source_snapshot=source,source_fingerprint='',
            filters=request.filters.model_dump(mode='json'),policies_snapshot=[],
            temporary_parameters=request.temporary_parameters,summary={})
        db.add(scenario);db.flush();job.scenario_id=scenario.id
        job.total_articles=len(codes);job.total_batches=(len(codes)+BATCH_SIZE-1)//BATCH_SIZE
        db.add_all([Batch(job_id=job.id,number=index//BATCH_SIZE+1,codes=codes[index:index+BATCH_SIZE])
                    for index in range(0,len(codes),BATCH_SIZE)])
        job.phase=f'Preparados {len(codes):,} artículos en {job.total_batches} bloques';db.commit()


def process_batch(job_id,token):
    with SessionLocal() as db:
        job=owned(db,job_id,token)
        batch=db.scalar(select(Batch).where(Batch.job_id==job.id,Batch.fingerprint.is_(None)).order_by(Batch.number).limit(1))
        if batch is None:return False
        if batch.attempts>=3:
            raise ValueError('El proceso se interrumpió tres veces en el mismo bloque. Revisa la memoria y los registros del proceso de reposición antes de repetir el cálculo.')
        request=RunInput.model_validate(job.request)
        batch.attempts+=1;job.phase=f'Consultando EXIT · bloque {batch.number} de {job.total_batches}'
        batch_id=batch.id;codes=list(batch.codes);number=batch.number;db.commit()
        # End the DB session before expensive I/O/CPU work: the website keeps its connection pool.
    source=read_replenishment_source(request.filters.date_from,request.filters.date_to,codes,BATCH_SIZE)
    if len(source['articles'])!=len(codes) or {row['sku'] for row in source['articles']}!=set(codes):
        raise ValueError('La selección de artículos cambió en EXIT durante el cálculo. Vuelve a calcular para obtener un conjunto completo.')
    with SessionLocal() as db:
        job=owned(db,job_id,token);enrich_source(db,source)
        job.phase=f'Calculando y guardando · bloque {number} de {job.total_batches}';db.commit()
    context=prepare_context(source,request.filters.delegations,[],request.temporary_parameters)
    results=[calculate_article(article,delegation,context) for article in source['articles'] for delegation in request.filters.delegations]
    # All delegations for an article stay together: central coverage remains a joint check.
    annotate_central(results,source)
    summary=summarize(results)
    for result in results:result['source_batch']=number
    with SessionLocal() as db:
        job=owned(db,job_id,token)
        batch=db.get(Batch,batch_id)
        if batch.fingerprint is not None:raise LostClaim()
        db.execute(insert(Result),[{'scenario_id':job.scenario_id,'sku':row['sku'],'delegation':row['delegation'],'payload':row} for row in results])
        batch.source=source;batch.fingerprint=digest(source)
        scenario=db.get(Scenario,job.scenario_id)
        previous=scenario.summary
        merged={key:previous.get(key,0)+value for key,value in summary.items() if key!='average_coverage_days'}
        merged['_coverage_count']=previous.get('_coverage_count',0)+sum(row['daily_mean']>0 for row in results)
        merged['_coverage_sum']=previous.get('_coverage_sum',0)+sum(row['target_stock']/row['daily_mean'] for row in results if row['daily_mean']>0)
        scenario.summary=merged
        scenario.source_snapshot={**scenario.source_snapshot,'captured_at':source['captured_at']}
        job.processed_articles+=len(codes);job.completed_batches+=1
        job.phase=f'Guardados {job.processed_articles:,} de {job.total_articles:,} artículos'
        # Sources, results and progress are atomic per batch. A restart never duplicates a committed batch.
        db.commit()
    return True


def publish(job_id,token):
    with SessionLocal() as db:
        job=owned(db,job_id,token)
        if job.completed_batches!=job.total_batches or job.processed_articles!=job.total_articles:
            raise ValueError('No se han guardado todos los bloques; no se publicará un resultado incompleto.')
        scenario=db.get(Scenario,job.scenario_id)
        fingerprints=db.scalars(select(Batch.fingerprint).where(Batch.job_id==job.id).order_by(Batch.number)).all()
        if len(fingerprints)!=job.total_batches or any(value is None for value in fingerprints):
            raise ValueError('Faltan bloques de origen; el cálculo no puede publicarse.')
        summary=dict(scenario.summary)
        count=summary.pop('_coverage_count',0);coverage=summary.pop('_coverage_sum',0)
        summary['average_coverage_days']=coverage/count if count else None
        scenario.summary=summary;scenario.source_fingerprint=digest(fingerprints)
        job.status='COMPLETED';job.phase='Cálculo completo y publicado';job.finished_at=now();job.error=None
        db.commit()


def process_job(job_id,token):
    try:
        initialize(job_id,token)
        while process_batch(job_id,token):pass
        publish(job_id,token)
    except LostClaim:
        logger.warning('Se cedió la ejecución de reposición %s a otro proceso',job_id)
    except Exception as exc:
        logger.exception('Error en el cálculo de reposición %s',job_id)
        with SessionLocal() as db:
            job=owned(db,job_id,token)
            job.status='FAILED';job.phase='Cálculo interrumpido; no se ha publicado el resultado parcial';job.finished_at=now()
            job.error=str(exc) if isinstance(exc,ValueError) else 'No se pudo completar la consulta o el cálculo. Revisa la conexión con EXIT y los registros de reposición. El resultado anterior se conserva.'
            db.commit()


def process_one():
    with worker_lock() as acquired:
        if not acquired:return False
        with SessionLocal() as db:
            # A RUNNING job can only be reclaimed once the previous process has released its global lock.
            job=db.scalar(select(Job).where(Job.status.in_(['QUEUED','RUNNING'])).order_by(Job.id).with_for_update().limit(1))
            if job is None:return False
            token=str(uuid.uuid4());job.status='RUNNING';job.worker_token=token
            job.started_at=job.started_at or now();job.phase='Iniciando cálculo por bloques';job_id=job.id;db.commit()
        process_job(job_id,token)
        return True


def main():
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            if not process_one():time.sleep(2)
        except Exception:
            logger.exception('Error del proceso de reposición; se volverá a consultar la cola')
            time.sleep(5)


if __name__=='__main__':main()
