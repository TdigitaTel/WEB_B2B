from datetime import date
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from app.bootstrap import main as bootstrap
from app.main import app
from app import main as main_module, replenishment as replenishment, replenishment_worker as worker
from app.category_visibility import UNCLASSIFIED_CODE, visible_catalog_codes
from app.db import SessionLocal
from app.models import (Product,MaterialArea,MaterialFamily,MaterialSubfamily,MaterialProductType,CatalogAreaVisibility,
    ReplenishmentJob as Job,ReplenishmentBatch as Batch,ReplenishmentScenario as Scenario,ReplenishmentResult as Result)

bootstrap()
PREFIX='/api/v1/store/replenishment'

def login(email='operador@bermudez.test'):
    client=TestClient(app)
    assert client.post('/api/v1/auth/login',json={'email':email,'password':'123456'}).status_code==200
    return client

@pytest.fixture
def materials():
    fields=('material_area_id','material_family_id','material_subfamily_id','material_product_type_id')
    with SessionLocal() as db:
        previous_jobs=set(db.scalars(select(Job.id)).all())
        products=db.scalars(select(Product).order_by(Product.id).limit(3)).all()
        old={row.id:{field:getattr(row,field) for field in fields} for row in products}
        areas=[MaterialArea(code='SCOPE-PUB',name='Familias publicadas de prueba'),MaterialArea(code='SCOPE-HID',name='Familias ocultas de prueba')]
        db.add_all(areas);db.flush()
        families=[MaterialFamily(code=f'SCOPE-F{i}',name=f'Familia alcance {i}',area_id=area.id) for i,area in enumerate(areas)]
        db.add_all(families);db.flush()
        subs=[MaterialSubfamily(code=f'SCOPE-S{i}',name=f'Subfamilia alcance {i}',family_id=row.id) for i,row in enumerate(families)]
        db.add_all(subs);db.flush()
        types=[MaterialProductType(code=f'SCOPE-T{i}',name=f'Tipo alcance {i}',subfamily_id=row.id) for i,row in enumerate(subs)]
        db.add_all(types);db.flush()
        for i in (0,1):
            for field,value in zip(fields,(areas[i].id,families[i].id,subs[i].id,types[i].id)):setattr(products[i],field,value)
            db.add(CatalogAreaVisibility(area_id=areas[i].id,code=areas[i].code,name=areas[i].name,visible=i==0))
        for field in fields:setattr(products[2],field,None)
        unclassified=db.scalar(select(MaterialArea).where(MaterialArea.code==UNCLASSIFIED_CODE))
        created=unclassified is None
        if created:
            unclassified=MaterialArea(code=UNCLASSIFIED_CODE,name='Artículos sin categoría');db.add(unclassified);db.flush()
        control=db.get(CatalogAreaVisibility,unclassified.id);control_existed=control is not None
        old_visibility=control.visible if control else None
        if control is None:
            control=CatalogAreaVisibility(area_id=unclassified.id,code=UNCLASSIFIED_CODE,name=unclassified.name);db.add(control)
        control.visible=False;db.commit()
        data={'codes':[row.sku for row in products],'ids':[row.public_id for row in products],
            'areas':[row.id for row in areas],'families':[row.id for row in families],
            'subs':[row.id for row in subs],'types':[row.id for row in types],'unclassified':unclassified.id}
    yield data
    with SessionLocal() as db:
        jobs=db.scalars(select(Job).where(Job.id.not_in(previous_jobs))).all();jobids=[row.id for row in jobs];scenarioids=[row.scenario_id for row in jobs if row.scenario_id]
        db.execute(delete(Batch).where(Batch.job_id.in_(jobids)));db.execute(delete(Result).where(Result.scenario_id.in_(scenarioids)))
        db.execute(delete(Job).where(Job.id.in_(jobids)));db.execute(delete(Scenario).where(Scenario.id.in_(scenarioids)))
        for pk,values in old.items():
            for field,value in values.items():setattr(db.get(Product,pk),field,value)
        db.flush()
        db.execute(delete(MaterialProductType).where(MaterialProductType.id.in_(data['types'])))
        db.execute(delete(MaterialSubfamily).where(MaterialSubfamily.id.in_(data['subs'])))
        db.execute(delete(MaterialFamily).where(MaterialFamily.id.in_(data['families'])))
        db.execute(delete(CatalogAreaVisibility).where(CatalogAreaVisibility.area_id.in_(data['areas'])))
        db.execute(delete(MaterialArea).where(MaterialArea.id.in_(data['areas'])))
        if control_existed:db.get(CatalogAreaVisibility,data['unclassified']).visible=old_visibility
        else:db.execute(delete(CatalogAreaVisibility).where(CatalogAreaVisibility.area_id==data['unclassified']))
        if created:db.execute(delete(MaterialArea).where(MaterialArea.id==data['unclassified']))
        db.commit()


