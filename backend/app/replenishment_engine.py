"""Motor puro de simulación. No conoce conexiones ni modifica políticas."""
from collections import Counter, defaultdict
from calendar import monthrange
from decimal import Decimal, ROUND_CEILING, InvalidOperation
from datetime import date, timedelta
from math import ceil, sqrt
from statistics import NormalDist, mean, median, pstdev
from typing import Literal
from pydantic import BaseModel, Field, model_validator

ConsumptionBasis=Literal['MEAN','MEDIAN','MODE']
BASIS_LABELS={'MEAN':'Media','MEDIAN':'Mediana','MODE':'Moda'}

class Parameters(BaseModel):
    consumption_basis: ConsumptionBasis = 'MEAN'
    target_mode: Literal['POINT','MAXIMUM'] = 'POINT'
    maximum_days: int | None = Field(None,ge=1,le=1095)
    central_reserve_days: int = Field(7,ge=1,le=365)
    exclude_no_consumption: bool = False
    # Legacy snapshots may contain this key; it no longer influences calculation.
    minimum_monthly_consumption: float = Field(0,ge=0,le=1e9)
    simple_formula: bool = False
    review_days: int = Field(7,ge=1,le=90)
    lead_days: int = Field(1,ge=0,le=180)
    use_safety_stock: bool = True
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
        if self.maximum_days is not None and self.maximum_days<self.review_days:
            raise ValueError('Los días de stock máximo no pueden ser menores que los días hasta la próxima reposición')
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

def exceptionality_analysis(values,start,outliers):
    days=len(values);total=sum(values)
    events=[{'day':(start+timedelta(days=i)).isoformat(),'quantity':value} for i,value in enumerate(values) if value>0]
    largest=sorted(events,key=lambda row:(-row['quantity'],row['day']))[:3]
    positive=len(events);frequency=positive/days*100 if days else 0
    share=sum(row['quantity'] for row in largest)/total*100 if total else 0
    reasons=[]
    if positive and share>=80:reasons.append('CONCENTRATION')
    if positive and days>=30 and frequency<=10:reasons.append('LOW_FREQUENCY')
    if outliers:reasons.append('OUTLIERS')
    if positive<8 and positive:reasons.append('FEW_ACTIVE_DAYS')
    if days<30 and positive:reasons.append('SHORT_PERIOD')
    level=('NO_CONSUMPTION' if not positive else 'LIMITED_HISTORY' if days<30 else
           'HIGH' if 'CONCENTRATION' in reasons or 'OUTLIERS' in reasons else
           'MEDIUM' if 'LOW_FREQUENCY' in reasons or 'FEW_ACTIVE_DAYS' in reasons else 'LOW')
    return {'level':level,'reasons':reasons,'observed_days':days,'positive_days':positive,
        'consumption_day_percent':frequency,'top3_share_percent':share,'top_days':largest,
        'largest_quantity':largest[0]['quantity'] if largest else None,
        'largest_date':largest[0]['day'] if largest else None,
        'outlier_days':len(outliers),'minimum_observed_days':30}


def spot_analysis(values,start,monthly,daily_mean):
    """Informative heuristic on positive daily NET demand; no automatic exclusion.

    Quartiles use linear interpolation at (n-1)*p. Tukey's upper inner fence
    is combined with a conservative 3x-median guard and 8-positive-day minimum.
    """
    positive=sorted(value for value in values if value>0)
    count=len(positive);normal=median(positive) if count else None
    def quantile(p):
        position=(count-1)*p;lower=int(position);fraction=position-lower
        return positive[lower]+fraction*(positive[min(lower+1,count-1)]-positive[lower])
    q1,q3=(quantile(.25),quantile(.75)) if count else (None,None)
    threshold=max(3*normal,q3+1.5*(q3-q1)) if count else None
    eligible=count>=8
    flagged=[{'day':(start+timedelta(days=i)).isoformat(),'demand':value,'times_normal':value/normal}
             for i,value in enumerate(values) if eligible and value>threshold]
    excluded_by_month=defaultdict(float)
    for row in flagged:excluded_by_month[row['day'][:7]]+=row['demand']
    baseline=mean((max(0,row['consumption']-excluded_by_month[row['month']])/row['observed_days']*row['calendar_days'])
                  for row in monthly)/30 if monthly else 0
    quantity=sum(row['demand'] for row in flagged);total=sum(values)
    single=next(({'day':(start+timedelta(days=i)).isoformat(),'quantity':value} for i,value in enumerate(values) if value>0),None) if count==1 else None
    return {'exceptionality':exceptionality_analysis(values,start,flagged),'single_consumption':single,'status':'NO_CONSUMPTION' if not count else 'SINGLE_CONSUMPTION' if count==1 else 'INSUFFICIENT' if not eligible else 'POSSIBLE_SPOT' if flagged else 'NO_OUTLIERS',
        'positive_days':count,'minimum_positive_days':8,'normal_daily_median':normal,'q1':q1,'q3':q3,'upper_threshold':threshold,
        'outliers':flagged,'flagged_quantity':quantity,'flagged_share_percent':quantity/total*100 if total else 0,
        'daily_mean':daily_mean,'daily_mean_without_peaks':baseline,
        'mean_uplift_percent':(daily_mean-baseline)/baseline*100 if baseline>0 else None}


