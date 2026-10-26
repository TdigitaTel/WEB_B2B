"""Motor puro de simulación. No conoce conexiones ni modifica políticas."""
from collections import defaultdict
from decimal import Decimal, ROUND_CEILING, InvalidOperation
from datetime import date, timedelta
from math import ceil, sqrt
from statistics import NormalDist, mean, median, pstdev
from typing import Literal
from pydantic import BaseModel, Field, model_validator

class Parameters(BaseModel):
    review_days: int = Field(7,ge=1,le=90)
    lead_days: int = Field(1,ge=0,le=180)
    service_level: float = Field(95,ge=50,le=99.9)
    history_days: int | None = Field(None,ge=1,le=1095)
    max_coverage_days: int | None = Field(None,ge=1,le=1095)
    minimum_quantity: float = Field(0,ge=0,le=1e9)
    multiple: float = Field(1,gt=0,le=1e6)
    multiple_mode: Literal['NONE','MANUAL','EXIT'] = 'MANUAL'
    manual_min: float | None = Field(None,ge=0,le=1e9)
    manual_max: float | None = Field(None,ge=0,le=1e9)
    enabled: bool = True
    no_sales_policy: Literal['REVIEW','COMPARABLE','NO_REPLENISH'] = 'REVIEW'
    new_policy: Literal['REVIEW','COMPARABLE','NO_REPLENISH'] = 'REVIEW'
    @model_validator(mode='after')
    def valid_range(self):
        if self.manual_min is not None and self.manual_max is not None and self.manual_min>self.manual_max:
            raise ValueError('El mínimo manual no puede superar el máximo')
        return self
    model_config={'extra':'forbid','allow_inf_nan':False}

PRECEDENCE=['GLOBAL','AREA','FAMILY','SUBFAMILY','TYPE','DELEGATION','ARTICLE_DELEGATION']
FIELDS={'AREA':'area_id','FAMILY':'family_id','SUBFAMILY':'subfamily_id','TYPE':'type_id'}

def resolve_parameters(article,delegation,policies,temporary=None):
    result=Parameters().model_dump();applied=[];origins={key:'Predeterminado' for key in result}
    for scope in PRECEDENCE:
        key='*' if scope=='GLOBAL' else delegation if scope=='DELEGATION' else f"{article['sku']}|{delegation}" if scope=='ARTICLE_DELEGATION' else str(article.get(FIELDS[scope]) or '')
        for policy in policies:
            if policy.get('active',True) and policy['scope']==scope and policy['scope_key']==key:
                result.update(policy['parameters']);label=f'{scope}:{key}'
                applied.append(label);origins.update({name:label for name in policy['parameters']})
    if temporary:
        result.update(temporary);applied.append('Ajuste temporal');origins.update({name:'Ajuste temporal' for name in temporary})
    return Parameters.model_validate(result).model_dump(),applied,origins

def demand_statistics(article,delegation,source,parameters,sales_index,include_daily=False):
    end=date.fromisoformat(source['end']);start=date.fromisoformat(source['start'])
    if parameters['history_days']:start=max(start,end-timedelta(days=parameters['history_days']-1))
    created=None
    try:created=date.fromisoformat((article.get('created_at') or '')[:10])
    except ValueError:pass
    if created and start<created<=end:start=created
    days=(end-start).days+1
    daily=[];values=[];gross=returned=0;last_sale=None;anomalous=0
    for offset in range(days):
        day=(start+timedelta(days=offset)).isoformat();sold,back=sales_index.get((article['sku'],delegation,day),(0,0))
        gross+=sold;returned+=back;anomalous+=int(back>sold)
        if sold>0:last_sale=day
        values.append(max(0,sold-back))
        if include_daily:daily.append({'day':day,'sold':sold,'returned':back,'demand':values[-1]})
    average=mean(values) if values else 0;deviation=pstdev(values) if values else 0
    sales_days=sum(value>0 for value in values)
    adi=days/sales_days if sales_days else None
    irregular=bool(sales_days and (adi>1.32 or (average>0 and deviation/average>1)))
    return {'days':days,'start':start.isoformat(),'end':end.isoformat(),'daily':daily,'demand_values':values,'gross_sales':gross,
            'returns':returned,'total_demand':sum(values),'daily_mean':average,'daily_std':deviation,
            'sales_days':sales_days,'last_sale':last_sale,'irregular':irregular,'anomalous_return_days':anomalous,
            'new_article':bool(created and (end-created).days<30),'created_in_future':bool(created and created>end)}

