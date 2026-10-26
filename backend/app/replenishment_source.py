"""Fuentes EXIT del MVP. Exclusivamente SELECT; no usa almacenes para el stock."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from .erp_db import connect_sqlserver

DELEGATIONS = {'01':'San Diego / A Coruña','02':'Ferrol','04':'Santiago','05':'Sanxenxo'}
MAX_ARTICLES = 5000

def number(value):
    result=float(value or 0)
    if result != result or abs(result)==float('inf'):
        raise ValueError('EXIT devolvió una cantidad no finita')
    return result

def dispatch_multiple(value):
    try:
        return number(value) if value is not None else None
    except (TypeError, ValueError):
        return None

def stamp(value):
    return value.isoformat() if isinstance(value,(date,datetime)) else str(value) if value is not None else None

def read_replenishment_source(start: date, end: date, skus: list[str] | None = None):
    """Empresa 1 para ventas. La vista de stock no tiene empresa en el esquema indicado."""
    captured=datetime.now(timezone.utc).isoformat()
    if skus == []:
        return {'captured_at':captured,'company':1,'start':start.isoformat(),'end':end.isoformat(),'articles':[],'sales':[],'stocks':[]}
    if skus is not None and len(skus)>MAX_ARTICLES:
        raise ValueError('Limita el filtro a un máximo de 5.000 artículos por simulación')
    article_rows=[]; sales=[]; stocks=[]
    with connect_sqlserver() as connection, connection.cursor() as cursor:
        batches=[None] if skus is None else [skus[i:i+1000] for i in range(0,len(skus),1000)]
        for batch in batches:
            where='inactivo=0'
            params=[]
            if batch is not None:
                where+=' AND codigoarticulo IN ('+','.join(['%s']*len(batch))+')';params.extend(batch)
            cursor.execute(f'''SELECT TOP {MAX_ARTICLES+1} codigoarticulo, descripcionarticulo, EX_tipounidad,
                inactivo, fechaalta, EX_multiplo, codigoalternativo7, codigoalternativo8, codigoalternativo9, codigoalternativo10
                FROM dbo.articulos WHERE {where} ORDER BY codigoarticulo''',tuple(params))
            article_rows.extend(cursor.fetchall())
        if len(article_rows)>MAX_ARTICLES:
            raise ValueError('Hay más de 5.000 artículos. Selecciona una familia o un conjunto de códigos para esta simulación')
        articles=[]; seen=set()
        for raw in article_rows:
            row={str(k).lower():v for k,v in raw.items()}
            sku=str(row['codigoarticulo']).strip()
            if sku in seen:raise ValueError(f'Código de artículo duplicado en EXIT: {sku}')
            seen.add(sku)
            articles.append({'sku':sku,'description':str(row.get('descripcionarticulo') or sku),
                'exit_multiple':dispatch_multiple(row.get('ex_multiplo')),'unit_type':str(row.get('ex_tipounidad') or ''),'created_at':stamp(row.get('fechaalta')),
                'alternatives':{str(i):str(row.get(f'codigoalternativo{i}') or '') for i in range(7,11)}})
        codes=[row['sku'] for row in articles]
        for offset in range(0,len(codes),1000):
            batch=codes[offset:offset+1000];marks=','.join(['%s']*len(batch))
            cursor.execute(f'''SELECT avl.CodigoArticulo AS sku, avc.IdDelegacion AS delegation,
                CONVERT(date,avc.FechaAlbaran) AS day,
                SUM(CASE WHEN avl.Unidades>0 THEN avl.Unidades ELSE 0 END) AS sold,
                SUM(CASE WHEN avl.Unidades<0 THEN -avl.Unidades ELSE 0 END) AS returned
                FROM dbo.AlbaranVentaCabecera avc INNER JOIN dbo.AlbaranVentaLineas avl
                ON avc.NumeroAlbaran=avl.NumeroAlbaran AND avc.EjercicioAlbaran=avl.EjercicioAlbaran
                AND avc.CodigoEmpresa=avl.CodigoEmpresa
                WHERE avc.CodigoEmpresa=1 AND avc.FechaAlbaran>=%s AND avc.FechaAlbaran<%s
                AND avc.IdDelegacion IN ('01','02','04','05') AND avl.CodigoArticulo IN ({marks})
                GROUP BY avl.CodigoArticulo,avc.IdDelegacion,CONVERT(date,avc.FechaAlbaran)''',
                (start,end+timedelta(days=1),*batch))
            sales.extend({'sku':str(row['sku']).strip(),'delegation':str(row['delegation']).strip(),
                'day':stamp(row['day'])[:10],'sold':number(row['sold']),'returned':number(row['returned'])} for row in cursor.fetchall())
            cursor.execute(f'''SELECT CodigoArticulo AS sku, IdDelegacion AS delegation, UnidadSaldo AS stock,
                PendienteRecibir AS incoming, PendienteServir AS outgoing FROM dbo.VIS_EX_StockVentasDelegacion
                WHERE IdDelegacion IN ('00','01','02','04','05') AND CodigoArticulo IN ({marks})''',tuple(batch))
            stocks.extend({'sku':str(row['sku']).strip(),'delegation':str(row['delegation']).strip(),
                'stock':number(row['stock']),'incoming':number(row['incoming']),'outgoing':number(row['outgoing'])} for row in cursor.fetchall())
    keys=[(row['sku'],row['delegation']) for row in stocks]
    if len(keys)!=len(set(keys)):
        raise ValueError('La vista de stock devuelve más de una fila por artículo/delegación. No se sumará stock consolidado duplicado')
    return {'captured_at':datetime.now(timezone.utc).isoformat(),'extraction_started_at':captured,'company':1,'start':start.isoformat(),'end':end.isoformat(),
            'articles':articles,'sales':sales,'stocks':stocks}
