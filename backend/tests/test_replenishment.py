from datetime import date,timedelta
from math import ceil,sqrt
from statistics import NormalDist
import io
import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from app.bootstrap import main as bootstrap
from app.main import app
from app.replenishment_engine import (Parameters,prepare_context,calculate_article,annotate_central,summarize,resolve_parameters)
bootstrap()


def source_for(skus=('03009',),values=None,stock=2):
    values=values if values is not None else [10]*30
    start=date(2026,1,1);end=start+timedelta(days=len(values)-1)
    return {'captured_at':'2026-02-01T10:00:00+00:00','company':1,'start':start.isoformat(),'end':end.isoformat(),
        'articles':[{'sku':sku,'description':'Material '+sku,'unit_type':'UD','created_at':'2020-01-01','area_id':1,'family_id':2,'subfamily_id':3,'type_id':4} for sku in skus],
        'sales':[{'sku':sku,'delegation':'02','day':(start+timedelta(days=i)).isoformat(),'sold':value,'returned':0} for sku in skus for i,value in enumerate(values) if value],
        'stocks':[{'sku':sku,'delegation':delegation,'stock':stock if delegation=='02' else 1000,'incoming':0,'outgoing':0} for sku in skus for delegation in ('00','02')]}


def calculate(source,temporary=None):
    context=prepare_context(source,['02'],[],temporary)
    return calculate_article(source['articles'][0],'02',context,include_daily=True)


def test_regular_formula_and_zero_days_and_pending_inventory():
    source=source_for();source['stocks'][1].update(stock=10,incoming=7,outgoing=4)
    row=calculate(source)
    assert row['daily_mean']==10 and row['daily_std']==0 and row['sales_days']==30
    assert row['inventory_position']==13
    assert row['safety_stock']==0 and row['minimum_stock']==10 and row['maximum_stock']==80
    assert row['final_quantity']==67
    assert row['calculation']['z']==pytest.approx(1.6448536269)
    sparse=calculate(source_for(values=[10 if i%2 else 0 for i in range(30)]))
    assert len(sparse['daily_sales'])==30 and sparse['daily_mean']==5
    assert sparse['method']=='PERCENTIL_EMPIRICO_INTERMITENTE'
    assert sparse['maximum_stock']==40


def test_service_level_sigma_and_constraints():
    row=calculate(source_for(values=[9,10,11]*10),{'service_level':99,'max_coverage_days':2,'multiple':7})
    expected=ceil(NormalDist().inv_cdf(.99)*row['daily_std']*sqrt(8))
    assert row['safety_stock']==expected and row['maximum_stock']==20
    assert row['final_quantity']==21
    disabled=calculate(source_for(),{'enabled':False})
    assert disabled['final_quantity']==0
    with pytest.raises(ValueError):Parameters(manual_min=5,manual_max=2)
    with pytest.raises(ValueError):Parameters(multiple=0)
    with pytest.raises(ValueError):Parameters(service_level=100)


def test_no_sales_returns_missing_and_negative_stock():
    source=source_for(values=[0]*30)
    source['sales']=[{'sku':'03009','delegation':'02','day':'2026-01-03','sold':0,'returned':12}]
    row=calculate(source)
    assert row['daily_mean']==0 and row['returns']==12 and row['final_quantity']==0
    assert 'DEVOLUCIONES_ANOMALAS' in [item['code'] for item in row['recommendations']]
    source['stocks']=[]
    row=calculate(source)
    assert row['stock'] is None and row['final_quantity']==0
    assert 'DATOS_STOCK' in [item['code'] for item in row['recommendations']]
    row=calculate(source_for(stock=-2))
    assert row['inventory_position']==-2 and row['final_quantity']==82