def prepare_context(source,delegations,policies,temporary=None):
    sales_index={}
    for row in source['sales']:
        key=(row['sku'],row['delegation'],row['day']);old=sales_index.get(key,(0,0))
        sales_index[key]=(old[0]+row['sold'],old[1]+row['returned'])
    stats={};resolved={};comparables=defaultdict(list)
    for article in source['articles']:
        for delegation in delegations:
            key=(article['sku'],delegation)
            parameters,rules,origins=resolve_parameters(article,delegation,policies,temporary)
            resolved[key]=(parameters,rules,origins)
            value=demand_statistics(article,delegation,source,parameters,sales_index);stats[key]=value
            if value['sales_days']>=5 and not value['new_article'] and value['daily_mean']>0:
                for level in ('type_id','subfamily_id','family_id'):
                    if article.get(level):comparables[(delegation,level,article[level],article.get('unit_type',''))].append((article['sku'],value['daily_mean']))
    stocks={(row['sku'],row['delegation']):row for row in source['stocks']}
    return {'source':source,'stats':stats,'resolved':resolved,'comparables':comparables,'stocks':stocks,'sales_index':sales_index}

def recommendation(code,reason,evidence,parameter=None,current=None,suggested=None,effect=None,confidence='BAJA'):
    return {'code':code,'reason':reason,'evidence':evidence,'parameter':parameter,'current_value':current,
            'suggested_value':suggested,'estimated_effect':effect,'confidence':confidence}

def effective_dispatch_multiple(article, parameters):
    mode=parameters['multiple_mode']
    if mode=='NONE':return None
    if mode=='MANUAL':return parameters['multiple']
    value=article.get('exit_multiple')
    try:
        number=Decimal(str(value))
        return float(number) if number.is_finite() and number>0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None

def rounded_dispatch(quantity, multiple):
    if quantity<=0 or multiple is None:return quantity
    value=Decimal(str(quantity));step=Decimal(str(multiple))
    return float((value/step).to_integral_value(rounding=ROUND_CEILING)*step)

