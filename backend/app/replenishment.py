"""API de simulación de reposición. Nunca genera outbox ni escribe en EXIT."""
import hashlib
import io
import json
import logging
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from openpyxl import Workbook
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session
from .auth import require_roles
from .db import get_db
from .models import (AuditEvent, MaterialArea, MaterialFamily, MaterialSubfamily, MaterialProductType, Product,
    ReplenishmentPolicy as Policy, ReplenishmentScenario as Scenario, ReplenishmentResult as Result,
    ReplenishmentAdjustment as Adjustment, ReplenishmentSettings as ModuleSettings, User)
from .replenishment_engine import Parameters, PRECEDENCE, prepare_context, calculate_article, annotate_central, summarize, rounded_dispatch
from .replenishment_source import DELEGATIONS, MAX_ARTICLES, HARD_MAX_ARTICLES, read_replenishment_source

operator=require_roles('ADMIN','OPERADOR_TIENDA')
router=APIRouter(prefix='/api/v1/store/replenishment',tags=['replenishment'],dependencies=[Depends(operator)])
logger=logging.getLogger(__name__)

def today():return datetime.now(ZoneInfo('Europe/Madrid')).date()

def validate_parameters(patch):
    try:Parameters.model_validate({**Parameters().model_dump(),**patch})
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    return patch

class Filters(BaseModel):
    date_from: date = date(2026,1,1)
    date_to: date = Field(default_factory=today)
    delegations: list[Literal['01','02','04','05']] = Field(default_factory=lambda:list(DELEGATIONS),min_length=1,max_length=4)
    area_id:int|None=None
    family_id:int|None=None
    subfamily_id:int|None=None
    type_id:int|None=None
    skus:list[str]=Field(default_factory=list,max_length=HARD_MAX_ARTICLES)
    @model_validator(mode='after')
    def dates(self):
        if self.date_from>self.date_to or self.date_to>today() or (self.date_to-self.date_from).days>1095:
            raise ValueError('El periodo debe terminar como máximo hoy y abarcar entre 1 y 1.096 días')
        self.delegations=list(dict.fromkeys(self.delegations))
        self.skus=list(dict.fromkeys(code.strip() for code in self.skus if code.strip()))
        if any(len(code)>50 for code in self.skus):raise ValueError('Código de artículo demasiado largo')
        return self

class PolicyInput(BaseModel):
    scope:Literal['GLOBAL','AREA','FAMILY','SUBFAMILY','TYPE','DELEGATION','ARTICLE_DELEGATION']
    scope_key:str=Field(min_length=1,max_length=100)
    parameters:dict=Field(default_factory=dict)
    active:bool=True

class RunInput(BaseModel):
    filters:Filters=Field(default_factory=Filters)
    temporary_parameters:dict=Field(default_factory=dict)
    source_id:str|None=None
    preview_only:bool=False

class RecalculateInput(BaseModel):
    parameters:dict=Field(default_factory=dict)

class AdjustmentInput(BaseModel):
    parameters:dict=Field(default_factory=dict)
    quantity:float|None=Field(None,ge=0,le=1e9,allow_inf_nan=False)
    excluded:bool=False
    reason:str=Field(min_length=3,max_length=500)
    expected_version:int=Field(ge=1)

def policy_payload(row):
    return {'id':row.id,'scope':row.scope,'scope_key':row.scope_key,'parameters':row.parameters,'active':row.active}

def scenario_or_404(db,public_id,lock=False):
    query=select(Scenario).where(Scenario.public_id==public_id)
    if lock:query=query.with_for_update()
    row=db.scalar(query)
    if not row:raise HTTPException(404,'Simulación no encontrada')
    return row

def result_or_404(db,scenario,result_id):
    row=db.scalar(select(Result).where(Result.id==result_id,Result.scenario_id==scenario.id))
    if not row:raise HTTPException(404,'Artículo de simulación no encontrado')
    return row

def audit(db,user,action,entity,metadata):
    db.add(AuditEvent(user_id=user.id,action=action,entity_type='REPLENISHMENT',entity_id=str(entity),metadata_json=metadata))

