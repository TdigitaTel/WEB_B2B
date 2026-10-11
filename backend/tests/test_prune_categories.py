from sqlalchemy import select
from app.bootstrap import main as bootstrap
from app.db import SessionLocal
from app.models import (MaterialArea, MaterialAreaImage, CatalogAreaVisibility,
                        MaterialFamily, MaterialSubfamily, MaterialProductType, Product)
from app.prune_categories import prune_unused_categories

bootstrap()


def test_prune_removes_empty_branch_and_preserves_used_categories():
    with SessionLocal() as db:
        old = MaterialArea(code='PRUNE-OLD', name='Antigua sin materiales')
        used = MaterialArea(code='PRUNE-USED', name='Actual con materiales')
        db.add_all([old, used]); db.flush()
        old_id, used_id = old.id, used.id
        family = MaterialFamily(code='PRUNE-F', name='Familia antigua', area_id=old_id)
        db.add(family); db.flush()
        sub = MaterialSubfamily(code='PRUNE-S', name='Subfamilia antigua', family_id=family.id)
        db.add(sub); db.flush()
        kind = MaterialProductType(code='PRUNE-T', name='Tipo antiguo', subfamily_id=sub.id)
        db.add(kind)
        for area in (old, used):
            db.add(CatalogAreaVisibility(area_id=area.id, code=area.code, name=area.name, visible=False))
            db.add(MaterialAreaImage(area_id=area.id, filename='example.webp', mime_type='image/webp', image_data=b'image', sha256='test'))
        product = db.scalar(select(Product).order_by(Product.id))
        original = product.material_area_id
        product.material_area_id = used_id
        result = prune_unused_categories(db)
        assert result['areas'] >= 1
        assert db.get(MaterialArea, old_id) is None
        assert db.get(MaterialAreaImage, old_id) is None
        assert db.get(CatalogAreaVisibility, old_id) is None
        assert db.get(MaterialArea, used_id) is not None
        assert db.get(MaterialAreaImage, used_id) is not None
        assert db.get(CatalogAreaVisibility, used_id).visible is False
        assert prune_unused_categories(db) == dict(types=0, subfamilies=0, families=0, areas=0)
        # Keep the shared test database unchanged.
        db.rollback()
