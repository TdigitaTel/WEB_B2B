from contextlib import contextmanager
from app import erp_db

def test_delivery_lines_show_delegation_description(monkeypatch):
    statements=[]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params):statements.append(sql)
        def fetchall(self):
            common={'EjercicioAlbaran':2026,'SerieAlbaran':'AL','NumeroAlbaran':123}
            if len(statements)==1:return [{**common,'FechaAlbaran':'2026-10-11','IdDelegacion':'00','DelegationName':'Almeiras'}]
            return [{**common,'CodigoAlmacen':'99','DispatchDelegation':'Almeiras'}]
    class Connection:
        def cursor(self):return Cursor()
    @contextmanager
    def connect():yield Connection()
    monkeypatch.setattr(erp_db,'connect_sqlserver',connect)
    rows=erp_db.fetch_customer_delivery_notes('83023')
    assert rows[0]['store_name']=='Almeiras'
    assert rows[0]['items'][0]['dispatch_delegation']=='Almeiras'
    assert 'd.CodigoEmpresa=l.CodigoEmpresa' in statements[1]
    assert 'd.IdDelegacion=s.IdDelegacion' in statements[1]


def test_delivery_line_uses_exact_exit_price_discount_net_and_total(monkeypatch):
    statements=[]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params):statements.append(sql)
        def fetchall(self):
            common={'EjercicioAlbaran':2026,'SerieAlbaran':'AL','NumeroAlbaran':456}
            if len(statements)==1:return [{**common,'FechaAlbaran':'2026-10-22'}]
            return [{**common,'Orden':1,'Precio':123.45,'Descuento':12.5,'ImporteNeto':84.25,'BaseImponible':999,'ImporteLiquido':101.94},
                    {**common,'Orden':2,'Precio':10,'Descuento':100,'ImporteNeto':0,'BaseImponible':999,'ImporteLiquido':0}]
    class Connection:
        def cursor(self):return Cursor()
    @contextmanager
    def connect():yield Connection()
    monkeypatch.setattr(erp_db,'connect_sqlserver',connect)
    items=erp_db.fetch_customer_delivery_notes('83023')[0]['items']
    assert 'l.[%Descuento] AS Descuento' in statements[1]
    assert items[0]['unit_price']==123.45
    assert items[0]['discount_pct']==12.5
    assert items[0]['net_amount']==84.25 and items[0]['total']==101.94
    assert items[1]['discount_pct']==100 and items[1]['net_amount']==0 and items[1]['total']==0
