"""Remove only seeded client test identities; preserve orders and operators."""
import argparse
import re
from sqlalchemy import select, update
from app.db import SessionLocal
from app.models import User, Customer, AuthSession, Cart, CartItem, Order, OrderStatusHistory, Notification, AuditEvent


def cleanup(db, apply=False):
    customers=[row for row in db.scalars(select(Customer)).all() if re.fullmatch(r'CLI\d{5}',row.erp_id or '') and re.fullmatch(r'compras\d{3,}@cliente\.test',(row.email or '').lower())]
    customer_ids=[row.id for row in customers]
    users=[row for row in db.scalars(select(User)).all() if row.role in {'CLIENTE','CLIENTE_ADMIN'} and (re.fullmatch(r'compras\d{3,}@cliente\.test',(row.email or '').lower()) or row.customer_id in customer_ids)]
    user_ids=[row.id for row in users]
    if customer_ids and db.scalar(select(User.id).where(User.customer_id.in_(customer_ids),User.id.not_in(user_ids))):
        raise RuntimeError('Hay una cuenta no demo vinculada a un cliente de prueba; revisar antes de eliminar')
    report={'apply':apply,'customers':[row.erp_id for row in customers],'client_accounts':len(users),'operators_preserved':True,'orders_preserved':True}
    if not apply:
        return report
    # Real orders and their audit history remain; detach only obsolete identity FKs.
    if user_ids:
        cart_ids=list(db.scalars(select(Cart.id).where(Cart.user_id.in_(user_ids))).all())
        for cart_item in db.scalars(select(CartItem).where(CartItem.cart_id.in_(cart_ids))).all():
            db.delete(cart_item)
        for cart in db.scalars(select(Cart).where(Cart.id.in_(cart_ids))).all():
            db.delete(cart)
        for session in db.scalars(select(AuthSession).where(AuthSession.user_id.in_(user_ids))).all():
            db.delete(session)
        for model, field in ((Order,Order.user_id),(OrderStatusHistory,OrderStatusHistory.changed_by_user_id),(Notification,Notification.user_id),(AuditEvent,AuditEvent.user_id)):
            db.execute(update(model).where(field.in_(user_ids)).values({field.key:None}))
    if customer_ids:
        for model in (Order,Notification,AuditEvent):
            db.execute(update(model).where(model.customer_id.in_(customer_ids)).values(customer_id=None))
        for cart in db.scalars(select(Cart).where(Cart.customer_id.in_(customer_ids))).all():
            cart.customer_id=None
    db.flush()
    for user in users:
        db.delete(user)
    db.flush()
    for customer in customers:
        db.delete(customer)
    db.commit()
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true',help='Aplica la limpieza; sin esta opción solo muestra la propuesta')
    args=parser.parse_args()
    with SessionLocal() as db:
        print(cleanup(db,args.apply))

if __name__=='__main__':
    main()
