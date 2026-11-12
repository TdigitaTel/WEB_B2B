"""Current delegation calculations and read-only redistribution proposals."""
from collections import defaultdict
import hashlib
import json
from decimal import Decimal, ROUND_FLOOR
from math import lcm
from fastapi import HTTPException
from sqlalchemy import select, delete, or_, text
from .models import (ReplenishmentDelegationCalculation as Current, ReplenishmentScenario as Scenario,
    ReplenishmentResult as Result, ReplenishmentJob as Job, ReplenishmentBatch as Batch,
    ReplenishmentAdjustment as Adjustment)
from .replenishment_source import DELEGATIONS


def lock_registry(db):
    if db.get_bind().dialect.name=='postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(724130292)'))


def current_calculations(db):
    """Adopt already published calculations on upgrade, without reading EXIT."""
    lock_registry(db)
    db.execute(delete(Current).where(Current.scenario_id.not_in(select(Scenario.id))))
    registered={row.delegation:row for row in db.scalars(select(Current)).all()}
    missing=set(DELEGATIONS)-registered.keys()
    if missing:
        candidates=db.execute(select(Scenario.id,Scenario.filters).outerjoin(Job,Job.scenario_id==Scenario.id)
            .where(or_(Job.status=='COMPLETED', (Job.id.is_(None) & select(Result.id).where(Result.scenario_id==Scenario.id).exists())))
            .order_by(Scenario.id.desc()))
        for sid,filters in candidates:
            for code in set(filters['delegations']) & missing:
                row=Current(delegation=code,scenario_id=sid);db.add(row);registered[code]=row;missing.remove(code)
            if not missing:break
        db.flush()
    return registered


def publish_calculations(db,scenario):
    """Replace only successful publications; retain shared sources still in use."""
    current=current_calculations(db);old=set()
    for code in scenario.filters['delegations']:
        row=current.get(code)
        if row:
            if row.scenario_id!=scenario.id:old.add((row.scenario_id,code))
            row.scenario_id=scenario.id
        else:db.add(Current(delegation=code,scenario_id=scenario.id))
    scenario.saved=True;scenario.name='Cálculo de reposición'
    db.flush()
    for sid,code in old:
        ids=select(Result.id).where(Result.scenario_id==sid,Result.delegation==code)
        db.execute(delete(Adjustment).where(Adjustment.result_id.in_(ids)))
        db.execute(delete(Result).where(Result.scenario_id==sid,Result.delegation==code))
    for sid in {sid for sid,_ in old}:
        if db.scalar(select(Current.delegation).where(Current.scenario_id==sid).limit(1)):continue
        jobs=db.scalars(select(Job).where(Job.scenario_id==sid)).all()
        for job in jobs:
            db.execute(delete(Batch).where(Batch.job_id==job.id))
            job.scenario_id=None;job.status='REPLACED';job.phase='Sustituido por un cálculo más reciente'
        db.flush()
        db.execute(delete(Adjustment).where(Adjustment.scenario_id==sid))
        db.execute(delete(Result).where(Result.scenario_id==sid))
        db.execute(delete(Scenario).where(Scenario.id==sid))


def calculation_list(db):
    from .replenishment import scenario_payload, ResultFilters, filtered_results, result_summary
    current=current_calculations(db);items=[]
    for code in DELEGATIONS:
        if code not in current:continue
        scenario=db.get(Scenario,current[code].scenario_id)
        job=db.scalar(select(Job).where(Job.scenario_id==scenario.id))
        payload=scenario_payload(scenario)
        payload.update(delegation=code,delegation_name=DELEGATIONS[code],
            calculated_at=job.finished_at if job else scenario.created_at,
            filters={**scenario.filters,'delegations':[code]},
            summary=result_summary(db,filtered_results(scenario.id,ResultFilters(delegation=code))))
        items.append(payload)
    return {'items':items,'missing_delegations':[{'code':code,'name':DELEGATIONS[code]} for code in DELEGATIONS if code not in current]}


def number(value):
    try:
        result=Decimal(str(value))
        return result if result.is_finite() else None
    except Exception:return None


def floor_step(value,step):return (value/step).to_integral_value(rounding=ROUND_FLOOR)*step


