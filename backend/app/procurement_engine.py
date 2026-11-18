"""Periodic purchasing cover for the five-branch network, with material-specific EXIT terms."""
from collections import defaultdict
from math import sqrt
from statistics import NormalDist
from .replenishment_engine import Parameters, consumption_reference, demand_statistics, rounded_dispatch
from .replenishment_source import CALCULATION_DELEGATIONS, dispatch_multiple


def terms(value,minimum):
    number=dispatch_multiple(value)
    return number if number is not None and minimum<=number<=3650 else None


def calculate(source,use_safety_stock=True,service_level=95):
    # Aggregate daily NET customer demand, not replenishment suggestions/transfers.
    # Net each branch/day first, preserving the existing returns floor at zero.
    branch_days=defaultdict(lambda:[0,0])
    for row in source['sales']:
        if row['delegation'] in CALCULATION_DELEGATIONS:
            pair=branch_days[(row['sku'],row['delegation'],row['day'])]
            pair[0]+=row['sold'];pair[1]+=row['returned']
    sales=defaultdict(lambda:[0,0])
    for (sku,delegation,day),(sold,returned) in branch_days.items():sales[(sku,'NW',day)][0]+=max(0,sold-returned)
    stock_index=defaultdict(dict)
    for row in source['stocks']:
        if row['delegation'] in CALCULATION_DELEGATIONS:
            if row['delegation'] in stock_index[row['sku']]:raise ValueError('Stock duplicado de artículo/delegación')
            stock_index[row['sku']][row['delegation']]=row
    params=Parameters(simple_formula=True).model_dump();z=NormalDist().inv_cdf(service_level/100)
    output=[]
    for article in source['articles']:
        stats=demand_statistics(article,'NW',source,params,sales)
        coverage=terms(article.get('procurement_coverage_days'),.000001)
        lead=terms(article.get('procurement_lead_days'),0)
        branches=stock_index[article['sku']]
        complete=set(branches)==set(CALCULATION_DELEGATIONS)
        valid_stock=complete and all(dispatch_multiple(row.get(key)) is not None and (key=='stock' or row[key]>=0) for row in branches.values() for key in ('stock','incoming','outgoing'))
        position=sum(r['stock']+r['incoming']-r['outgoing'] for r in branches.values()) if valid_stock else None
        notes=[]
        if coverage is None:notes.append('Revisar Aprovisionamiento en EXIT: días de cobertura ausentes o no válidos.')
        if lead is None:notes.append('Revisar DiasReposicion en EXIT: plazo ausente o no válido.')
        if not valid_stock:notes.append('Falta stock o pendientes válidos en alguna de las cinco delegaciones; no se propone compra.')
        if any(dispatch_multiple(row.get('stock')) is not None and row['stock']<0 for row in branches.values()):notes.append('Hay stock negativo: revisar los compromisos y el inventario.')
        if any(dispatch_multiple(row.get('incoming')) is not None and row['incoming']>0 for row in branches.values()):notes.append('Hay entradas pendientes sin fecha de llegada: confirmar plazos y que los traspasos internos estén reflejados en ambos lados.')
        if stats['spot_analysis']['status']=='SINGLE_CONSUMPTION':notes.append('Consumo en un solo día: revisar si es compra puntual. No se ha excluido del cálculo.')
        if stats['exceptionality']['level']=='HIGH':notes.append('Alta excepcionalidad: revisar ventas puntuales antes de comprar.')
        if stats['created_in_future']:notes.append('Fecha de alta futura: revisar el material antes de comprar.')
        if stats['days']<30:notes.append('Menos de 30 días de histórico; propuesta de baja confianza.')
        variants={}
        for basis in ('MEAN','MEDIAN','MODE'):
            daily,available=consumption_reference(stats,{'consumption_basis':basis})
            valid=coverage is not None and lead is not None and position is not None and available and not stats['created_in_future']
            horizon=(coverage+lead) if coverage is not None and lead is not None else None
            safety=z*stats['daily_std']*sqrt(horizon) if horizon is not None and use_safety_stock and stats['total_demand']>0 else 0
            target=daily*horizon+safety if horizon is not None and available else None
            raw=max(0,target-position) if valid else None
            # No demand does not establish a reason to buy, even with negative inventory.
            if valid and stats['total_demand']<=0:raw=0
            multiple=dispatch_multiple(article.get('exit_multiple'))
            quantity=rounded_dispatch(raw,None) if raw is not None else None
            grouped=rounded_dispatch(raw,multiple) if raw is not None and multiple is not None and multiple>0 else (0 if raw==0 else None)
            variants[basis]={'daily_reference':daily if available else None,'statistic_available':available,
                'safety_stock':safety if horizon is not None else None,'target_stock':target,
                'quantity':quantity,'quantity_with_multiple':grouped,
                'coverage_now':position/daily if position is not None and daily>0 else None,
                'status':'REVIEW' if not valid else 'BUY' if quantity>0 else 'COVERED'}
        output.append({**article,'stock':sum(r['stock'] for r in branches.values()) if valid_stock else None,
            'incoming':sum(r['incoming'] for r in branches.values()) if valid_stock else None,
            'outgoing':sum(r['outgoing'] for r in branches.values()) if valid_stock else None,
            'central_stock':branches.get('00',{}).get('stock'),'inventory_position':position,
            'coverage_days':coverage,'lead_days':lead,'protection_days':coverage+lead if coverage is not None and lead is not None else None,
            'monthly_mean':stats['monthly_mean'],'daily_std':stats['daily_std'],'daily_median':stats['daily_median'],'daily_modes':stats['daily_modes'],
            'observed_days':stats['days'],'positive_days':stats['sales_days'],'total_demand':stats['total_demand'],
            'exceptionality':stats['exceptionality'],'variants':variants,'notes':notes,
            'captured_at':source['captured_at'],'start':source['start'],'end':source['end']})
    return output
