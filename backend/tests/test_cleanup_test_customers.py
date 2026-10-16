from sqlalchemy import select
from app.bootstrap import main as bootstrap
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import Base
from app.models import User, Customer, Order
from scripts.cleanup_test_customers import cleanup

bootstrap()


def test_cleanup_preserves_real_clients_operators_and_orders():
    engine=create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        test_customer=Customer(erp_id="CLI00001",legal_name="Demo",trade_name="Demo",tax_id="TEST",email="compras001@cliente.test",phone="",billing_address="",price_list="PROFESIONAL",discount_pct=0)
        db.add(test_customer);db.flush()
        db.add(User(email="compras001@cliente.test",full_name="Demo",role="CLIENTE_ADMIN",customer_id=test_customer.id,password_hash="unused"))
        db.add(User(email="operador@bermudez.test",full_name="Operador",role="OPERADOR_TIENDA",password_hash="unused"))
        db.commit()
        real=User(email='real-cleanup@example.com',full_name='Cliente real',role='CLIENTE_ADMIN',erp_customer_code='11511',password_hash='unused',active=True)
        db.add(real)
        order=Order(order_number='WEB-KEEP-CLEANUP',customer_id=test_customer.id,company_code=0,delegation_code='00',origen_pedido='B2B',estado_registro_exit='PENDIENTE',subtotal=0,tax_total=0,total=0)
        db.add(order);db.commit();oid=order.id
        preview=cleanup(db)
        assert 'CLI00001' in preview['customers'] and db.get(Customer,test_customer.id)
        cleanup(db,True)
        assert db.scalar(select(User).where(User.email=='real-cleanup@example.com'))
        assert db.scalar(select(User).where(User.email=='operador@bermudez.test'))
        assert db.get(Order,oid) and db.get(Order,oid).customer_id is None
        assert not db.scalar(select(Customer).where(Customer.erp_id=='CLI00001'))
        assert cleanup(db)['client_accounts']==0