def calculate_article(article,delegation,context,override=None,include_daily=False):
    key=(article['sku'],delegation);parameters,rules,origins=context['resolved'][key]
    parameters=dict(parameters)
    if override:
        parameters=Parameters.model_validate({**parameters,**override}).model_dump();rules=[*rules,'Ajuste del artículo'];origins={**origins,**{key:'Ajuste del artículo' for key in override}}
    stats=demand_statistics(article,delegation,context['source'],parameters,context['sales_index'],include_daily) if override or include_daily else context['stats'][key]
    avg,std=stats['daily_mean'],stats['daily_std'];horizon=parameters['review_days']+parameters['lead_days']
    z=NormalDist().inv_cdf(parameters['service_level']/100)
    safety=ceil(z*std*sqrt(horizon));minimum=ceil(avg*parameters['lead_days']+safety);maximum=ceil(avg*horizon+safety)
    method='REVISION_PERIODICA';confidence='ALTA' if stats['sales_days']>=30 and not stats['irregular'] else 'MEDIA'
    recs=[];comparable=None
    sparse=stats['sales_days']<5 or stats['new_article']
    if sparse:
        safety=minimum=maximum=0;confidence='BAJA';method='REVISION_MANUAL'
        policy=parameters['new_policy'] if stats['new_article'] else parameters['no_sales_policy']
        if policy!='NO_REPLENISH':
            for level in ('type_id','subfamily_id','family_id'):
                candidates=[value for sku,value in context['comparables'].get((delegation,level,article.get(level),article.get('unit_type','')),[]) if sku!=article['sku']]
                if len(candidates)>=3:
                    estimate=median(candidates);minimum=maximum=ceil(estimate*max(1,parameters['lead_days']))
                    comparable={'level':level,'count':len(candidates),'median_daily_demand':estimate,'indicative_minimum':minimum}
                    method='MINIMO_ORIENTATIVO_COMPARABLES';break
        recs.append(recommendation('HISTORICO_INSUFICIENTE','Histórico insuficiente: revisar la propuesta orientativa; no representa ventas reales del artículo.',
            {'days':stats['days'],'sales_days':stats['sales_days'],'comparables':comparable},'new_policy' if stats['new_article'] else 'no_sales_policy',policy))
    elif stats['irregular']:
        # Percentil empírico de demanda en ventanas completas del horizonte.
        values=stats['demand_values'];sums=[]
        if len(values)>=horizon:
            current=sum(values[:horizon]);sums=[current]
            for index in range(horizon,len(values)):
                current+=values[index]-values[index-horizon];sums.append(current)
        if len(sums)>=5:
            sums.sort();maximum=ceil(sums[min(len(sums)-1,ceil(len(sums)*parameters['service_level']/100)-1)])
            safety=max(0,ceil(maximum-avg*horizon));minimum=min(maximum,ceil(avg*parameters['lead_days']+safety))
            method='PERCENTIL_EMPIRICO_INTERMITENTE';confidence='BAJA'
        else:
            safety=minimum=maximum=0;method='REVISION_MANUAL';confidence='BAJA'
    raw_maximum=maximum
    stock=context['stocks'].get(key);position=stock['stock']+stock['incoming']-stock['outgoing'] if stock else None
    calculated=max(0,ceil(maximum-position)) if position is not None else 0
    if parameters['max_coverage_days'] and avg>0:
        maximum=min(maximum,ceil(avg*parameters['max_coverage_days']));minimum=min(minimum,maximum)
    if parameters['manual_min'] is not None:minimum=parameters['manual_min']
    if parameters['manual_max'] is not None:maximum=parameters['manual_max']
    maximum=max(minimum,maximum)
    if sparse and (parameters['manual_min'] is not None or parameters['manual_max'] is not None):method='LIMITES_MANUALES';confidence='BAJA'
    quantity=max(0,maximum-position) if position is not None else 0
    dispatch_multiple=effective_dispatch_multiple(article,parameters)
    before_rounding=max(quantity,parameters['minimum_quantity']) if quantity>0 else 0
    quantity=rounded_dispatch(before_rounding,dispatch_multiple)
    if parameters['multiple_mode']=='EXIT' and dispatch_multiple is None:
        quantity=0
        recs.append(recommendation('MULTIPLO_EXIT_INVALIDO','EX_multiplo no contiene un múltiplo positivo válido. La propuesta queda a cero hasta revisar el formato de despacho.',
            {'exit_multiple':article.get('exit_multiple'),'quantity_before_rounding':before_rounding},'multiple_mode','EXIT'))
    if not parameters['enabled'] or stats['created_in_future'] or (sparse and (parameters['new_policy'] if stats['new_article'] else parameters['no_sales_policy'])=='NO_REPLENISH'):quantity=0
    if quantity>0 and position is not None and position+quantity>maximum+1e-8:
        recs.append(recommendation('REDONDEO_SOBRE_MAXIMO','El múltiplo o la cantidad mínima elevan el inventario por encima del máximo objetivo.',
            {'quantity':quantity,'position_after':position+quantity,'maximum':maximum,'effective_multiple':dispatch_multiple},'multiple_mode',parameters['multiple_mode']))
    coverage=position/avg if position is not None and avg>0 else None
    if coverage is not None and coverage>max(90,3*horizon):
        recs.append(recommendation('EXCESO_STOCK',f'El inventario equivale a {coverage:.1f} días de demanda observada.',
            {'coverage_days':coverage,'horizon':horizon},'manual_max',parameters['manual_max'],raw_maximum,
            {'target_stock_delta':raw_maximum-maximum},confidence))
    if position is not None and avg>0 and position<avg*horizon:
        recs.append(recommendation('STOCK_INSUFICIENTE','La posición de inventario no cubre el horizonte de reposición.',
            {'position':position,'expected_horizon_demand':avg*horizon},'review_days',parameters['review_days'],confidence=confidence))
    if stats['irregular']:
        recs.append(recommendation('DEMANDA_IRREGULAR','Ventas intermitentes: se utiliza un percentil empírico o se requiere revisión, no el modelo normal de forma ciega.',
            {'sales_days':stats['sales_days'],'observed_days':stats['days'],'method':method}))
    if stats['gross_sales']==0:
        recs.append(recommendation('SIN_MOVIMIENTO',f"No registra ventas en los {stats['days']} días observados; revisar mínimo de exposición.",
            {'from':stats['start'],'to':stats['end']},'no_sales_policy',parameters['no_sales_policy']))
    if stats['new_article'] or stats['created_in_future']:
        recs.append(recommendation('ARTICULO_NUEVO','Artículo nuevo o fecha de alta futura: estimación de baja confianza.',{'created_at':article.get('created_at'),'comparables':comparable},'new_policy',parameters['new_policy']))
    if stats['returns']>stats['gross_sales'] or stats['anomalous_return_days']:
        recs.append(recommendation('DEVOLUCIONES_ANOMALAS','Las devoluciones superan ventas en alguno de los días; la demanda diaria se limita a cero, conservando ambas cantidades.',
            {'sales':stats['gross_sales'],'returns':stats['returns'],'days':stats['anomalous_return_days']}))
    if stock is None or (stock and (stock['stock']<0 or stock['incoming']<0 or stock['outgoing']<0)):
        recs.append(recommendation('DATOS_STOCK','Falta stock en la vista o hay existencias/pendientes negativos. Verificar antes de reponer.',{'stock':stock}))
    if not article.get('area_id'):
        recs.append(recommendation('SIN_CLASIFICACION','El artículo no tiene área comercial B2B.',{'sku':article['sku']}))
    if avg>0 and (safety>3*avg*horizon or maximum/avg>max(90,3*horizon)):
        recs.append(recommendation('PARAMETROS_REVISAR','La seguridad o el máximo generan una cobertura elevada respecto a la demanda.',
            {'safety':safety,'horizon_demand':avg*horizon,'maximum_coverage':maximum/avg},'max_coverage_days',parameters['max_coverage_days']))
    if quantity>max(1000,avg*horizon*10) or (stats['gross_sales']==0 and quantity>0) or (avg>0 and quantity==0 and position is not None and position<minimum):
        recs.append(recommendation('PROPUESTA_REVISAR','Revisar una cantidad elevada, una reposición sin ventas o una reposición cero bajo el mínimo.',
            {'quantity':quantity,'position':position,'minimum':minimum,'horizon_demand':avg*horizon}))
    result={**article,'delegation':delegation,'stock':stock['stock'] if stock else None,'incoming':stock['incoming'] if stock else None,
        'outgoing':stock['outgoing'] if stock else None,'inventory_position':position,'gross_sales':stats['gross_sales'],
        'returns':stats['returns'],'total_demand':stats['total_demand'],'daily_mean':avg,'daily_std':std,'sales_days':stats['sales_days'],
        'last_sale':stats['last_sale'],'observed_days':stats['days'],'irregular':stats['irregular'],'new_article':stats['new_article'],
        'safety_stock':safety,'minimum_stock':minimum,'maximum_stock':maximum,'calculated_quantity':calculated,
        'recommended_quantity':round(quantity,6),'adjusted_quantity':None,'final_quantity':round(quantity,6),'coverage_days':coverage,
        'confidence':confidence,'method':method,'comparables':comparable,'parameters':parameters,'applied_rules':rules,
        'parameter_origins':origins,'recommendations':recs,'manual_parameters':{},'effective_multiple':dispatch_multiple,'quantity_before_rounding':before_rounding,
        'calculation':{'horizon':horizon,'z':z,'formula':'S = ceil(media × horizonte + seguridad); Q = max(0, S − posición)',
            'safety_formula':'ceil(Z × desviación diaria × sqrt(horizonte))' if method=='REVISION_PERIODICA' else 'Modelo alternativo explicado en método y recomendaciones',
            'dispatch_days':parameters['review_days'],'lead_days':parameters['lead_days'],'raw_maximum':raw_maximum,'window_start':stats['start'],'window_end':stats['end']}}
    if include_daily:result['daily_sales']=stats['daily']
    return result