def test_comparables_are_low_confidence_and_not_fabricated_history():
    source=source_for(('A','B','C','TARGET'))
    source['sales']=[row for row in source['sales'] if row['sku']!='TARGET']
    context=prepare_context(source,['02'],[])
    row=calculate_article(source['articles'][-1],'02',context)
    assert row['daily_mean']==0 and row['total_demand']==0
    assert row['comparables']['count']==3 and row['minimum_stock']==10 and row['confidence']=='BAJA'
    assert row['method']=='MINIMO_ORIENTATIVO_COMPARABLES'
    assert row['final_quantity']==8
    source['articles']=source['articles'][1:]
    row=calculate_article(source['articles'][-1],'02',prepare_context(source,['02'],[]))
    assert row['comparables'] is None and row['final_quantity']==0


def test_policy_precedence_and_shared_central_shortage():
    article=source_for()['articles'][0]
    policies=[{'scope':scope,'scope_key':key,'parameters':{'review_days':value},'active':True} for scope,key,value in
        [('GLOBAL','*',8),('AREA','1',9),('FAMILY','2',10),('SUBFAMILY','3',11),('TYPE','4',12),('DELEGATION','02',13),('ARTICLE_DELEGATION','03009|02',14)]]
    parameters,rules,origins=resolve_parameters(article,'02',policies)
    assert parameters['review_days']==14 and rules[-1]=='ARTICLE_DELEGATION:03009|02'
    assert origins['review_days']==rules[-1]
    source=source_for();source['stocks'][0]['stock']=100
    row=calculate(source);second={**row,'delegation':'01','recommendations':[]}
    annotate_central([row,second],source)
    assert row['central_total_requested']==156
    assert 'CENTRAL_INSUFICIENTE' in [item['code'] for item in row['recommendations']]
    assert summarize([row,second])['units_proposed']==156


def login(email='operador@bermudez.test'):
    client=TestClient(app)
    assert client.post('/api/v1/auth/login',json={'email':email,'password':'123456'}).status_code==200
    return client


def test_api_scenarios_adjustments_compare_export_and_permissions(monkeypatch):
    import app.replenishment as module
    operator=login();client=login('compras001@cliente.test')
    assert client.get('/api/v1/store/replenishment/options').status_code==403
    raw=source_for()
    monkeypatch.setattr(module,'read_replenishment_source',lambda *args:raw)
    prefix='/api/v1/store/replenishment'
    filters={'date_from':raw['start'],'date_to':raw['end'],'delegations':['02']}
    response=operator.post(prefix+'/simulations',json={'filters':filters})
    assert response.status_code==201,response.text
    first=response.json();sid=first['id']
    assert first['summary']['units_proposed']==78
    rows=operator.get(f'{prefix}/simulations/{sid}/results').json()['items'];rid=rows[0]['id']
    baseline=operator.get(f'{prefix}/simulations/{sid}/results/{rid}').json()
    assert len(baseline['daily_sales'])==30
    recalculated=operator.post(f'{prefix}/simulations/{sid}/results/{rid}/recalculate',json={'parameters':{'review_days':1}}).json()
    assert recalculated['final_quantity']==18
    assert operator.get(f'{prefix}/simulations/{sid}/results/{rid}').json()['final_quantity']==78
    adjusted=operator.post(f'{prefix}/simulations/{sid}/results/{rid}/adjustments',json={'quantity':5,'reason':'Revisión operativa','expected_version':1})
    assert adjusted.status_code==200,adjusted.text
    result=adjusted.json();assert result['result']['calculated_quantity']==78
    assert result['result']['recommended_quantity']==78 and result['result']['adjusted_quantity']==5
    assert result['scenario']['summary']['units_proposed']==5
    assert operator.post(f'{prefix}/simulations/{sid}/results/{rid}/adjustments',json={'quantity':6,'reason':'Edición obsoleta','expected_version':1}).status_code==409
    saved=operator.patch(f'{prefix}/simulations/{sid}',json={'name':'Escenario A','expected_version':2}).json()
    assert saved['saved']
    second=operator.post(prefix+'/simulations',json={'filters':filters,'source_id':sid,'temporary_parameters':{'service_level':90,'review_days':1}}).json()
    comparison=operator.get(prefix+'/compare',params={'a':sid,'b':second['id']}).json()
    assert comparison['same_source_context'] is True
    assert comparison['differences']['units_proposed']==13
    exported=operator.get(f'{prefix}/simulations/{sid}/export.xlsx')
    book=load_workbook(io.BytesIO(exported.content));assert book.active['A2'].value=='03009' and book.active['A2'].data_type=='s'
    assert operator.put(prefix+'/policies',json={'scope':'DELEGATION','scope_key':'02','parameters':{'review_days':5}}).status_code==200
    assert operator.put(prefix+'/policies',json={'scope':'DELEGATION','scope_key':'99','parameters':{}}).status_code==422
    assert operator.get(prefix+'/simulations').json()[0]['name']=='Escenario A'


