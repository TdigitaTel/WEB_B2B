"""Remove classification branches that are no longer referenced by materials."""
from sqlalchemy import delete, select
from .models import (CatalogAreaVisibility, MaterialArea, MaterialAreaImage,
                     MaterialFamily, MaterialSubfamily, MaterialProductType, Product)


def prune_unused_categories(db):
    db.flush()
    removed = {}
    # Work upwards, preserving any direct product reference or surviving child.
    levels = [
        ('types', MaterialProductType, Product.material_product_type_id, None, None),
        ('subfamilies', MaterialSubfamily, Product.material_subfamily_id,
         MaterialProductType, MaterialProductType.subfamily_id),
        ('families', MaterialFamily, Product.material_family_id,
         MaterialSubfamily, MaterialSubfamily.family_id),
        ('areas', MaterialArea, Product.material_area_id,
         MaterialFamily, MaterialFamily.area_id),
    ]
    for name, model, product_column, child, child_column in levels:
        unused = select(model.id).where(~select(Product.id).where(product_column == model.id).exists())
        if child is not None:
            unused = unused.where(~select(child.id).where(child_column == model.id).exists())
        ids = list(db.scalars(unused))
        if name == 'areas' and ids:
            db.execute(delete(MaterialAreaImage).where(MaterialAreaImage.area_id.in_(ids)))
            db.execute(delete(CatalogAreaVisibility).where(CatalogAreaVisibility.area_id.in_(ids)))
        if ids:
            db.execute(delete(model).where(model.id.in_(ids)))
        removed[name] = len(ids)
    return removed