def test_catalog_search_suggestions_favorites_and_detail_share_visibility(materials,monkeypatch):
    client=login('compras001@cliente.test');codes=materials['codes']
    monkeypatch.setattr(main_module,'fetch_customer_favorite_articles',lambda *a:[{'article_code':code,'purchased_units':1} for code in codes])
    for index,code in enumerate(codes):
        result=client.get('/api/v1/products',params={'q':code}).json()
        assert bool(result['total'])==(index==0)
        suggestions=client.get('/api/v1/search/suggestions',params={'q':code}).json()
        assert bool(suggestions)==(index==0)
        response=client.get('/api/v1/products/'+materials['ids'][index])
        assert response.status_code==(200 if index==0 else 404)
    favorites=client.get('/api/v1/catalog/favorites').json()
    assert [row['sku'] for row in favorites['items']]==[codes[0]]
    manager=login()
    assert manager.patch(f"/api/v1/store/category-visibility/{materials['areas'][1]}",json={'visible':True}).status_code==200
    assert client.get('/api/v1/products',params={'q':codes[1]}).json()['total']>0
    assert client.get('/api/v1/products/'+materials['ids'][1]).status_code==200


def test_replenishment_options_hide_all_descendants_and_restore_together(materials):
    manager=login();options=manager.get(PREFIX+'/options').json()
    for key,ids in [('areas',materials['areas']),('families',materials['families']),('subfamilies',materials['subs']),('types',materials['types'])]:
        visible={row['id'] for row in options[key]}
        assert ids[0] in visible and ids[1] not in visible
    manager.patch(f"/api/v1/store/category-visibility/{materials['areas'][1]}",json={'visible':True})
    options=manager.get(PREFIX+'/options').json()
    for key,ids in [('areas',materials['areas']),('families',materials['families']),('subfamilies',materials['subs']),('types',materials['types'])]:
        assert ids[1] in {row['id'] for row in options[key]}


@pytest.mark.parametrize('selection',['ALL','MANUAL','HIDDEN_FAMILY'])
def test_replenishment_worklist_never_bypasses_hidden_category(materials,selection):
    filters=replenishment.Filters(date_from='2026-04-01',date_to='2026-04-02',delegations=['02'])
    if selection=='MANUAL':filters.skus=materials['codes']+['EXIT-UNKNOWN']
    if selection=='HIDDEN_FAMILY':filters.family_id=materials['families'][1]
    with SessionLocal() as db:
        result=replenishment.selected_product_codes(db,filters)
        assert result is not None
        assert materials['codes'][1] not in result and materials['codes'][2] not in result and 'EXIT-UNKNOWN' not in result
        if selection!='HIDDEN_FAMILY':assert materials['codes'][0] in result
        else:assert result==[]