def annotate_central(results,source):
    central={row['sku']:row for row in source['stocks'] if row['delegation']=='00'}
    totals=defaultdict(float)
    for row in results:totals[row['sku']]+=row['final_quantity']
    for row in results:
        row['recommendations']=[r for r in row['recommendations'] if r['code'] not in ('CENTRAL_INSUFICIENTE','CENTRAL_SIN_DATOS')]
        stock=central.get(row['sku']);available=stock['stock']+stock['incoming']-stock['outgoing'] if stock else None
        row['central_position']=available;row['central_total_requested']=totals[row['sku']]
        if totals[row['sku']]>0 and (available is None or totals[row['sku']]>max(0,available)):
            row['recommendations'].append(recommendation('CENTRAL_SIN_DATOS' if available is None else 'CENTRAL_INSUFICIENTE',
                'La propuesta conjunta requiere revisar existencias consolidadas de Almeiras; no se supone stock transferible.',
                {'total_requested':totals[row['sku']],'central_position':available}))

def summarize(results):
    coverage=[row['maximum_stock']/row['daily_mean'] for row in results if row['daily_mean']>0]
    return {'articles_analyzed':len({row['sku'] for row in results}),'article_delegations':len(results),
        'to_replenish':sum(row['final_quantity']>0 for row in results),'units_proposed':sum(row['final_quantity'] for row in results),
        'without_movement':sum(row['gross_sales']==0 for row in results),'irregular':sum(row['irregular'] for row in results),
        'alerts':sum(len(row['recommendations']) for row in results),'target_stock':sum(row['maximum_stock'] for row in results),
        'average_coverage_days':mean(coverage) if coverage else None}
