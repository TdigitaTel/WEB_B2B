from sqlalchemy import text

from .db import Base, engine
from . import models  # noqa: F401


def main():
    Base.metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            # create_all does not alter an existing MVP database. These additions are
            # intentionally idempotent so old installations can adopt the real catalogue.
            for statement in (
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS original_description TEXT",
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS material_area_id INTEGER REFERENCES material_areas(id)",
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS material_family_id INTEGER REFERENCES material_families(id)",
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS material_subfamily_id INTEGER REFERENCES material_subfamilies(id)",
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS material_product_type_id INTEGER REFERENCES material_product_types(id)",
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS classification_status VARCHAR(50)",
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS classification_reason TEXT",
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS classification_confidence VARCHAR(30)",
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS source_system VARCHAR(40)",
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS image_data BYTEA",
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS image_media_type VARCHAR(80)",
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS image_source_url TEXT",
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS image_source_provider VARCHAR(160)",
                "ALTER TABLE products ADD COLUMN IF NOT EXISTS image_sha256 VARCHAR(64)",
                "CREATE INDEX IF NOT EXISTS ix_products_material_area_id ON products(material_area_id)",
                "CREATE INDEX IF NOT EXISTS ix_products_material_family_id ON products(material_family_id)",
                "CREATE INDEX IF NOT EXISTS ix_products_material_subfamily_id ON products(material_subfamily_id)",
                "CREATE INDEX IF NOT EXISTS ix_products_material_product_type_id ON products(material_product_type_id)",
                "CREATE INDEX IF NOT EXISTS ix_products_classification_status ON products(classification_status)",
                "CREATE INDEX IF NOT EXISTS ix_products_classification_confidence ON products(classification_confidence)",
                "CREATE INDEX IF NOT EXISTS ix_products_source_system ON products(source_system)",
                "CREATE INDEX IF NOT EXISTS ix_products_image_sha256 ON products(image_sha256)",
            ):
                conn.execute(text(statement))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_products_search_trgm ON products USING gin (normalized_search gin_trgm_ops)"))
    from .seed import seed
    seed()


if __name__ == "__main__":
    main()