def scenario_payload(row):
    return {'id':row.public_id,'name':row.name,'saved':row.saved,'version':row.version,'created_at':row.created_at,
        'captured_at':row.source_snapshot['captured_at'],'source_fingerprint':row.source_fingerprint,
        'filters':row.filters,'temporary_parameters':row.temporary_parameters,'summary':row.summary,
        'article_limit':row.source_snapshot.get('article_limit',5000),'source_articles':len(row.source_snapshot['articles']),'read_only_exit':True,
        'source_notes':['Stock transferible Almeiras = stock físico − comprometido − reserva de consumo; no incluye entradas pendientes.',
            'Ventas: empresa 1. La vista de stock se usa con el alcance indicado, sin campo de empresa.',
            'Ventas del periodo elegido y stock consultado en la extracción; no se reconstruye stock histórico.',
            'El vínculo cabecera/líneas usa número, ejercicio y empresa según el esquema facilitado.']}

class SettingsInput(BaseModel):
    article_limit:int=Field(ge=1,le=HARD_MAX_ARTICLES)

def module_settings(db):
    row=db.get(ModuleSettings,1)
    return {'article_limit':row.article_limit if row else MAX_ARTICLES,'maximum_article_limit':HARD_MAX_ARTICLES}

@router.get('/settings')
def read_settings(db:Session=Depends(get_db)):
    return module_settings(db)

@router.put('/settings')
def save_settings(body:SettingsInput,db:Session=Depends(get_db),user:User=Depends(operator)):
    previous=module_settings(db)
    row=db.get(ModuleSettings,1)
    if row is None:
        row=ModuleSettings(id=1);db.add(row)
    row.article_limit=body.article_limit;row.updated_by=user.id
    audit(db,user,'REPLENISHMENT_SETTINGS_SAVED','1',{'previous':previous,'article_limit':body.article_limit})
    db.commit();return module_settings(db)

@router.get('/options')
def options(db:Session=Depends(get_db)):
    result={'server_date':today().isoformat(),'delegations':[{'code':key,'name':value} for key,value in DELEGATIONS.items()],
        'defaults':Parameters().model_dump(),'precedence':PRECEDENCE,**module_settings(db)}
    for key,model,parent in [('areas',MaterialArea,None),('families',MaterialFamily,'area_id'),
        ('subfamilies',MaterialSubfamily,'family_id'),('types',MaterialProductType,'subfamily_id')]:
        result[key]=[{'id':row.id,'code':row.code,'name':row.name,**({parent:getattr(row,parent)} if parent else {})}
            for row in db.scalars(select(model).order_by(model.name)).all()]
    return result

@router.get('/policies')
def policies(db:Session=Depends(get_db)):
    return [policy_payload(row) for row in db.scalars(select(Policy).order_by(Policy.scope,Policy.scope_key)).all()]

@router.put('/policies')
def save_policy(body:PolicyInput,db:Session=Depends(get_db),user:User=Depends(operator)):
    validate_parameters(body.parameters)
    key=body.scope_key.strip()
    models={'AREA':MaterialArea,'FAMILY':MaterialFamily,'SUBFAMILY':MaterialSubfamily,'TYPE':MaterialProductType}
    if body.scope=='GLOBAL':key='*'
    elif body.scope in models and (not key.isdigit() or not db.get(models[body.scope],int(key))):
        raise HTTPException(422,'Clasificación no encontrada')
    elif body.scope=='DELEGATION' and key not in DELEGATIONS:raise HTTPException(422,'Delegación no admitida')
    elif body.scope=='ARTICLE_DELEGATION' and (len(key.rsplit('|',1))!=2 or key.rsplit('|',1)[1] not in DELEGATIONS or not key.rsplit('|',1)[0]):
        raise HTTPException(422,'Utiliza código de artículo|delegación, por ejemplo 03009|02')
    row=db.scalar(select(Policy).where(Policy.scope==body.scope,Policy.scope_key==key).with_for_update())
    previous=policy_payload(row) if row else None
    if row is None:
        row=Policy(scope=body.scope,scope_key=key,updated_by=user.id);db.add(row)
    row.parameters=body.parameters;row.active=body.active;row.updated_by=user.id
    db.flush();audit(db,user,'REPLENISHMENT_POLICY_SAVED',row.id,{'previous':previous,'new':policy_payload(row)})
    db.commit();return policy_payload(row)