def test_enabled_unclassified_never_enables_a_known_hidden_category(materials):
    login().patch(f"/api/v1/store/category-visibility/{materials['unclassified']}",json={'visible':True})
    candidates=materials['codes']+['EXIT-UNKNOWN']
    with SessionLocal() as db:
        assert visible_catalog_codes(db,candidates)==[candidates[0],candidates[2],candidates[3]]
        assert visible_catalog_codes(db,None) is None
        selected=replenishment.selected_product_codes(db,replenishment.Filters(skus=candidates))
        assert selected==[candidates[0],candidates[2],candidates[3]]
        selected=replenishment.selected_product_codes(db,replenishment.Filters(area_id=materials['unclassified']))
        assert candidates[2] in selected and candidates[0] not in selected and candidates[1] not in selected


def test_background_job_filters_before_sales_queries_and_counts_only_visible(materials,monkeypatch):
    candidates=materials['codes']+['EXIT-UNKNOWN'];reads=[];enumerations=[]
    def list_codes(selected,limit,excluded_codes=None):
        enumerations.append((selected,excluded_codes))
        return [code for code in candidates if (selected is None or code in selected) and code not in (excluded_codes or [])]
    def read(start,end,codes,limit):
        reads.append(list(codes))
        return {'captured_at':'2026-04-02T12:00:00+00:00','company':1,'start':start.isoformat(),'end':end.isoformat(),
            'sales_delegations':['00','02'],'articles':[{'sku':code,'description':code,'unit_type':'UD'} for code in codes],
            'sales':[],'stocks':[{'sku':code,'delegation':delegation,'stock':0,'incoming':0,'outgoing':0} for code in codes for delegation in ('00','02')]}
    monkeypatch.setattr(worker,'list_replenishment_codes',list_codes);monkeypatch.setattr(worker,'read_replenishment_source',read)
    manager=login();body={'filters':{'date_from':'2026-04-01','date_to':'2026-04-02','delegations':['02']},'temporary_parameters':{'simple_formula':True}}
    jid=manager.post(PREFIX+'/jobs',json=body).json()['id'];worker.process_one()
    assert reads==[[candidates[0]]]
    done=manager.get(PREFIX+'/jobs/'+jid).json()
    assert done['status']=='COMPLETED' and done['total_articles']==1
    assert manager.get(f"{PREFIX}/simulations/{done['result']['id']}/results").json()['total']==1
    manager.patch(f"/api/v1/store/category-visibility/{materials['unclassified']}",json={'visible':True})
    reads.clear();jid=manager.post(PREFIX+'/jobs',json=body).json()['id'];worker.process_one()
    assert reads==[[candidates[0],candidates[2],candidates[3]]]
    assert enumerations[-1][0] is None and candidates[1] in enumerations[-1][1]
    assert manager.get(PREFIX+'/jobs/'+jid).json()['total_articles']==3


@pytest.mark.parametrize('operation',['enumerate','source'])
def test_exit_exclusion_is_parameterized_and_applied_before_count_limit(operation,monkeypatch):
    from app import replenishment_source as module
    calls=[]
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def execute(self,sql,params=()):calls.append((sql,params));self.sql=sql
        def fetchall(self):
            if 'FROM dbo.articulos' in self.sql:
                return [{'codigoarticulo':'VISIBLE','descripcionarticulo':'Material visible','replenishment_unit':'UD'}]
            return []
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def cursor(self):return Cursor()
    monkeypatch.setattr(module,'connect_sqlserver',lambda:Connection())
    excluded=["HIDDEN'CODE"]
    if operation=='enumerate':assert module.list_replenishment_codes(None,1,excluded)==['VISIBLE']
    else:assert module.read_replenishment_source(date(2026,4,1),date(2026,4,2),None,1,excluded)['articles'][0]['sku']=='VISIBLE'
    insertion=next((sql,params) for sql,params in calls if sql.startswith('INSERT INTO #HiddenArticles'))
    assert insertion[1]==("HIDDEN'CODE",) and "HIDDEN'CODE" not in insertion[0]
    master=next(sql for sql,params in calls if 'FROM dbo.articulos' in sql)
    assert 'TOP 2' in master and 'NOT EXISTS (SELECT 1 FROM #HiddenArticles' in master
