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