def classified_source(db,filters):
    query=select(Product.sku)
    for key,column in [('area_id',Product.material_area_id),('family_id',Product.material_family_id),
                       ('subfamily_id',Product.material_subfamily_id),('type_id',Product.material_product_type_id)]:
        if getattr(filters,key) is not None:query=query.where(column==getattr(filters,key))
    selected=list(db.scalars(query).all()) if any(getattr(filters,key) is not None for key in ('area_id','family_id','subfamily_id','type_id')) else None
    if filters.skus:selected=filters.skus if selected is None else sorted(set(selected).intersection(filters.skus))
    limit=module_settings(db)['article_limit']
    source=read_replenishment_source(filters.date_from,filters.date_to,selected,limit)
    source['article_limit']=limit
    codes=[row['sku'] for row in source['articles']]
    rows=[]
    for offset in range(0,len(codes),1000):
        rows.extend(db.execute(select(Product.sku,Product.material_area_id,Product.material_family_id,
            Product.material_subfamily_id,Product.material_product_type_id).where(Product.sku.in_(codes[offset:offset+1000]))).all())
    metadata={row[0]:dict(zip(('area_id','family_id','subfamily_id','type_id'),row[1:])) for row in rows}
    names={key:{row.id:row.name for row in db.scalars(select(model)).all()} for key,model in
        [('area',MaterialArea),('family',MaterialFamily),('subfamily',MaterialSubfamily),('type',MaterialProductType)]}
    for article in source['articles']:
        article.update(metadata.get(article['sku'],{}))
        for key in names:article[key]=names[key].get(article.get(key+'_id'))
    return source

