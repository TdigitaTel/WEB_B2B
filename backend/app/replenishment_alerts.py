"""Informative replenishment alarms from saved quantities and central physical availability."""
from math import isfinite
from sqlalchemy import case, func, or_

LABELS={'NONE':'','NO_STOCK':'Reponer · Almeiras sin disponible','INSUFFICIENT':'Reponer · Almeiras no cubre el conjunto','UNKNOWN':'Reponer · revisar disponibilidad de Almeiras'}


def finite(value):
    return value if isinstance(value,(int,float)) and isfinite(value) else None


def stock_alert_code(row):
    quantity=finite(row.get('quantity_without_multiple'))
    if quantity is None:quantity=finite(row.get('final_quantity'))
    if quantity is None or quantity<=0 or row.get('manually_excluded'):return 'NONE'
    # Own replenishment is not a transfer from Almeiras to itself: use its physical stock.
    if row.get('delegation')=='00':
        stock=finite(row.get('stock'))
        return 'UNKNOWN' if stock is None else 'NO_STOCK' if stock<=0 else 'NONE'
    available=finite(row.get('central_available'))
    if available is None:
        physical=finite(row.get('central_stock'))
        return 'NO_STOCK' if physical is not None and physical<=0 else 'UNKNOWN'
    if available<=0:return 'NO_STOCK'
    covered=row.get('central_covers_without_multiple')
    if covered is None:covered=row.get('central_can_supply')
    if covered is False or available+1e-8<quantity:return 'INSUFFICIENT'
    return 'NONE' if covered is True else 'UNKNOWN'


def with_stock_alert(row):
    code=stock_alert_code(row)
    return {**row,'stock_alert':{'code':code,'label':'Reponer Almeiras · sin stock físico' if row.get('delegation')=='00' and code=='NO_STOCK' else LABELS[code]}}


def stock_alert_expression(projected,original,delegation):
    """Old projections need only a few JSON scalars, never full histories or recalculation."""
    def numeric(key):return func.coalesce(projected[key].as_float(),original[key].as_float())
    needed=func.coalesce(numeric('quantity_without_multiple'),numeric('final_quantity'))
    available=numeric('central_available');stock=numeric('stock')
    covered=func.coalesce(projected['central_covers_without_multiple'].as_boolean(),original['central_covers_without_multiple'].as_boolean(),
        projected['central_can_supply'].as_boolean(),original['central_can_supply'].as_boolean())
    excluded=original['manually_excluded'].as_boolean().is_(True)
    fallback=case((or_(needed.is_(None),needed<=0,excluded),'NONE'),
        (delegation=='00',case((stock.is_(None),'UNKNOWN'),(stock<=0,'NO_STOCK'),else_='NONE')),
        (available.is_(None),case((numeric('central_stock')<=0,'NO_STOCK'),else_='UNKNOWN')),(available<=0,'NO_STOCK'),
        (or_(covered.is_(False),available+1e-8<needed),'INSUFFICIENT'),
        (covered.is_(True),'NONE'),else_='UNKNOWN')
    return func.coalesce(projected['stock_alert_code'].as_string(),fallback)