def test_source_sql_is_read_only_uses_prompt_fields_and_rejects_duplicate_stock(monkeypatch):
    from contextlib import contextmanager
    import app.replenishment_source as module
    calls=[];duplicate=False
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params=()):self.sql=sql;calls.append((sql,params))
        def fetchall(self):
            if 'FROM dbo.articulos' in self.sql:return [{'codigoarticulo':'03009','descripcionarticulo':'Material','EX_tipounidad':'UD','inactivo':0,'fechaalta':date(2020,1,1)}]
            if 'AlbaranVentaCabecera' in self.sql:return [{'sku':'03009','delegation':'02','day':date(2026,1,5),'sold':4,'returned':1}]
            rows=[{'sku':'03009','delegation':'00','stock':10,'incoming':2,'outgoing':1}]
            return rows*2 if duplicate else rows
    class Connection:
        def cursor(self):return Cursor()
    @contextmanager
    def connect():yield Connection()
    monkeypatch.setattr(module,'connect_sqlserver',connect)
    result=module.read_replenishment_source(date(2026,1,1),date(2026,1,31),['03009'])
    assert result['articles'][0]['sku']=='03009'
    assert result['sales'][0]['sold']==4 and result['sales'][0]['returned']==1
    assert len(result['stocks'])==1 and result['stocks'][0]['stock']==10
    assert all(sql.strip().upper().startswith('SELECT') for sql,params in calls)
    assert 'avc.CodigoEmpresa=avl.CodigoEmpresa' in calls[1][0]
    assert 'avc.IdDelegacion' in calls[1][0] and 'CodigoAlmacen' not in calls[2][0]
    assert calls[1][1][:2]==(date(2026,1,1),date(2026,2,1))
    duplicate=True
    with pytest.raises(ValueError,match='más de una fila'):module.read_replenishment_source(date(2026,1,1),date(2026,1,31))


def test_source_context_and_history_differences_are_disclosed(monkeypatch):
    import app.replenishment as module
    raw=source_for();monkeypatch.setattr(module,'read_replenishment_source',lambda *args:raw)
    client=login();prefix='/api/v1/store/replenishment';filters={'date_from':raw['start'],'date_to':raw['end'],'delegations':['02']}
    a=client.post(prefix+'/simulations',json={'filters':filters}).json()
    b=client.post(prefix+'/simulations',json={'filters':filters,'source_id':a['id'],'temporary_parameters':{'history_days':10}}).json()
    compared=client.get(prefix+'/compare',params={'a':a['id'],'b':b['id']}).json()
    assert compared['same_source_context'] and not compared['same_history_window']
    assert 'Contextos diferentes' in compared['notice']
    raw={**raw,'captured_at':'2026-02-02T10:00:00+00:00'}
    c=client.post(prefix+'/simulations',json={'filters':filters}).json()
    assert not client.get(prefix+'/compare',params={'a':a['id'],'b':c['id']}).json()['same_source_context']
    rows=client.get(f"{prefix}/simulations/{a['id']}/results",params={'needed_only':True,'alerts_only':True,'q':'Material','sort':'quantity'}).json()
    assert rows['total']==1 and len(rows['items'])==1