@router.post('/simulations',status_code=201)
def run_simulation(body:RunInput,db:Session=Depends(get_db),user:User=Depends(operator)):
    validate_parameters(body.temporary_parameters)
    filters=body.filters.model_dump(mode='json')
    if body.source_id:
        base=scenario_or_404(db,body.source_id)
        if base.filters!=filters:raise HTTPException(422,'Para reutilizar datos conserva los filtros originales o actualiza la extracción')
        source=base.source_snapshot
    else:
        try:source=classified_source(db,body.filters)
        except ValueError as exc:raise HTTPException(422,str(exc)) from exc
        except Exception as exc:
            logger.exception('Error leyendo fuentes de reposición EXIT')
            raise HTTPException(503,'No se pudieron leer las fuentes EXIT indicadas. Revisa el registro de la API y la conexión') from exc
    snapshots=[]  # El cálculo simple usa exclusivamente los parámetros visibles enviados.
    fingerprint=hashlib.sha256(json.dumps(source,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    scenario=Scenario(created_by=user.id,source_snapshot=source,source_fingerprint=fingerprint,filters=filters,
        policies_snapshot=snapshots,temporary_parameters=body.temporary_parameters,summary={})
    db.add(scenario);db.flush()
    results=[]
    if not body.preview_only:
        try:
            context=prepare_context(source,body.filters.delegations,snapshots,body.temporary_parameters)
            results=[calculate_article(article,delegation,context) for article in source['articles'] for delegation in body.filters.delegations]
        except ValueError as exc:raise HTTPException(422,f'Parámetros incompatibles al resolver políticas: {exc}') from exc
        annotate_central(results,source);scenario.summary=summarize(results)
        db.add_all([Result(scenario_id=scenario.id,sku=row['sku'],delegation=row['delegation'],payload=row) for row in results])
    audit(db,user,'REPLENISHMENT_SIMULATED',scenario.public_id,{'preview_only':body.preview_only,'source_fingerprint':fingerprint})
    db.commit();return scenario_payload(scenario)

@router.get('/simulations/{scenario_id}/results')
def results(scenario_id:str,q:str='',alerts_only:bool=False,needed_only:bool=False,page:int=Query(1,ge=1),
        central_only:bool=False,overstock_only:bool=False,consumption:Literal['ALL','WITH','WITHOUT']='ALL',
        page_size:int=Query(50,ge=1,le=100),sort:Literal['sku','quantity','coverage','alerts']='sku',descending:bool=False,db:Session=Depends(get_db)):
    scenario=scenario_or_404(db,scenario_id)
    query=select(Result).where(Result.scenario_id==scenario.id)
    if q:
        query=query.where(or_(func.lower(Result.sku).contains(q.lower(),autoescape=True),
            func.lower(Result.payload['description'].as_string()).contains(q.lower(),autoescape=True)))
    if alerts_only:query=query.where(func.json_array_length(Result.payload['recommendations'])>0)
    if needed_only:query=query.where(Result.payload['final_quantity'].as_float()>0)
    if central_only:query=query.where(Result.payload['central_can_supply'].as_boolean().is_(True))
    if overstock_only:query=query.where(Result.payload['overstock'].as_boolean().is_(True))
    if consumption=='WITHOUT':query=query.where(Result.payload['total_demand'].as_float()<=0)
    if consumption=='WITH':query=query.where(Result.payload['total_demand'].as_float()>0)
    order={'sku':Result.sku,'quantity':Result.payload['final_quantity'].as_float(),
        'coverage':Result.payload['coverage_days'].as_float(),'alerts':func.json_array_length(Result.payload['recommendations'])}[sort]
    total=db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows=db.scalars(query.order_by(order.desc() if descending else order.asc(),Result.sku,Result.delegation)
        .offset((page-1)*page_size).limit(page_size)).all()
    return {'items':[{'id':row.id,**row.payload} for row in rows],'total':total,'page':page,'version':scenario.version}


def article_context(scenario,result):
    source=scenario.source_snapshot
    article=next((row for row in source['articles'] if row['sku']==result.sku),None)
    if not article:raise HTTPException(404,'Artículo ausente en la instantánea')
    context=prepare_context(source,scenario.filters['delegations'],scenario.policies_snapshot,scenario.temporary_parameters)
    return article,context

@router.get('/simulations/{scenario_id}/results/{result_id}')
def detail(scenario_id:str,result_id:int,db:Session=Depends(get_db)):
    scenario=scenario_or_404(db,scenario_id);row=result_or_404(db,scenario,result_id)
    article,context=article_context(scenario,row)
    calculated=calculate_article(article,row.delegation,context,row.payload.get('manual_parameters'),True)
    history=db.scalars(select(Adjustment).where(Adjustment.result_id==row.id).order_by(Adjustment.created_at)).all()
    return {'id':row.id,**row.payload,'daily_sales':calculated['daily_sales'],'scenario_version':scenario.version,
        'adjustments':[{'created_at':event.created_at,'user_id':event.user_id,'reason':event.reason,'changes':event.changes} for event in history]}

@router.post('/simulations/{scenario_id}/results/{result_id}/recalculate')
def recalculate(scenario_id:str,result_id:int,body:RecalculateInput,db:Session=Depends(get_db)):
    validate_parameters(body.parameters)
    scenario=scenario_or_404(db,scenario_id);row=result_or_404(db,scenario,result_id)
    article,context=article_context(scenario,row)
    try:result=calculate_article(article,row.delegation,context,{**row.payload.get('manual_parameters',{}),**body.parameters},True)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    other=[dict(item.payload) for item in db.scalars(select(Result).where(Result.scenario_id==scenario.id,Result.id!=row.id)).all()]
    annotate_central([*other,result],scenario.source_snapshot)
    return result

@router.post('/simulations/{scenario_id}/results/{result_id}/adjustments')
def adjust(scenario_id:str,result_id:int,body:AdjustmentInput,db:Session=Depends(get_db),user:User=Depends(operator)):
    validate_parameters(body.parameters)
    scenario=scenario_or_404(db,scenario_id,True);row=result_or_404(db,scenario,result_id)
    if scenario.version!=body.expected_version:raise HTTPException(409,'Otra persona modificó el escenario. Actualiza los datos')
    article,context=article_context(scenario,row);previous=dict(row.payload)
    patch={**previous.get('manual_parameters',{}),**body.parameters}
    try:updated=calculate_article(article,row.delegation,context,patch)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    updated['manual_parameters']=patch
    if not body.excluded and body.quantity is not None and body.quantity>0 and updated['parameters']['multiple_mode']=='EXIT':
        multiple=updated['effective_multiple']
        if multiple is None:raise HTTPException(422,'No hay un EX_multiplo válido. Corrige EXIT o selecciona otro modo de agrupación')
        if abs(rounded_dispatch(body.quantity,multiple)-body.quantity)>1e-8:
            raise HTTPException(422,f'La cantidad ajustada debe ser múltiplo de {multiple:g}, según EX_multiplo de EXIT')
    updated['adjusted_quantity']=0 if body.excluded else body.quantity
    updated['final_quantity']=updated['recommended_quantity'] if updated['adjusted_quantity'] is None else updated['adjusted_quantity']
    updated['manually_excluded']=body.excluded;updated['calculated_quantity']=previous['calculated_quantity']
    row.payload=updated
    all_rows=db.scalars(select(Result).where(Result.scenario_id==scenario.id)).all()
    payloads=[dict(item.payload) for item in all_rows];annotate_central(payloads,scenario.source_snapshot)
    for item,payload in zip(all_rows,payloads):item.payload=payload
    scenario.summary=summarize(payloads);scenario.version+=1
    db.add(Adjustment(scenario_id=scenario.id,result_id=row.id,user_id=user.id,reason=body.reason,previous=previous,changes=body.model_dump()))
    audit(db,user,'REPLENISHMENT_MANUAL_ADJUSTMENT',scenario.public_id,{'sku':row.sku,'delegation':row.delegation,'reason':body.reason})
    db.commit();return {'scenario':scenario_payload(scenario),'result':{'id':row.id,**row.payload}}

@router.get('/simulations/{scenario_id}/export.xlsx')
def export(scenario_id:str,db:Session=Depends(get_db)):
    scenario=scenario_or_404(db,scenario_id)
    rows=db.scalars(select(Result).where(Result.scenario_id==scenario.id).order_by(Result.sku,Result.delegation)).all()
    book=Workbook();sheet=book.active;sheet.title='Reposición'
    fields=[('sku','Código'),('description','Descripción'),('delegation','Delegación'),('unit_type','Tipo unidad'),('family','Familia'),('target_mode','Objetivo elegido'),
        ('central_stock','Stock Almeiras'),('central_outgoing','Comprometido Almeiras'),('central_incoming','Pendiente recibir Almeiras'),('central_monthly_consumption','Consumo mensual Almeiras'),('central_reserve','Reserva Almeiras'),('central_available','Disponible para despacho Almeiras'),('central_total_requested','Propuesta conjunta'),('central_can_supply','Almeiras cubre propuesta conjunta'),('overstock','Sobrestock'),('excess_stock','Exceso previsto'),('no_consumption','Sin consumo'),('stock','Stock'),('incoming','Pendiente recibir'),('outgoing','Pendiente servir'),('inventory_position','Posición'),('monthly_mean','Consumo mensual medio'),
        ('safety_stock','Seguridad'),('minimum_stock','Mínimo'),('maximum_stock','Stock máximo'),('expected_cycle_consumption','Consumo hasta próxima reposición'),('replenishment_point','Punto de reposición'),('target_stock','Objetivo aplicado'),('calculated_quantity','Cantidad calculada'),
        ('exit_multiple','Múltiplo EXIT'),('effective_multiple','Múltiplo aplicado'),('quantity_before_rounding','Cantidad antes de agrupar'),('recommended_quantity','Cantidad recomendada'),('adjusted_quantity','Ajuste manual'),('final_quantity','Cantidad final'),('method','Método'),('confidence','Confianza')]
    sheet.append([label for _,label in fields]+['Reglas aplicadas','Recomendaciones'])
    for result in rows:
        row={**result.payload,'monthly_mean':result.payload['daily_mean']*30};values=[row.get(key) for key,_ in fields]+[' → '.join(row['applied_rules']),'; '.join(item['reason'] for item in row['recommendations'])]
        sheet.append(values)
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value,str):cell.data_type='s'
    sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
    metadata=book.create_sheet('Contexto');metadata.append(['Dato','Valor'])
    for key,value in [('Cálculo',scenario.public_id),('Corte',scenario.source_snapshot['captured_at']),('Huella de datos',scenario.source_fingerprint),
        ('Filtros',json.dumps(scenario.filters,ensure_ascii=False)),('Parámetros temporales',json.dumps(scenario.temporary_parameters,ensure_ascii=False)),
        ('Políticas',json.dumps(scenario.policies_snapshot,ensure_ascii=False)),('Modo','Solo cálculo; no genera pedidos. Almeiras protegido por su consumo y reserva.')]:
        metadata.append([key,value]);metadata.cell(metadata.max_row,2).data_type='s'
    buffer=io.BytesIO();book.save(buffer)
    return Response(buffer.getvalue(),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="reposicion.xlsx"'})
