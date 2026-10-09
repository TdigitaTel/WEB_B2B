"""Apply the reviewed classification without changing ERP or commercial data."""
import csv
import hashlib
import io
from pathlib import Path

from sqlalchemy import select

from .db import SessionLocal
from .models import CatalogAreaVisibility, MaterialImportRow, Product
from .category_import import (
    _get_or_create_area, _get_or_create_category, _get_or_create_family,
    _get_or_create_subfamily, _get_or_create_type,
)

SOURCE = 'CLASIFICACIO.xlsx/2026-10-09'
DATA = Path(__file__).resolve().parent.parent / 'data/classification_20261009.csv'


def apply_classification(db, path=DATA):
    content = Path(path).read_bytes()
    source = SOURCE + '/' + hashlib.sha256(content).hexdigest()
    if db.scalar(select(MaterialImportRow.id).where(MaterialImportRow.source_file == source).limit(1)):
        return {'already_applied': True}
    rows = list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
    products = {p.sku: p for p in db.scalars(select(Product)).all()}
    areas, families, subfamilies, types, categories = {}, {}, {}, {}, {}
    updated, missing, seen = 0, [], {}
    for number, row in enumerate(rows, 2):
        code = row['CodigoArticulo'].strip()
        hierarchy = tuple(row[key].strip() for key in (
            'Area_Categoria', 'Familia', 'Subfamilia_Aplicacion', 'TipoProducto'))
        if not code or not all(hierarchy):
            raise ValueError(f'Fila {number}: código o clasificación incompletos')
        if code in seen:
            if seen[code] != hierarchy:
                raise ValueError(f'Clasificaciones incompatibles para {code}')
            continue
        seen[code] = hierarchy
        product = products.get(code)
        if product is None:
            missing.append(code)
            continue
        area_name, family_name, subfamily_name, type_name = hierarchy
        if area_name not in areas:
            areas[area_name] = _get_or_create_area(db, area_name)[0]
        area = areas[area_name]
        if hierarchy[:2] not in families:
            families[hierarchy[:2]] = _get_or_create_family(db, area, family_name)[0]
        family = families[hierarchy[:2]]
        if hierarchy[:3] not in subfamilies:
            subfamilies[hierarchy[:3]] = _get_or_create_subfamily(db, family, area_name, subfamily_name)[0]
        subfamily = subfamilies[hierarchy[:3]]
        if hierarchy not in types:
            types[hierarchy] = _get_or_create_type(db, subfamily, hierarchy[:3], type_name)[0]
        if family_name not in categories:
            categories[family_name] = _get_or_create_category(db, family_name)
        product.material_area_id = area.id
        product.material_family_id = family.id
        product.material_subfamily_id = subfamily.id
        product.material_product_type_id = types[hierarchy].id
        product.category_id = categories[family_name].id
        product.family, product.subfamily = family_name, subfamily_name
        attributes = dict(product.attributes or {})
        for key, column in {
            'material': 'Material_Filtro', 'tipo_union': 'TipoUnion_Filtro',
            'tipo_conexion': 'Conexion_Filtro', 'medida_diametro': 'Medida_Filtro',
            'marca_clasificacion': 'Marca_Filtro', 'serie_modelo': 'Modelo_Filtro',
            'publicacion_propuesta': 'PUBLICACIÓN_PROPUESTA',
            'revision_propuesta': 'REVISIÓN_PROPUESTA',
            'incidencias_revision': 'INCIDENCIAS_REVISIÓN',
        }.items():
            attributes[key] = row.get(column, '').strip()
        product.attributes = attributes
        product.classification_status = row['EstadoClasificacionWeb'][:50]
        product.classification_reason = row.get('MOTIVO_PROPUESTA', '')
        product.normalized_search = ' '.join(filter(None, [
            code, product.short_description, product.original_description,
            product.manufacturer_reference, product.brand.name if product.brand else '',
            *hierarchy, *attributes.values(),
        ])).lower()
        db.add(MaterialImportRow(source_file=source, source_sheet='Sheet1',
                                 source_row=number, article_code=code,
                                 product_id=product.id, raw_data=row))
        updated += 1
    if missing:
        raise ValueError(f'{len(missing)} códigos no existen en la tabla de materiales: {missing[:20]}')
    for area in areas.values():
        if db.get(CatalogAreaVisibility, area.id) is None:
            db.add(CatalogAreaVisibility(area_id=area.id, code=area.code,
                                         name=area.name, visible=True))
    db.flush()
    return {'updated': updated, 'source_rows': len(rows), 'areas': len(areas),
            'families': len(families), 'subfamilies': len(subfamilies), 'types': len(types)}


def main():
    with SessionLocal() as db:
        result = apply_classification(db)
        db.commit()
        print(result)


if __name__ == '__main__':
    main()
