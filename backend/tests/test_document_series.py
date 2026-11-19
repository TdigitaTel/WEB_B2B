"""Execute the real extraction join against colliding document series."""
from contextlib import contextmanager
from datetime import date
import sqlite3
from app import replenishment_source, erp_db


def test_sales_extraction_never_crosses_series_year_or_company(monkeypatch):
    database=sqlite3.connect(':memory:');database.row_factory=sqlite3.Row
    database.execute("ATTACH DATABASE ':memory:' AS dbo")
    database.execute('CREATE TABLE dbo.AlbaranVentaCabecera (CodigoEmpresa INTEGER,EjercicioAlbaran INTEGER,SerieAlbaran TEXT,NumeroAlbaran INTEGER,FechaAlbaran TEXT,IdDelegacion TEXT)')
    database.execute('CREATE TABLE dbo.AlbaranVentaLineas (CodigoEmpresa INTEGER,EjercicioAlbaran INTEGER,SerieAlbaran TEXT,NumeroAlbaran INTEGER,CodigoArticulo TEXT,Unidades REAL)')
    database.executemany('INSERT INTO dbo.AlbaranVentaCabecera VALUES (?,?,?,?,?,?)',[
        (1,2026,'A',100,'2026-01-05 10:00:00','00'),
        (1,2026,'B',100,'2026-01-06 11:00:00','02'),
        (2,2026,'A',100,'2026-01-07 12:00:00','00'),
        (1,2025,'A',100,'2025-01-05 10:00:00','00'),
        (1,2026,'',101,'2026-01-08 10:00:00','00'),
        (1,2026,'C',100,'2026-02-01 00:00:00','00')])
    database.executemany('INSERT INTO dbo.AlbaranVentaLineas VALUES (?,?,?,?,?,?)',[
        (1,2026,'A',100,'03283',10),(1,2026,'A',100,'03283',-2),
        (1,2026,'B',100,'03283',30),(1,2026,'B',100,'03283',-5),
        (2,2026,'A',100,'03283',1000),(1,2025,'A',100,'03283',2000),
        (1,2026,'',101,'03283',7),(1,2026,'C',100,'03283',5000),
        (1,2026,'B',100,'OTHER',999)])
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params=()):self.sql,self.params=sql,params
        def fetchall(self):
            if 'INFORMATION_SCHEMA' in self.sql:return [{'COLUMN_NAME':'UnidadMedida1_'}]
            if 'FROM dbo.articulos' in self.sql:return [{'codigoarticulo':'03283','descripcionarticulo':'Material','replenishment_unit':'PZ','unit_source':'UnidadMedida1_','fechaalta':date(2020,1,1)}]
            if 'FROM dbo.AlbaranVentaCabecera' in self.sql:
                # Only translate SQL Server's date conversion and bind markers;
                # execute its JOIN, filters and aggregates unchanged.
                sql=self.sql.replace('CONVERT(date,avc.FechaAlbaran)','date(avc.FechaAlbaran)').replace('%s','?')
                params=tuple(v.isoformat() if isinstance(v,date) else v for v in self.params)
                return [dict(row) for row in database.execute(sql,params)]
            return []
    class Connection:
        def cursor(self):return Cursor()
    @contextmanager
    def connect():yield Connection()
    monkeypatch.setattr(replenishment_source,'connect_sqlserver',connect)
    try:
        source=replenishment_source.read_replenishment_source(date(2026,1,1),date(2026,1,31),['03283'])
        rows={(r['delegation'],r['day']):(r['sold'],r['returned']) for r in source['sales']}
        assert rows=={('00','2026-01-05'):(10,2),('02','2026-01-06'):(30,5),('00','2026-01-08'):(7,0)}
        assert sum(r['sold']-r['returned'] for r in source['sales'])==40
    finally:database.close()


def test_customer_delivery_lines_stay_with_their_series(monkeypatch):
    calls=[]
    common={'CodigoEmpresa':1,'EjercicioAlbaran':2026,'NumeroAlbaran':100}
    headers=[{**common,'SerieAlbaran':s,'FechaAlbaran':'2026-01-05'} for s in ('A','B')]
    lines=[{**common,'SerieAlbaran':s,'CodigoArticulo':'ONLY-'+s,'Unidades':1} for s in ('A','B')]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params):self.sql=sql;calls.append(sql)
        def fetchall(self):return lines if 'WITH selected' in self.sql else headers
    class Connection:
        def cursor(self):return Cursor()
    @contextmanager
    def connect():yield Connection()
    monkeypatch.setattr(erp_db,'connect_sqlserver',connect)
    documents=erp_db.fetch_customer_delivery_notes('CLIENT')
    assert 's.SerieAlbaran=l.SerieAlbaran' in calls[1]
    assert [[item['sku'] for item in d['items']] for d in documents]==[['ONLY-A'],['ONLY-B']]


def test_invoice_tax_join_keeps_the_complete_document_key(monkeypatch):
    statements=[]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params):statements.append(sql)
        def fetchall(self):return [{'EjercicioFactura':2026,'SerieFactura':s,'NumeroFactura':100,'TaxTotal':tax} for s,tax in [('A',10),('B',25)]]
    class Connection(Cursor):
        def cursor(self):return Cursor()
    monkeypatch.setattr(erp_db,'connect_sqlserver',lambda:Connection())
    documents=erp_db.fetch_customer_invoices('CLIENT')
    for field in ('CodigoEmpresa','EjercicioFactura','SerieFactura','NumeroFactura'):
        assert f'i.{field}=f.{field}' in statements[0]
    assert [d['id'] for d in documents]==['2026~A~100','2026~B~100']
    assert [d['tax_total'] for d in documents]==[10,25]


def test_order_details_are_selected_and_grouped_by_series(monkeypatch):
    from app import exit_db
    calls=[]
    headers=[{'company':1,'year':2026,'series':s,'number':100,'customer':'CLIENT','recorded_date':date(2026,1,5)} for s in ('A','B')]
    lines=[{'year':2026,'series':s,'number':100,'sku':'ONLY-'+s,'quantity':1,'zone':'SGA'} for s in ('A','B')]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params):self.sql=sql;calls.append((sql,params))
        def fetchall(self):return lines if 'PedidoVentaLineas' in self.sql else headers
    class Connection:
        def cursor(self):return Cursor()
    @contextmanager
    def connect():yield Connection()
    monkeypatch.setattr(exit_db,'connect_sqlserver',connect)
    monkeypatch.setattr(exit_db,'_columns',lambda connection,table,candidates:{key:key for key in candidates})
    documents=exit_db.fetch_customer_exit_orders('CLIENT',date(2026,1,1),date(2026,1,31))
    sql,params=calls[1]
    assert 'd.[year]' in sql and 'd.[series]' in sql and 'd.[number]' in sql
    assert {tuple(params[i:i+3]) for i in range(0,len(params),3)}=={('2026','A','100'),('2026','B','100')}
    assert [[line.sku for line in d.lines] for d in documents]==[['ONLY-A'],['ONLY-B']]
