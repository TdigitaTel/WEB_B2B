"""Operator classification: explicit selection, transactional assignment, ERP stays read-only."""
from datetime import datetime, timezone
from uuid import uuid4
import unicodedata
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .auth import audit, require_roles
from .db import get_db
from .models import MaterialArea as Area, MaterialFamily as Family, MaterialSubfamily as Subfamily, MaterialProductType as ProductType, Product, MaterialImportRow, Brand, SyncStatus
from .erp_db import fetch_catalog_articles, fetch_catalog_articles_by_codes
from .category_import import _get_or_create_brand, _get_or_create_category, _get_or_create_subfamily, _get_or_create_type
from .category_visibility import unclassified_area_ids
from .search_settings import get_search_config
from .import_materials import fake_ean

router = APIRouter(prefix='/api/v1/store/catalog-categories/manual', tags=['catalog-categories'])
operator = require_roles('ADMIN', 'OPERADOR_TIENDA')


def node(db, model, ident):
    value = db.get(model, ident)
    if not value or value.deleted_at:
        raise HTTPException(404, 'La clasificación elegida ya no existe. Actualiza la lista')
    return value


def path_for(db, product_type_id):
    kind = node(db, ProductType, product_type_id)
    sub = node(db, Subfamily, kind.subfamily_id)
    family = node(db, Family, sub.family_id)
    return node(db, Area, family.area_id), family, sub, kind


@router.get('/tree')
def tree(db: Session = Depends(get_db), user=Depends(operator)):
    return {key:[{'id':row.id,'code':row.code,'name':row.name,**({parent:getattr(row,parent)} if parent else {})}
                 for row in db.scalars(select(model).where(model.deleted_at.is_(None)).order_by(model.name,model.id))]
            for key,model,parent in [('areas',Area,None),('families',Family,'area_id'),
                                     ('subfamilies',Subfamily,'family_id'),('product_types',ProductType,'subfamily_id')]}


@router.get('/materials')
def materials(q: str = Query('', max_length=200), area_id: int | None = None, family_id: int | None = None,
              subfamily_id: int | None = None, product_type_id: int | None = None, unclassified: bool = False,
              page: int = Query(1,ge=1), page_size: int = Query(50,ge=1,le=100),
              db: Session = Depends(get_db), user=Depends(operator)):
    query = select(Product.sku)
    for field,value in [('material_area_id',area_id),('material_family_id',family_id),
                        ('material_subfamily_id',subfamily_id),('material_product_type_id',product_type_id)]:
        if value is not None:
            query = query.where(getattr(Product,field)==value)
    selected_codes = list(db.scalars(query)) if any((area_id,family_id,subfamily_id,product_type_id)) else None
    try:
        # Administrative lookup must not infer a required classification from the description.
        articles,total = fetch_catalog_articles(q,page,page_size,selected_codes,search_config=get_search_config(db),
                                               management=True,excluded_codes=(list(db.scalars(select(Product.sku).where(
                Product.material_product_type_id.is_not(None),Product.material_area_id.is_not(None),
                Product.material_family_id.is_not(None),Product.material_subfamily_id.is_not(None),
                Product.material_area_id.not_in(unclassified_area_ids(db))))) if unclassified else None))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503,'No se pudo consultar la maestra de materiales en EXIT') from None
    codes = [row['article_code'] for row in articles]
    local = {row.sku:row for row in db.scalars(select(Product).where(Product.sku.in_(codes)))}
    levels=[(Area,'material_area_id'),(Family,'material_family_id'),(Subfamily,'material_subfamily_id'),(ProductType,'material_product_type_id')]
    names={field:dict(db.execute(select(model.id,model.name).where(model.id.in_(
        {getattr(product,field) for product in local.values() if getattr(product,field)}))).all()) for model,field in levels}
    def classification(product):
        return ' / '.join(names[field].get(getattr(product,field),'—') for _,field in levels) if product else None
    return {'items':[{'code':row['article_code'],'description':row['description'],
                      'reference':row.get('manufacturer_reference'),'brand':row.get('brand_name'),
                      'classification':classification(local.get(row['article_code']))} for row in articles],
            'total':total,'page':page,'page_size':page_size}


class Assignment(BaseModel):
    model_config=ConfigDict(extra='forbid')
    codes:list[str]=Field(min_length=1,max_length=5000)
    product_type_id:int=Field(gt=0,strict=True)

    @field_validator('codes')
    @classmethod
    def valid_codes(cls,values):
        values=[value.strip() for value in values]
        if any(not value or len(value)>80 or any(ord(c)<32 for c in value) for value in values):
            raise ValueError('Hay códigos de material vacíos o no válidos')
        return list(dict.fromkeys(values))