def demand_statistics(article,delegation,source,parameters,sales_index,include_daily=False):
    end=date.fromisoformat(source['end']);start=date.fromisoformat(source['start'])
    if parameters['history_days']:start=max(start,end-timedelta(days=parameters['history_days']-1))
    created=None
    try:created=date.fromisoformat((article.get('created_at') or '')[:10])
    except ValueError:pass
    if created and start<created<=end:start=created
    days=(end-start).days+1
    daily=[];values=[];months={};gross=returned=0;last_sale=None;anomalous=0
    for offset in range(days):
        day=(start+timedelta(days=offset)).isoformat();sold,back=sales_index.get((article['sku'],delegation,day),(0,0))
        gross+=sold;returned+=back;anomalous+=int(back>sold)
        if sold>0:last_sale=day
        values.append(max(0,sold-back))
        bucket=months.setdefault(day[:7], {'month':day[:7], 'observed_days':0, 'consumption':0, 'calendar_days':monthrange(int(day[:4]),int(day[5:7]))[1]})
        bucket['observed_days']+=1;bucket['consumption']+=values[-1]
        if include_daily:daily.append({'day':day,'sold':sold,'returned':back,'demand':values[-1]})
    monthly=[]
    for bucket in months.values():
        bucket['estimated']=bucket['observed_days']<bucket['calendar_days']
        bucket['monthly_consumption']=bucket['consumption']/bucket['observed_days']*bucket['calendar_days'] if bucket['estimated'] else bucket['consumption']
        monthly.append(bucket)
    monthly_mean=mean(row['monthly_consumption'] for row in monthly) if monthly else 0
    average=monthly_mean/30;deviation=pstdev(values) if values else 0
    sales_days=sum(value>0 for value in values)
    adi=days/sales_days if sales_days else None
    irregular=bool(sales_days and (adi>1.32 or (average>0 and deviation/average>1)))
    positive=[value for value in values if value>0]
    frequencies=Counter(positive);frequency=max(frequencies.values(),default=0)
    modes=sorted(value for value,count in frequencies.items() if count==frequency) if frequency>1 else []
    analysis=spot_analysis(values,start,monthly,average)
    exceptionality=analysis.pop('exceptionality')
    return {'exceptionality':exceptionality,'spot_analysis':analysis,'daily_median':median(positive) if positive else None,'daily_modes':modes,'positive_consumption_days':len(positive),
            'days':days,'start':start.isoformat(),'end':end.isoformat(),'daily':daily,'demand_values':values,'gross_sales':gross,
            'returns':returned,'total_demand':sum(values),'daily_mean':average,'monthly_mean':monthly_mean,'monthly_consumption':monthly,'daily_std':deviation,
            'sales_days':sales_days,'last_sale':last_sale,'irregular':irregular,'anomalous_return_days':anomalous,
            'new_article':bool(created and (end-created).days<30),'created_in_future':bool(created and created>end)}