def common_step(*rows):
    steps=[number(row['effective_multiple'] if row.get('effective_multiple') is not None else 1) for row in rows]
    if any(step is None or step<=0 for step in steps):return None
    places=max(max(0,-step.as_tuple().exponent) for step in steps)
    factor=10**places
    return Decimal(lcm(*(int(step*factor) for step in steps)))/factor


def redistribution(rows):
    """Never allocate future incoming stock or the same surplus twice."""
    groups=defaultdict(list)
    for row in rows:groups[row['sku']].append(row)
    moves=[];unmet=[];warnings=[]
    for sku,group in sorted(groups.items()):
        if {r['delegation'] for r in group}!=set(DELEGATIONS):
            warnings.append({'sku':sku,'reason':'Falta el cálculo de este material en alguna delegación.'});continue
        if len({r.get('unit_type','') for r in group})!=1:
            warnings.append({'sku':sku,'reason':'Las unidades del material no coinciden entre delegaciones.'});continue
        if any(row.get('statistic_available') is False for row in group):
            warnings.append({'sku':sku,'reason':'No hay moda positiva repetida en alguna delegación; material excluido con este criterio.'});continue
        fields=('stock','incoming','outgoing','maximum_stock','inventory_position','final_quantity')
        if any(number(r.get(key)) is None or (key in ('stock','incoming','outgoing','maximum_stock','final_quantity') and number(r[key])<0) for r in group for key in fields):
            warnings.append({'sku':sku,'reason':'Stock, pendientes u objetivos ausentes o negativos; revisar antes de mover.'});continue
        donors=[];needs=[]
        for row in group:
            # Leave the maximum stock physically in the donor, plus commitments;
            # incoming orders are deliberately excluded from dispatchable surplus.
            available=max(Decimal(0),number(row['stock'])-number(row['outgoing'])-number(row['maximum_stock']))
            step=common_step(row)
            if step is None:
                warnings.append({'sku':sku,'reason':'Múltiplo de despacho no válido.'});donors=[];needs=[];break
            available=floor_step(available,step)
            need=max(Decimal(0),number(row['final_quantity']))
            if available>0:donors.append({'row':row,'left':available,'initial':available})
            elif need>0:needs.append({'row':row,'left':need})
        # Stockouts first, then lowest coverage, then delegation code for reproducibility.
        needs.sort(key=lambda n:(number(n['row']['inventory_position'])>0,
            number(n['row']['inventory_position'])/number(n['row']['daily_mean']) if number(n['row'].get('daily_mean')) and number(n['row']['daily_mean'])>0 else Decimal('Infinity'),n['row']['delegation']))
        donors.sort(key=lambda d:(-d['left'],d['row']['delegation']))
        def movement(d,destination,quantity,kind):
            row=d['row'];d['left']-=quantity
            moves.append({'sku':sku,'description':row['description'],'unit_type':row.get('unit_type',''),
                'from_delegation':row['delegation'],'to_delegation':destination,'quantity':float(quantity),
                'kind':kind,'origin_maximum_stock':row['maximum_stock'],'origin_transferable_surplus':float(d['initial'])})
        for need in needs:
            for donor in donors:
                if need['left']<=0:break
                step=common_step(donor['row'],need['row'])
                qty=floor_step(min(donor['left'],need['left']),step)
                if qty>0:
                    movement(donor,need['row']['delegation'],qty,'TRANSFER');need['left']-=qty
        for donor in donors:
            if donor['left']>0:movement(donor,'00',donor['left'],'RETURN_CENTRAL')
        for need in needs:
            if need['left']>0:unmet.append({'sku':sku,'delegation':need['row']['delegation'],'quantity':float(need['left']),'unit_type':need['row'].get('unit_type','')})
    return {'movements':moves,'unmet_needs':unmet,'material_warnings':warnings,
        'summary':{'materials':len({m['sku'] for m in moves}),'transfers':sum(m['kind']=='TRANSFER' for m in moves),
                   'returns_to_central':sum(m['kind']=='RETURN_CENTRAL' for m in moves),'unmet_needs':len(unmet),'excluded_materials':len(warnings)}}


