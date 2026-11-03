"""Scoped origin correction explicitly confirmed by the customer on 2026-11-03.

No blanket inference from a WEB header: other lines can have been added in EXIT.
"""
import argparse
import json
from pathlib import Path

from sqlalchemy import select
from .models import Order, OrderItem
from .exit_order_key import stored_key


def confirmed_targets():
    return json.loads((Path(__file__).parent / 'data' / 'confirmed_web_line_origins.json').read_text())


def repair_confirmed_web_origins(db, apply=False, targets=None):
    from .auth import audit
    report = {'changed': [], 'skipped': []}
    for target in confirmed_targets() if targets is None else targets:
        statement = select(Order).where(Order.order_number == target['web_number'])
        order = db.scalar(statement.with_for_update() if apply else statement)
        if not order:
            continue  # Not every environment contains these historical orders.
        expected = (target['exit_year'], target['exit_series'], target['exit_number'])
        key = stored_key(order)
        reference = str(order.nro_pedido_exit or '').strip().upper().replace('~', '/').replace('-', '/')
        valid_reference = ((int(key[1]), str(key[2]).strip().upper(), str(key[3])) == expected if key else
                           reference in {target['exit_number'], f"{target['exit_year']}/{target['exit_series']}/{target['exit_number']}"})
        partial = (order.exit_order_year, order.exit_series, order.exit_order_number)
        compatible = all(value is None or str(value).strip().upper() == str(wanted).upper() for value, wanted in zip(partial, expected))
        if order.origen_pedido != 'B2B' or order.customer_code != target['customer_code'] or not valid_reference or not compatible:
            report['skipped'].append({'web_number': target['web_number'], 'reason': 'Cliente, origen o vínculo EXIT no coincide'})
            continue
        for sku in target['skus']:
            items = list(db.scalars(select(OrderItem).where(OrderItem.order_id == order.id, OrderItem.sku == sku)))
            if len(items) != 1:
                report['skipped'].append({'web_number': target['web_number'], 'sku': sku, 'reason': 'Artículo ausente o repetido; requiere revisión'})
                continue
            item = items[0]
            if item.created_in_web is True:
                continue
            change = {'web_number': order.order_number, 'sku': sku, 'line_id': item.id,
                      'previous_created_in_web': item.created_in_web, 'created_in_web': True,
                      'reason': 'Origen WEB confirmado por el usuario el 2026-11-03'}
            report['changed'].append(change)
            if apply:
                item.created_in_web = True
                audit(db, None, 'ORDER_LINE_WEB_ORIGIN_CONFIRMED', 'ORDER_ITEM', str(item.id), change)
    if apply:
        db.flush()
    return report


def main():
    parser = argparse.ArgumentParser(description='Revisar o aplicar la corrección de origen WEB confirmada')
    parser.add_argument('--apply', action='store_true', help='Guardar los cambios y su auditoría; sin esta opción solo se previsualiza')
    options = parser.parse_args()
    from .db import SessionLocal
    with SessionLocal() as db:
        report = repair_confirmed_web_origins(db, apply=options.apply)
        if options.apply:
            db.commit()
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
