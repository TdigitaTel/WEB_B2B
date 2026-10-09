import csv

from sqlalchemy import select
from app.db import SessionLocal
from app.models import Product
from app.reclassify_materials import apply_classification


def test_reclassification_preserves_commercial_data_and_is_idempotent(tmp_path):
    path = tmp_path / 'classification.csv'
    with SessionLocal() as db:
        product = db.scalar(select(Product).limit(1))
        before = (product.short_description, product.brand_id, product.list_price,
                  product.active, product.manufacturer_reference)
        row = dict(CodigoArticulo=product.sku, Area_Categoria='ÁREA NUEVA',
                   Familia='FAMILIA NUEVA', Subfamilia_Aplicacion='SUBFAMILIA NUEVA',
                   TipoProducto='TIPO NUEVO', EstadoClasificacionWeb='CLASIFICADO',
                   PUBLICACIÓN_PROPUESTA='EXCLUIR', Material_Filtro='LATÓN')
        with path.open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(row))
            writer.writeheader(); writer.writerow(row); writer.writerow(row)
        result = apply_classification(db, path)
        db.commit()
        assert result['updated'] == 1
        assert result['source_rows'] == 2
        assert product.family == 'FAMILIA NUEVA'
        assert product.attributes['publicacion_propuesta'] == 'EXCLUIR'
        assert before == (product.short_description, product.brand_id, product.list_price,
                          product.active, product.manufacturer_reference)
        assert apply_classification(db, path) == {'already_applied': True}
