"""One-time initialization of existing WEB orders, never overwrites saved lines."""
import argparse
from sqlalchemy import select
from .db import SessionLocal
from .models import Order
from .line_planning import local_context,initialize_context,source


def run(apply=False):
    cursor=0;count=0
    with SessionLocal() as db:
        while True:
            orders=db.scalars(select(Order).where(Order.id>cursor,Order.origen_pedido=='B2B',Order.estado_registro_exit.notin_(['BORRADOR','ENTREGADO','FACTURADO'])).order_by(Order.id).limit(20)).all()
            if not orders:break
            cursor=orders[-1].id
            contexts=[local_context(db,order) for order in orders]
            from .models import OrderLinePlanning
            missing=[]
            for context in contexts:
                saved=db.get(OrderLinePlanning,context[0]);data=saved.lines if saved else {}
                if any(line['pending']>0 and data.get(line['line_key'],{}).get('sku')!=line['sku'] for line in context[4]):missing.append(context)
            contexts=missing
            count+=len(contexts)
            if apply and contexts:
                # Bounded groups of 20 orders; source itself splits SQL reads by 500 codes.
                codes=list(dict.fromkeys(line['sku'] for context in contexts for line in context[4] if line['pending']>0))
                sources=source(codes)
                for context in contexts:initialize_context(db,context,sources)
                db.commit()
            print(f'{count} pedidos {"inicializados" if apply else "sin planificación"}',flush=True)
    return count

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true',help='Guardar únicamente las líneas sin planificación')
    run(parser.parse_args().apply)
