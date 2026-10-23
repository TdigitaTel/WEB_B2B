from contextlib import contextmanager
from fastapi.testclient import TestClient
from app import erp_db
from app.main import app
from app.bootstrap import main as bootstrap
bootstrap()


def test_brand_filter_is_sql_predicate_scoped_by_company(monkeypatch):
    monkeypatch.setattr(erp_db,'_brand_columns',lambda connection:{'code':'Marca','name':'DescripcionMarca','internet_b2b':'InternetB2B','company':'CodigoEmpresa'})
    sql=erp_db._brand_catalog_condition(None,{'brand_filter_code':'Marca','brand_code':'CodigoMarca','company':'CodigoEmpresa'})
    assert 'NOT EXISTS' in sql and '[dbo].[marcas]' in sql
    assert 'm.[Marca] = a.[Marca]' in sql
    assert 'm.[CodigoEmpresa] = a.[CodigoEmpresa]' in sql
    assert 'm.[InternetB2B] = -1' in sql
    sql=erp_db._brand_catalog_condition(None,{'brand_code':'CodigoMarca'})
    assert 'm.[Marca] = a.[CodigoMarca]' in sql and 'a.[CodigoEmpresa]' not in sql


def test_brand_view_returns_original_flag_and_visibility(monkeypatch):
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params=()):self.schema='INFORMATION_SCHEMA' in sql
        def fetchall(self):
            if self.schema:return [{'COLUMN_NAME':name} for name in ['CodigoMarca','DescripcionMarca','InternetB2B']]
            return [{'code':'001','name':'Marca visible','company':None,'internet_b2b':0},
                    {'code':'002','name':'Marca oculta','company':None,'internet_b2b':-1}]
    class Connection:
        def cursor(self):return Cursor()
    @contextmanager
    def connect():yield Connection()
    monkeypatch.setattr(erp_db,'connect_sqlserver',connect)
    rows=erp_db.fetch_catalog_brands()
    assert [(row['code'],row['internet_b2b'],row['visible']) for row in rows]==[('001',0,True),('002',-1,False)]


def test_brand_view_is_operator_only(monkeypatch):
    from app import main as module
    monkeypatch.setattr(module,'fetch_catalog_brands',lambda:[{'code':'A','name':'Marca','internet_b2b':-1,'visible':False,'company':0}])
    client=TestClient(app)
    client.post('/api/v1/auth/login',json={'email':'compras001@cliente.test','password':'123456'})
    assert client.get('/api/v1/store/catalog-brands').status_code==403
    client.post('/api/v1/auth/login',json={'email':'operador@bermudez.test','password':'123456'})
    assert client.get('/api/v1/store/catalog-brands').json()[0]['visible'] is False


def test_brand_predicate_applies_before_count_and_page_and_active_code_reads(monkeypatch):
    statements=[]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params=()):statements.append(sql)
        def fetchone(self):return {'total':0}
        def fetchall(self):return []
    class Connection:
        def cursor(self):return Cursor()
    @contextmanager
    def connect():yield Connection()
    from app.erp_schema import ARTICLE
    columns={key:None for key in ARTICLE['columns']}
    columns.update(code='CodigoArticulo',brand_code='Marca',brand_filter_code='Marca')
    monkeypatch.setattr(erp_db,'connect_sqlserver',connect)
    monkeypatch.setattr(erp_db,'_article_columns',lambda conn:columns)
    monkeypatch.setattr(erp_db,'_brand_columns',lambda conn:{'code':'Marca','name':None,'internet_b2b':'InternetB2B','company':None})
    erp_db.fetch_catalog_articles('laton')
    selections=[sql for sql in statements if sql.startswith('SELECT')]
    assert len(selections)==2
    assert all('NOT EXISTS' in sql and 'm.[InternetB2B] = -1' in sql for sql in selections)
    assert 'COUNT_BIG' in selections[0] and 'OFFSET' in selections[1]
    statements.clear()
    erp_db.fetch_catalog_articles_by_codes(['00001'])
    assert 'm.[InternetB2B] = -1' in statements[-1]
    statements.clear()
    erp_db.fetch_catalog_articles_by_codes(['00001'],active_only=False)
    assert 'InternetB2B' not in statements[-1]