@router.post('/assign')
def assign(data: Assignment, db: Session=Depends(get_db), user=Depends(operator)):
    area,family,sub,kind=path_for(db,data.product_type_id)
    if area.id in set(db.scalars(unclassified_area_ids(db))):
        raise HTTPException(422,'Elige una clasificación de destino completa')
    try:
        articles=fetch_catalog_articles_by_codes(data.codes,active_only=False)
    except Exception:
        raise HTTPException(503,'No se pudieron verificar los materiales en EXIT. No se ha movido ningún material') from None
    missing=[code for code in data.codes if code not in articles]
    if missing:
        raise HTTPException(409,'No se han aplicado cambios: estos materiales ya no existen en EXIT: '+', '.join(missing[:20]))
    source='MANUAL/'+uuid4().hex
    created=0
    try:
        products={row.sku:row for row in db.scalars(select(Product).where(Product.sku.in_(data.codes)).order_by(Product.sku).with_for_update())}
        category=_get_or_create_category(db,family.name[:120])
        missing_codes=[code for code in data.codes if code not in products]
        brand_cache={}
        for code in missing_codes:
            name=str(articles[code].get('brand_name') or 'SIN MARCA')[:100]
            if name not in brand_cache:brand_cache[name]=_get_or_create_brand(db,name)[0]
        for code in missing_codes:
            article=articles[code];description=article.get('description') or code
            brand=brand_cache[str(article.get('brand_name') or 'SIN MARCA')[:100]]
            products[code]=Product(sku=code,erp_id=code,ean=fake_ean(code),
                manufacturer_reference=article.get('manufacturer_reference') or '',brand_id=brand.id,
                category_id=category.id,family=family.name,subfamily=sub.name,short_description=description[:240],
                original_description=description,commercial_description=description,technical_description='',
                unit=article.get('unit') or 'UD',pack_size=1,list_price=0,tax_rate=21,attributes={},
                normalized_search='',active=True,sync_status=SyncStatus.pending,source_system='MANUAL_CLASSIFICATION')
            db.add(products[code])
        # Allocate IDs together instead of flushing every new material and rebuilding its parents.
        db.flush()
        created=len(missing_codes);new_codes=set(missing_codes)
        brand_names=dict(db.execute(select(Brand.id,Brand.name).where(Brand.id.in_({value.brand_id for value in products.values()}))).all())
        for index,code in enumerate(data.codes,1):
            product=products[code]
            previous=({key:getattr(product,key) for key in ('material_area_id','material_family_id','material_subfamily_id','material_product_type_id')} if code not in new_codes else None)
            db.add(MaterialImportRow(source_file=source,source_sheet='Manual',source_row=index,article_code=code,
                                     product_id=product.id,raw_data={'operation':'MANUAL_CLASSIFICATION','previous':previous,'product_type_id':kind.id}))
            # Rebuild the full path from the selected type. Never accept inconsistent parent IDs.
            product.material_area_id=area.id;product.material_family_id=family.id
            product.material_subfamily_id=sub.id;product.material_product_type_id=kind.id
            product.family=family.name;product.subfamily=sub.name;product.category_id=category.id
            product.classification_status='CLASIFICADO_MANUAL';product.source_system='MANUAL_CLASSIFICATION'
            product.last_sync_at=datetime.now(timezone.utc)
            product.normalized_search=' '.join(filter(None,[code,product.short_description,product.original_description,
                product.commercial_description,product.technical_description,product.manufacturer_reference,
                product.ean,brand_names.get(product.brand_id,''),area.name,family.name,sub.name,kind.name,
                *(str(value) for value in (product.attributes or {}).values())])).lower()
        audit(db,user,'MATERIALS_CLASSIFIED_MANUALLY','MATERIAL_CLASSIFICATION',source,
              {'count':len(data.codes),'created':created,'product_type_id':kind.id})
        db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'La clasificación cambió durante la operación. Actualiza la lista e inténtalo de nuevo') from None
    return {'assigned':len(data.codes),'created_products':created,'destination':' / '.join([area.name,family.name,sub.name,kind.name])}


class NodeCreate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    parent_id:int=Field(gt=0,strict=True)
    name:str=Field(min_length=1,max_length=160)

    @field_validator('name')
    @classmethod
    def clean_name(cls,value):
        value=unicodedata.normalize('NFKC',' '.join(value.split()))
        if not value or len(value)>160 or any(ord(c)<32 or ord(c)==127 for c in value):raise ValueError('Escribe un nombre válido')
        return value


def create_node(db,user,data,is_type):
    parent=node(db,Subfamily if is_type else Family,data.parent_id)
    family=node(db,Family,parent.family_id) if is_type else parent
    area=node(db,Area,family.area_id)
    if area.id in set(db.scalars(unclassified_area_ids(db))):
        raise HTTPException(422,'Elige una familia de una categoría válida')
    if db.bind.dialect.name=='postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':f'manual-classification:{is_type}:{parent.id}'})
    model=ProductType if is_type else Subfamily
    field=model.subfamily_id if is_type else model.family_id
    existing=next((row for row in db.scalars(select(model).where(field==parent.id)) if row.name.casefold()==data.name.casefold()),None)
    if existing:
        if existing.deleted_at:raise HTTPException(409,'Existe una clasificación con ese nombre que está desactivada')
        return {'id':existing.id,'name':existing.name,'created':False}
    try:
        value,_=(_get_or_create_type(db,parent,(area.name,family.name,parent.name),data.name) if is_type
                 else _get_or_create_subfamily(db,parent,area.name,data.name))
        audit(db,user,'PRODUCT_TYPE_CREATED' if is_type else 'SUBFAMILY_CREATED','MATERIAL_CLASSIFICATION',str(value.id),{'parent_id':parent.id,'name':value.name})
        db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'Ya existe una clasificación con ese nombre. Actualiza la lista') from None
    return {'id':value.id,'name':value.name,'created':True}


@router.post('/subfamilies',status_code=201)
def create_subfamily(data:NodeCreate,db:Session=Depends(get_db),user=Depends(operator)):
    return create_node(db,user,data,False)


@router.post('/product-types',status_code=201)
def create_product_type(data:NodeCreate,db:Session=Depends(get_db),user=Depends(operator)):
    return create_node(db,user,data,True)
