"""Versiones de flujo; el bloqueo de IncidentType serializa cambios y registro de casos."""
import json
from copy import deepcopy
from sqlalchemy import select,func
from sqlalchemy.orm import Session,load_only
from .models import IncidentType,LogisticsIncident,IncidentFlowVersion as Version,IncidentFlowChange as Change
from .incident_flow import normalize
from .incident_schemas import TypeConfiguration


def configuration(value):
    return TypeConfiguration.model_validate(normalize(value)).model_dump()


def structure(value):
    return {key:item for key,item in configuration(value).items() if key!='name'}


def record(db,row,number,action,user=None,**detail):
    db.add(Change(type_code=row.code,flow_version=number,action=action,actor_id=user.id if user else None,detail=detail))


def ensure(db,row):
    if row.configuration.get('_flow_version'):
        return int(row.configuration['_flow_version'])
    # Older releases stored complete snapshots on each case, but no explicit version.
    # Reconstruct distinct inherited definitions without changing their execution rules.
    versions={};number=0;last_key=None
    query=select(LogisticsIncident).where(LogisticsIncident.type_code==row.code).options(load_only(LogisticsIncident.id,LogisticsIncident.workflow,LogisticsIncident.created_at)).order_by(LogisticsIncident.created_at,LogisticsIncident.id)
    for case in db.scalars(query):
        cfg=configuration(case.workflow);key=json.dumps(structure(cfg),sort_keys=True)
        if key not in versions:
            number+=1;versions[key]=number
            db.add(Version(type_code=row.code,number=number,configuration=cfg,legacy=True,note='Reconstruida de una incidencia anterior; autor de configuración no registrado.',created_at=case.created_at))
        case.workflow={**case.workflow,'_flow_version':versions[key]}
        last_key=key
    cfg=configuration(row.configuration);key=json.dumps(structure(cfg),sort_keys=True)
    if not versions or key!=last_key:
        number+=1
        db.add(Version(type_code=row.code,number=number,configuration=cfg,legacy=True,note='Configuración vigente anterior al control de versiones.'))
    else:number=versions[key]
    row.configuration={**row.configuration,'_flow_version':number}
    record(db,row,number,'IMPORTED',versions=number)
    db.flush()
    return number


def used(db,code,number=None):
    query=select(func.count()).select_from(LogisticsIncident).where(LogisticsIncident.type_code==code)
    if number is not None:query=query.where(LogisticsIncident.workflow['_flow_version'].as_integer()==number)
    return db.scalar(query) or 0


def metadata(db,row):
    number=int(row.configuration.get('_flow_version',1))
    return {'flow_version':number,'in_use':bool(used(db,row.code,number)),'has_incidents':bool(used(db,row.code)),
        'version_count':db.scalar(select(func.count()).select_from(Version).where(Version.type_code==row.code)) or 1}


def migrate(engine):
    # Called after create_all, before serving requests. Idempotent on restart.
    with Session(engine) as db:
        for row in db.scalars(select(IncidentType).with_for_update()):ensure(db,row)
        db.commit()