def rebased_planning_rows(db,scenario,delegation,basis):
    """Recalculate from immutable saved sources, not live EXIT. Bound memory per source batch."""
    from .replenishment_engine import prepare_context,calculate_article
    batch_numbers=list(db.scalars(select(Result.payload['source_batch'].as_integer()).where(
        Result.scenario_id==scenario.id,Result.delegation==delegation).distinct()))
    output=[]
    for number in batch_numbers:
        query=select(Result).where(Result.scenario_id==scenario.id,Result.delegation==delegation)
        if number is None:query=query.where(Result.payload['source_batch'].as_integer().is_(None))
        else:query=query.where(Result.payload['source_batch'].as_integer()==number)
        source=(db.scalar(select(Batch.source).join(Job,Job.id==Batch.job_id).where(Job.scenario_id==scenario.id,Batch.number==number))
                if scenario.source_snapshot.get('batched') else scenario.source_snapshot)
        if not source:raise HTTPException(409,'Falta la instantánea del histórico. Recalcula la delegación antes de usar otro criterio.')
        articles={article['sku']:article for article in source['articles']}
        params={**scenario.temporary_parameters,'consumption_basis':basis}
        context=prepare_context(source,[delegation],scenario.policies_snapshot,params)
        for stored in db.scalars(query):
            old=stored.payload
            if stored.sku not in articles:raise HTTPException(409,'Falta un material en la instantánea. Recalcula la delegación.')
            row=calculate_article(articles[stored.sku],delegation,context,{**old.get('manual_parameters',{}),'consumption_basis':basis})
            if old.get('adjusted_quantity') is not None:row['final_quantity']=old['adjusted_quantity']
            if old.get('manually_excluded'):row['final_quantity']=0
            output.append({key:row.get(key) for key in ('sku','delegation','description','unit_type','stock','incoming','outgoing','maximum_stock','inventory_position','final_quantity','effective_multiple','statistic_available')}|
                          {'daily_mean':row['daily_reference']})
    return output


def calculate_redistribution(db,consumption_basis='MEAN'):
    current=current_calculations(db)
    missing=[{'code':d,'name':name} for d,name in DELEGATIONS.items() if d not in current]
    if missing:raise HTTPException(409,{'message':'Faltan cálculos guardados. Calcula todas las delegaciones antes de redistribuir.','missing_delegations':missing})
    # Lock snapshots as well as the registry: manual result adjustments serialize with this proposal.
    scenarios={s.id:s for s in db.scalars(select(Scenario).where(Scenario.id.in_({r.scenario_id for r in current.values()})).order_by(Scenario.id).with_for_update()).all()}
    rows=[];calculations=[];ranges=set()
    for code,pointer in sorted(current.items()):
        scenario=scenarios[pointer.scenario_id]
        # Read only the planning fields, not monthly history/recommendations for
        # tens of thousands of materials. The source snapshots remain untouched.
        columns=[Result.sku,Result.delegation]
        columns += [Result.payload[key].as_string().label(key) for key in ('description','unit_type')]
        columns += [Result.payload[key].as_float().label(key) for key in ('stock','incoming','outgoing','maximum_stock','inventory_position','final_quantity','daily_mean','effective_multiple')]
        columns += [Result.payload['statistic_available'].as_boolean().label('statistic_available')]
        if consumption_basis!='MEAN' or scenario.temporary_parameters.get('consumption_basis','MEAN')!='MEAN':
            rows.extend(rebased_planning_rows(db,scenario,code,consumption_basis))
        else:
            rows.extend(dict(row) for row in db.execute(select(*columns).where(Result.scenario_id==scenario.id,Result.delegation==code)).mappings())
        ranges.add((scenario.filters['date_from'],scenario.filters['date_to']))
        calculations.append({'delegation':code,'name':DELEGATIONS[code],'scenario_id':scenario.public_id,
            'captured_at':scenario.source_snapshot['captured_at'],'date_from':scenario.filters['date_from'],'date_to':scenario.filters['date_to']})
    result=redistribution(rows)
    proposal={**result,'calculations':calculations,'warnings':(['Los cálculos utilizan periodos de ventas diferentes. Revisa las fechas antes de aplicar la propuesta.'] if len(ranges)>1 else []),
        'read_only_exit':True,'consumption_basis':consumption_basis,'consumption_basis_label':{'MEAN':'Media','MEDIAN':'Mediana','MODE':'Moda'}[consumption_basis]}
    proposal['fingerprint']=hashlib.sha256(json.dumps(proposal,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    return proposal
