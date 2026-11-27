"""Interchanges currently in transit, grouped through the configured stock warehouses."""
from collections import defaultdict
from sqlalchemy import select
from .db import SessionLocal
from .models import DelegationWarehouse


def stock_warehouse_map(company=1):
    with SessionLocal() as db:
        rows=db.scalars(select(DelegationWarehouse).where(DelegationWarehouse.company_code==company,
            DelegationWarehouse.active.is_(True),DelegationWarehouse.use_for_stock.is_(True))).all()
        mapping={}
        for row in rows:
            previous=mapping.get(row.warehouse_code)
            if previous is not None and previous!=row.delegation_code:
                raise ValueError(f'El almacén {row.warehouse_code} está marcado para stock en más de una delegación de la empresa {company}. Revisa Delegaciones y almacenes.')
            mapping[row.warehouse_code]=row.delegation_code
    if not mapping:raise ValueError('Configura los almacenes activos para stock en Delegaciones y almacenes antes de sumar los intercambios en tránsito.')
    return mapping


def fetch_transits(cursor,codes):
    # Some EXIT schemas have a series in this document key, others use company/year/number only.
    cursor.execute("SELECT TABLE_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME IN ('MovimientoAlmacenCabecera','MovimientoAlmacenLineas')")
    columns=defaultdict(set)
    for row in cursor.fetchall():columns[str(row.get('TABLE_NAME','')).casefold()].add(str(row.get('COLUMN_NAME','')).casefold())
    shared=columns['movimientoalmacencabecera']&columns['movimientoalmacenlineas']
    series=''.join(f' AND mac.[{name}]=mal.[{name}]' for name in ('Serie','SerieMovimiento','SerieMovimientoAlmacen') if name.casefold() in shared)
    marks=','.join(['%s']*len(codes))
    cursor.execute(f'''SELECT mal.CodigoArticulo AS sku, mal.CodigoAlmacen AS origin,
        mal.AlmacenContrapartida AS destination, SUM(mal.Unidades) AS units
        FROM dbo.MovimientoAlmacenCabecera mac INNER JOIN dbo.MovimientoAlmacenLineas mal
        ON mac.CodigoEmpresa=mal.CodigoEmpresa AND mac.Ejercicio=mal.Ejercicio AND mac.Numero=mal.Numero{series}
        WHERE mac.CodigoEmpresa=%s AND mal.EX_EstadoMovA=%s AND mal.TipoMovimientoAlmacen=%s
        AND mal.CodigoArticulo IN ({marks})
        GROUP BY mal.CodigoArticulo,mal.CodigoAlmacen,mal.AlmacenContrapartida''',(1,'Transito','T',*codes))
    return [{'sku':str(row['sku']).strip(),'origin':str(row['origin'] if row['origin'] is not None else '').strip(),
             'destination':str(row['destination'] if row['destination'] is not None else '').strip(),'units':row['units']} for row in cursor.fetchall()]


def add_transits(stocks,transits,mapping):
    from .replenishment_source import number,CALCULATION_DELEGATIONS
    totals=defaultdict(lambda:{'incoming':0.0,'outgoing':0.0})
    for row in transits:
        units=number(row['units'])
        if units<0:raise ValueError('EXIT devuelve unidades negativas en un intercambio en tránsito. Revisa el movimiento antes de calcular.')
        for warehouse,field in ((row['origin'],'outgoing'),(row['destination'],'incoming')):
            delegation=mapping.get(warehouse)
            if delegation in CALCULATION_DELEGATIONS:totals[(row['sku'],delegation)][field]+=units
    # Keep absent base stock absent: a transfer alone does not prove zero physical stock.
    for row in stocks:
        transit=totals.get((row['sku'],row['delegation']),{'incoming':0,'outgoing':0})
        row.update(incoming_exit=row['incoming'],outgoing_exit=row['outgoing'],incoming_transit=transit['incoming'],outgoing_transit=transit['outgoing'],interchanges_included=True)
        row['incoming']+=transit['incoming'];row['outgoing']+=transit['outgoing']
    missing=set(totals)-{(row['sku'],row['delegation']) for row in stocks}
    if missing:
        raise ValueError('Hay tránsitos para artículos/delegaciones sin fila de stock en EXIT. Revisa la vista antes de calcular: '+', '.join(f'{sku}/{delegation}' for sku,delegation in sorted(missing)[:10]))