def consumption_reference(stats,parameters):
    basis=parameters.get('consumption_basis','MEAN')
    if basis=='MEAN':return stats['daily_mean'],True
    if not stats['positive_consumption_days']:return 0,True
    if basis=='MEDIAN':return stats['daily_median'],True
    return (max(stats['daily_modes']),True) if stats['daily_modes'] else (0,False)

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
            value=demand_statistics(article,delegation,source,parameters,sales_index)
            if not value['irregular']:value['demand_values']=[]
            stats[key]=value
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
    if quantity<=0:return 0
    if multiple is None:return float(Decimal(str(quantity)).to_integral_value(rounding=ROUND_CEILING))
    value=Decimal(str(quantity));step=Decimal(str(multiple))
    return float((value/step).to_integral_value(rounding=ROUND_CEILING)*step)

def calculate_article(article,delegation,context,override=None,include_daily=False):
    key=(article['sku'],delegation);parameters,rules,origins=context['resolved'][key]
    parameters=dict(parameters)
    if override:
        parameters=Parameters.model_validate({**parameters,**override}).model_dump();rules=[*rules,'Ajuste del artículo'];origins={**origins,**{key:'Ajuste del artículo' for key in override}}
    stats=demand_statistics(article,delegation,context['source'],parameters,context['sales_index'],include_daily) if override or include_daily else context['stats'][key]
    avg,statistic_available=consumption_reference(stats,parameters)
    std=stats['daily_std'];horizon=parameters['review_days']+parameters['lead_days']
    z=NormalDist().inv_cdf(parameters['service_level']/100)
    safety=z*std*sqrt(parameters['lead_days']) if parameters['use_safety_stock'] else 0;minimum=avg*parameters['lead_days']+safety;maximum=avg*horizon+safety
    method='REVISION_PERIODICA';confidence='ALTA' if stats['sales_days']>=30 and not stats['irregular'] else 'MEDIA'
    recs=[];comparable=None
    analysis=stats['spot_analysis']
    if analysis['status']=='POSSIBLE_SPOT':
        recs.append(recommendation('POSIBLE_SPOT','Hay consumos diarios atípicos que elevan la media. Revisa si son ventas puntuales antes de reponer; no se ha excluido ninguna cantidad.',{'days':len(analysis['outliers']),'share_percent':analysis['flagged_share_percent'],'daily_mean_without_peaks':analysis['daily_mean_without_peaks']}))
    sparse=stats['sales_days']<5 or stats['new_article']
    if sparse and not parameters["simple_formula"] and parameters["consumption_basis"]=="MEAN":
        safety=minimum=maximum=0;confidence='BAJA';method='REVISION_MANUAL'
        policy=parameters['new_policy'] if stats['new_article'] else parameters['no_sales_policy']
        if policy!='NO_REPLENISH':
            for level in ('type_id','subfamily_id','family_id'):
                candidates=[value for sku,value in context['comparables'].get((delegation,level,article.get(level),article.get('unit_type','')),[]) if sku!=article['sku']]
                if len(candidates)>=3:
                    estimate=median(candidates);minimum=maximum=estimate*max(1,parameters['lead_days'])
                    comparable={'level':level,'count':len(candidates),'median_daily_demand':estimate,'indicative_minimum':minimum}
                    method='MINIMO_ORIENTATIVO_COMPARABLES';break
        recs.append(recommendation('HISTORICO_INSUFICIENTE','Histórico insuficiente: revisar la propuesta orientativa; no representa ventas reales del artículo.',
            {'days':stats['days'],'sales_days':stats['sales_days'],'comparables':comparable},'new_policy' if stats['new_article'] else 'no_sales_policy',policy))
    elif stats['irregular'] and not parameters['simple_formula'] and parameters['use_safety_stock'] and parameters['consumption_basis']=='MEAN':
        # Percentil empírico de demanda en ventanas completas del horizonte.
        values=stats['demand_values'];sums=[]
        if len(values)>=horizon:
            current=sum(values[:horizon]);sums=[current]
            for index in range(horizon,len(values)):
                current+=values[index]-values[index-horizon];sums.append(current)
        if len(sums)>=5:
            sums.sort();maximum=sums[min(len(sums)-1,ceil(len(sums)*parameters['service_level']/100)-1)]
            safety=max(0,maximum-avg*horizon);minimum=min(maximum,avg*parameters['lead_days']+safety)
            method='PERCENTIL_EMPIRICO_INTERMITENTE';confidence='BAJA'
        else:
            safety=minimum=maximum=0;method='REVISION_MANUAL';confidence='BAJA'
    raw_maximum=maximum
    stock=context['stocks'].get(key);position=stock['stock']+stock['incoming']-stock['outgoing'] if stock else None
    original_target=minimum+(avg*parameters['review_days'] if method!='REVISION_MANUAL' else 0)
    calculated=max(0,original_target-position) if position is not None else 0
    if parameters['max_coverage_days'] and avg>0:
        maximum=min(maximum,avg*parameters['max_coverage_days'])
    if parameters['manual_min'] is not None:minimum=parameters['manual_min']
    if parameters['manual_max'] is not None:maximum=parameters['manual_max']
    if parameters['maximum_days'] is not None:
        maximum=minimum+avg*parameters['maximum_days']
        if parameters['manual_max'] is not None:maximum=parameters['manual_max']
        if parameters['max_coverage_days'] and avg>0:maximum=min(maximum,avg*parameters['max_coverage_days'])
    maximum=max(minimum,maximum)
    if sparse and (parameters['manual_min'] is not None or parameters['manual_max'] is not None):method='LIMITES_MANUALES';confidence='BAJA'
    expected_consumption=avg*parameters['review_days'] if method!='REVISION_MANUAL' else 0
    replenishment_point=minimum+expected_consumption
    target=maximum if parameters["target_mode"]=="MAXIMUM" else replenishment_point
    # Only explicitly configured limits cap the point; calculated maximum is not a target.
    if parameters['max_coverage_days'] and avg>0:
        target=max(minimum,min(target,avg*parameters['max_coverage_days']))
    if parameters['manual_max'] is not None:
        target=max(minimum,min(target,parameters['manual_max']))
    if parameters["target_mode"]=="POINT" and target<replenishment_point:
        recs.append(recommendation('OBJETIVO_LIMITADO','Un límite explícito reduce el punto de reposición; revisa si cubre el consumo hasta la próxima reposición.',
            {'replenishment_point':replenishment_point,'limited_target':target,'minimum':minimum},'manual_max' if parameters['manual_max'] is not None else 'max_coverage_days',parameters['manual_max'] if parameters['manual_max'] is not None else parameters['max_coverage_days']))
    quantity=max(0,target-position) if position is not None else 0
    calculated=quantity
    dispatch_multiple=effective_dispatch_multiple(article,parameters)
    before_rounding=max(quantity,parameters['minimum_quantity']) if quantity>0 else 0
    quantity=rounded_dispatch(before_rounding,dispatch_multiple)
    if parameters['multiple_mode']=='EXIT' and dispatch_multiple is None:
        quantity=0
        recs.append(recommendation('MULTIPLO_EXIT_INVALIDO','EX_multiplo no contiene un múltiplo positivo válido. La propuesta queda a cero hasta revisar el formato de despacho.',
            {'exit_multiple':article.get('exit_multiple'),'quantity_before_rounding':before_rounding},'multiple_mode','EXIT'))
    if parameters['exclude_no_consumption'] and stats['total_demand']<=0:
        quantity=0
        recs.append(recommendation('SIN_CONSUMO_EXCLUIDO','Sin consumo neto en el periodo: se ha excluido de la reposición por la opción seleccionada.',{'total_demand':stats['total_demand']}))
    if not parameters['enabled'] or stats['created_in_future'] or (sparse and (parameters['new_policy'] if stats['new_article'] else parameters['no_sales_policy'])=='NO_REPLENISH'):quantity=0
    if not statistic_available:
        quantity=0
        recs.append(recommendation('SIN_MODA','No hay un consumo positivo repetido: no se propone reposición ni redistribución con moda. Revisa el material o elige otro criterio.',{'positive_days':stats['positive_consumption_days']}))
    elif parameters['consumption_basis']=='MODE' and len(stats['daily_modes'])>1:
        recs.append(recommendation('MODA_MULTIPLE','Hay varias modas; se utiliza la mayor para el cálculo.',{'modes':stats['daily_modes'],'selected':avg}))
    if quantity>0 and position is not None and position+quantity>target+1e-8:
        recs.append(recommendation('REDONDEO_SOBRE_MAXIMO','El múltiplo o la cantidad mínima elevan el inventario por encima del objetivo elegido.',
            {'quantity':quantity,'position_after':position+quantity,'target':target,'effective_multiple':dispatch_multiple},'multiple_mode',parameters['multiple_mode']))
    overstock=bool(statistic_available and position is not None and position>maximum+1e-8)
    excess=max(0,position-maximum) if statistic_available and position is not None else 0
    coverage=position/avg if position is not None and avg>0 else None
    if coverage is not None and coverage>max(90,3*horizon):
        recs.append(recommendation('EXCESO_STOCK',f'El inventario equivale a {coverage:.1f} días de demanda observada.',
            {'coverage_days':coverage,'replenishment_point':replenishment_point},'review_days',parameters['review_days'],confidence=confidence))
    if position is not None and avg>0 and position<target:
        recs.append(recommendation('STOCK_INSUFICIENTE','El disponible previsto está por debajo del objetivo de reposición elegido.',
            {'position':position,'target':target,'minimum':minimum,'expected_cycle_consumption':expected_consumption},'review_days',parameters['review_days'],confidence=confidence))
    if stats['irregular']:
        recs.append(recommendation('DEMANDA_IRREGULAR','Ventas irregulares: el cálculo no incluye stock de seguridad por la opción seleccionada.' if not parameters['use_safety_stock'] else 'Ventas irregulares: revisa la seguridad calculada con la desviación observada.' if parameters['simple_formula'] else 'Ventas intermitentes: se utiliza un percentil empírico o se requiere revisión, no el modelo normal de forma ciega.',
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
    if avg>0 and (safety>3*avg*horizon or target/avg>max(90,3*horizon)):
        recs.append(recommendation('PARAMETROS_REVISAR','La seguridad o el objetivo de reposición generan una cobertura elevada respecto a la demanda.',
            {'safety':safety,'horizon_demand':avg*horizon,'target_coverage':target/avg},'max_coverage_days',parameters['max_coverage_days']))
    if quantity>max(1000,avg*horizon*10) or (stats['gross_sales']==0 and quantity>0) or (avg>0 and quantity==0 and position is not None and position<minimum):
        recs.append(recommendation('PROPUESTA_REVISAR','Revisar una cantidad elevada, una reposición sin ventas o una reposición cero bajo el mínimo.',
            {'quantity':quantity,'position':position,'minimum':minimum,'horizon_demand':avg*horizon}))
    result={**article,'delegation':delegation,'stock':stock['stock'] if stock else None,'incoming':stock['incoming'] if stock else None,
        'outgoing':stock['outgoing'] if stock else None,'inventory_position':position,'gross_sales':stats['gross_sales'],
        'returns':stats['returns'],'total_demand':stats['total_demand'],'daily_mean':stats['daily_mean'],'daily_reference':avg,'spot_analysis':analysis,'exceptionality':stats['exceptionality'],'consumption_basis':parameters['consumption_basis'],'statistic_available':statistic_available,'daily_median':stats['daily_median'],'daily_modes':stats['daily_modes'],'positive_consumption_days':stats['positive_consumption_days'],'monthly_mean':stats['monthly_mean'],'monthly_consumption':stats['monthly_consumption'],'daily_std':std,'sales_days':stats['sales_days'],
        'last_sale':stats['last_sale'],'observed_days':stats['days'],'irregular':stats['irregular'],'new_article':stats['new_article'],
        'overstock':overstock,'excess_stock':excess,'no_consumption':stats['total_demand']<=0,'target_mode':parameters['target_mode'],
        'calculation_model':'MAXIMUM_COVERAGE' if parameters['target_mode']=='MAXIMUM' else 'MINIMUM_PLUS_CYCLE_DEMAND','replenishment_point':replenishment_point,'target_stock':target,'expected_cycle_consumption':expected_consumption,'safety_stock':safety,'minimum_stock':minimum,'maximum_stock':maximum,'calculated_quantity':calculated,
        'recommended_quantity':round(quantity,6),'adjusted_quantity':None,'final_quantity':round(quantity,6),'coverage_days':coverage,
        'confidence':confidence,'method':method,'comparables':comparable,'parameters':parameters,'applied_rules':rules,
        'parameter_origins':origins,'recommendations':recs,'manual_parameters':{},'effective_multiple':dispatch_multiple,'quantity_before_rounding':before_rounding,
        'calculation':{'horizon':horizon,'z':z,'formula':('Stock máximo = stock mínimo + consumo diario × días de cobertura máxima' if parameters['target_mode']=='MAXIMUM' else 'Punto de reposición = stock mínimo + consumo diario × días hasta próxima reposición') + '; cantidad = max(0, objetivo − disponible previsto).',
            'safety_formula':'Sin stock de seguridad (opción seleccionada)' if not parameters['use_safety_stock'] else 'Z × desviación diaria × sqrt(plazo de llegada)' if method=='REVISION_PERIODICA' else 'Modelo alternativo explicado en método y recomendaciones',
            'maximum_formula':'stock mínimo + consumo diario × días de cobertura máxima', 'minimum_formula':'consumo diario × plazo de llegada + stock de seguridad' if parameters['use_safety_stock'] else 'consumo diario × plazo de llegada', 'dispatch_days':parameters['review_days'],'lead_days':parameters['lead_days'],'raw_maximum':raw_maximum,'window_start':stats['start'],'window_end':stats['end']}}
    result['comparison_eligible']=bool(statistic_available and parameters['enabled'] and not stats['created_in_future'] and not (parameters['exclude_no_consumption'] and stats['total_demand']<=0) and not (sparse and (parameters['new_policy'] if stats['new_article'] else parameters['no_sales_policy'])=='NO_REPLENISH'))
    result=quantity_comparison(result)
    if include_daily:
        # Median/modes describe active consumption days only. Sigma and the
        # weekly evidence still retain zero days over the entire observed window.
        positive_values=[value for value in stats['demand_values'] if value>0]
        counts=Counter(positive_values)
        frequency=max(counts.values(),default=0)
        weeks={}
        for item in stats['daily']:
            day=date.fromisoformat(item['day']);monday=(day-timedelta(days=day.weekday())).isoformat()
            bucket=weeks.setdefault(monday,{'week_start':monday,'from':item['day'],'to':item['day'],
                'observed_days':0,'sold':0,'returned':0,'demand':0})
            bucket['to']=item['day'];bucket['observed_days']+=1
            for key in ('sold','returned','demand'):bucket[key]+=item[key]
        median_value=median(positive_values) if positive_values else None
        modes=sorted(value for value,count in counts.items() if count==frequency) if frequency>1 else []
        dates_by_value=defaultdict(list)
        for item in stats['daily']:
            if item['demand']>0:dates_by_value[item['demand']].append(item['day'])
        result.update(daily_sales=stats['daily'],daily_median=median_value,
            daily_median_frequency=counts.get(median_value,0),daily_median_dates=dates_by_value.get(median_value,[]),
            daily_modes=modes,daily_mode_occurrences=[{'value':value,'count':counts[value],'dates':dates_by_value[value]} for value in modes],
            daily_mode_frequency=frequency,positive_consumption_days=len(positive_values),weekly_sales=list(weeks.values()))
    return result

def quantity_comparison(row):
    """Compare the same saved need without changing legacy/manual final quantities."""
    multiple=effective_dispatch_multiple(row,{'multiple_mode':'EXIT'})
    allowed=row.get('comparison_eligible')
    if allowed is None:
        allowed=row.get('recommended_quantity',row.get('final_quantity',0))>0 or any(
            note['code']=='MULTIPLO_EXIT_INVALIDO' for note in row.get('recommendations',[]))
        if row.get('parameters',{}).get('exclude_no_consumption') and row.get('no_consumption'):allowed=False
        params=row.get('parameters',{})
        if not params.get('enabled',True):allowed=False
        sparse=row.get('sales_days',0)<5 or row.get('new_article',False)
        if sparse and params.get('new_policy' if row.get('new_article') else 'no_sales_policy')=='NO_REPLENISH':allowed=False
        created=str(row.get('created_at') or '')[:10]
        window_end=row.get('calculation',{}).get('window_end')
        if created and window_end and created>window_end:allowed=False
    raw=row.get('quantity_before_rounding',row.get('calculated_quantity',0)) if allowed else 0
    if row.get('adjusted_quantity') is not None:raw=row['adjusted_quantity']
    if row.get('manually_excluded'):raw=0
    return {**row,'quantity_without_multiple':round(rounded_dispatch(raw,None),6),
        'quantity_with_exit_multiple':round(rounded_dispatch(raw,multiple),6) if multiple is not None else (0 if raw<=0 else None),
        'exit_multiple_valid':multiple is not None}

def annotate_central(results,source):
    """Comprueba la propuesta conjunta sin prometer entradas pendientes ni asignar dos veces stock."""
    central={row['sku']:row for row in source['stocks'] if row['delegation']=='00'}
    articles={row['sku']:row for row in source['articles']}
    groups=defaultdict(list);sales_index={}
    for row in source['sales']:
        key=(row['sku'],row['delegation'],row['day']);old=sales_index.get(key,(0,0))
        sales_index[key]=(old[0]+row['sold'],old[1]+row['returned'])
    central_sales_known='00' in source.get('sales_delegations',[]) or any(row['delegation']=='00' for row in source['sales'])
    for row in results:
        row.update(quantity_comparison(row))
        groups[row['sku']].append(row)
    for sku,rows in groups.items():
        stock=central.get(sku);total=sum(row['final_quantity'] for row in rows)
        comparison_totals={key:(sum(row[key] for row in rows) if all(row[key] is not None for row in rows) else None) for key in ('quantity_without_multiple','quantity_with_exit_multiple')}
        stats_cache={};reserve=0;central_avg=0;central_observed_avg=0;reserve_days=0;central_std=0
        for row in rows:
            params=Parameters.model_validate(row['parameters']).model_dump()
            history=params['history_days']
            if history not in stats_cache:
                stats_cache[history]=demand_statistics(articles[sku],'00',source,params,sales_index)
            stats=stats_cache[history];central_observed_avg=max(central_observed_avg,stats['daily_mean']);avg,available_statistic=consumption_reference(stats,params);std=stats['daily_std']
            if not available_statistic:stats['basis_unavailable']=True
            risk=params['lead_days']+params['central_reserve_days']
            safety=NormalDist().inv_cdf(params['service_level']/100)*std*sqrt(params['lead_days']) if params['use_safety_stock'] else 0
            required=avg*(params['lead_days']+params['central_reserve_days'])+safety
            reserve=max(reserve,required);central_avg=max(central_avg,avg);central_std=max(central_std,std)
            reserve_days=max(reserve_days,params['central_reserve_days'])
        valid_stock=stock is not None and stock['stock']>=0 and stock['outgoing']>=0 and stock['incoming']>=0
        valid_history=central_sales_known and not any(stats['created_in_future'] or stats.get('basis_unavailable') for stats in stats_cache.values())
        # PendienteRecibir se muestra, pero no se promete como stock físico transferible.
        physical=max(0,stock['stock']-stock['outgoing']) if valid_stock else None
        available=max(0,physical-reserve) if physical is not None and valid_history else None
        covered=bool(total>0 and available is not None and total<=available+1e-8)
        for row in rows:
            row['recommendations']=[r for r in row['recommendations'] if r['code'] not in ('CENTRAL_INSUFICIENTE','CENTRAL_SIN_DATOS')]
            row.update(central_stock=stock['stock'] if stock else None,central_incoming=stock['incoming'] if stock else None,
                central_outgoing=stock['outgoing'] if stock else None,
                central_position=stock['stock']+stock['incoming']-stock['outgoing'] if stock else None,
                central_physical_available=physical,central_monthly_consumption=central_observed_avg*30 if valid_history else None,
                central_daily_mean=central_observed_avg if valid_history else None,central_daily_reference=central_avg if valid_history else None,central_daily_std=central_std if valid_history else None,
                central_reserve=reserve if valid_history else None,central_reserve_days=reserve_days,
                central_available=available,central_total_requested=total,central_can_supply=covered and row['final_quantity']>0,
                central_shortage=max(0,total-available) if available is not None else None)
            for key,suffix in [('quantity_without_multiple','without_multiple'),('quantity_with_exit_multiple','with_exit_multiple')]:
                requested=comparison_totals[key]
                row['central_total_'+suffix]=requested
                row['central_covers_'+suffix]=(None if requested is None or available is None else bool(requested<=available+1e-8))
            if total>0 and not covered:
                row['recommendations'].append(recommendation('CENTRAL_SIN_DATOS' if available is None else 'CENTRAL_INSUFICIENTE',
                    'No se puede asegurar despacho: faltan datos de stock o consumo de Almeiras.' if available is None else
                    'Almeiras no cubre la propuesta conjunta después de reservar su consumo. No despachar esta propuesta completa sin provocar una rotura de stock.',
                    {'total_requested':total,'central_available':available,'central_stock':row['central_stock'],
                     'central_reserve':row['central_reserve'],'central_monthly_consumption':row['central_monthly_consumption']}))

def summarize(results):
    coverage=[row.get('target_stock',row['maximum_stock'])/row.get('daily_reference',row['daily_mean']) for row in results if row.get('daily_reference',row['daily_mean'])>0]
    return {'articles_analyzed':len({row['sku'] for row in results}),'article_delegations':len(results),
        'to_replenish':sum(row['final_quantity']>0 for row in results),'units_proposed':sum(row['final_quantity'] for row in results),
        'overstock':sum(row.get('overstock',False) for row in results),'central_covered':sum(row.get('central_can_supply',False) for row in results),
        'without_movement':sum(row.get('no_consumption',row['gross_sales']==0) for row in results),'irregular':sum(row['irregular'] for row in results),
        'alerts':sum(len(row['recommendations']) for row in results),'target_stock':sum(row.get('target_stock',row['maximum_stock']) for row in results),
        'average_coverage_days':mean(coverage) if coverage else None}


def selected_basis(row,basis=None):
    """Select an already saved calculation, never calculate while filtering."""
    if basis is None or row.get('consumption_basis','MEAN')==basis:
        return {key:value for key,value in row.items() if key!='consumption_variants'}
    return row.get('consumption_variants',{}).get(basis)


def calculate_all_bases(source,delegations,policies,temporary):
    calculations={}
    for basis in BASIS_LABELS:
        context=prepare_context(source,delegations,policies,{**temporary,'consumption_basis':basis})
        rows=[calculate_article(article,delegation,context) for article in source['articles'] for delegation in delegations]
        annotate_central(rows,source)
        calculations[basis]=rows
    primary=temporary.get('consumption_basis','MEAN')
    return [{**row,'consumption_variants':{basis:calculations[basis][i] for basis in BASIS_LABELS if basis!=primary}}
            for i,row in enumerate(calculations[primary])]


def annotate_all_bases(rows,source):
    for basis in BASIS_LABELS:
        selected=[(row,selected_basis(row,basis)) for row in rows]
        selected=[(row,view) for row,view in selected if view is not None]
        annotate_central([view for _,view in selected],source)
        for row,view in selected:
            if row.get('consumption_basis','MEAN')==basis:row.update(view)
            else:row['consumption_variants'][basis]=view


def consumption_analysis_label(row):
    info=row.get('exceptionality')
    if info:
        labels={'HIGH':'Alta excepcionalidad · revisar','MEDIUM':'Consumo poco frecuente · revisar',
                'LOW':'Sin señales de excepcionalidad','LIMITED_HISTORY':'Periodo corto · interpretación limitada',
                'NO_CONSUMPTION':'Sin consumo positivo'}
        flags={'CONCENTRATION':'consumo concentrado en pocos días','LOW_FREQUENCY':'baja frecuencia',
               'OUTLIERS':'picos atípicos','FEW_ACTIVE_DAYS':'pocos días de consumo','SHORT_PERIOD':'menos de 30 días observados'}
        return (f"{labels[info['level']]}: {info['positive_days']} de {info['observed_days']} días con consumo "
                f"({info['consumption_day_percent']:.1f} %); {info['top3_share_percent']:.1f} % del consumo en los {len(info['top_days'])} mayores días. "
                + '; '.join(flags[key] for key in info['reasons']))
    analysis=row.get('spot_analysis') or {}
    if analysis.get('positive_days',row.get('positive_consumption_days'))==1:
        return f"Consumo único · revisar: {row.get('total_demand',0):g} {row.get('unit_type','')} en 1 día. Generar cálculo nuevo para el indicador completo."
    return 'Excepcionalidad sin analizar: generar un cálculo nuevo.'
