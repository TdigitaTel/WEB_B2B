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
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS erp_customer_code VARCHAR(40)",
                "CREATE INDEX IF NOT EXISTS ix_users_erp_customer_code ON users(erp_customer_code)",
                "UPDATE users u SET erp_customer_code = c.erp_id FROM customers c WHERE u.customer_id = c.id AND u.erp_customer_code IS NULL",
                "ALTER TABLE carts ADD COLUMN IF NOT EXISTS customer_code VARCHAR(40)",
                "ALTER TABLE carts ALTER COLUMN customer_id DROP NOT NULL",
                "CREATE INDEX IF NOT EXISTS ix_carts_customer_code ON carts(customer_code)",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_code VARCHAR(40)",
                "ALTER TABLE orders ALTER COLUMN customer_id DROP NOT NULL",
                "CREATE INDEX IF NOT EXISTS ix_orders_customer_code ON orders(customer_code)",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS nro_pedido_exit VARCHAR(80)",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS fecha_registro_exit TIMESTAMPTZ",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS origen_pedido VARCHAR(20) DEFAULT 'B2B' NOT NULL",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS estado_registro_exit VARCHAR(80)",
                """DO $$ BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='orders' AND column_name='exit_order_id') THEN
                        EXECUTE 'UPDATE orders SET nro_pedido_exit=exit_order_id WHERE nro_pedido_exit IS NULL AND exit_order_id IS NOT NULL';
                    END IF;
                    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='orders' AND column_name='source_updated_at') THEN
                        EXECUTE 'UPDATE orders SET fecha_registro_exit=source_updated_at WHERE fecha_registro_exit IS NULL AND nro_pedido_exit IS NOT NULL';
                    END IF;
                    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='orders' AND column_name='exit_status') THEN
                        EXECUTE 'UPDATE orders SET estado_registro_exit=exit_status WHERE estado_registro_exit IS NULL AND exit_status IS NOT NULL';
                    END IF;
                    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='orders' AND column_name='source_system') THEN
                        EXECUTE 'UPDATE orders SET origen_pedido=''EXIT'' WHERE source_system=''EXIT''';
                    END IF;
                END $$""",
                "ALTER TABLE orders ALTER COLUMN user_id DROP NOT NULL",
                "ALTER TABLE order_items ALTER COLUMN product_id DROP NOT NULL",
                "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS fulfillment_zone VARCHAR(20)",
                "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS pending_quantity NUMERIC(14,3)",
                "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS served_quantity NUMERIC(14,3)",
                "CREATE INDEX IF NOT EXISTS ix_order_items_fulfillment_zone ON order_items(fulfillment_zone)",
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_orders_nro_pedido_exit ON orders(nro_pedido_exit) WHERE nro_pedido_exit IS NOT NULL",
                "CREATE INDEX IF NOT EXISTS ix_orders_origen_pedido ON orders(origen_pedido)",
                "UPDATE orders SET origen_pedido = 'B2B' WHERE origen_pedido IS NULL OR origen_pedido NOT IN ('B2B', 'EXIT')",
                "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS customer_code VARCHAR(40)",
                "ALTER TABLE notifications ALTER COLUMN customer_id DROP NOT NULL",
                "CREATE INDEX IF NOT EXISTS ix_notifications_customer_code ON notifications(customer_code)",
                "CREATE INDEX IF NOT EXISTS ix_products_material_area_id ON products(material_area_id)",
                "CREATE INDEX IF NOT EXISTS ix_products_material_family_id ON products(material_family_id)",
                "CREATE INDEX IF NOT EXISTS ix_products_material_subfamily_id ON products(material_subfamily_id)",
                "CREATE INDEX IF NOT EXISTS ix_products_material_product_type_id ON products(material_product_type_id)",
                "CREATE INDEX IF NOT EXISTS ix_products_classification_status ON products(classification_status)",
                "CREATE INDEX IF NOT EXISTS ix_products_classification_confidence ON products(classification_confidence)",
                "CREATE INDEX IF NOT EXISTS ix_products_source_system ON products(source_system)",
                "CREATE INDEX IF NOT EXISTS ix_products_image_sha256 ON products(image_sha256)",
                "DROP INDEX IF EXISTS ux_orders_exit_order_id",
                "DROP INDEX IF EXISTS ix_orders_exit_order_id",
                "DROP INDEX IF EXISTS ix_orders_source_system",
                "DROP INDEX IF EXISTS ix_orders_authority_system",
                "ALTER TABLE orders DROP COLUMN IF EXISTS source_system",
                "ALTER TABLE orders DROP COLUMN IF EXISTS authority_system",
                "ALTER TABLE orders DROP COLUMN IF EXISTS exit_order_id",
                "ALTER TABLE orders DROP COLUMN IF EXISTS exit_status",
                "ALTER TABLE orders DROP COLUMN IF EXISTS source_created_by",
                "ALTER TABLE orders DROP COLUMN IF EXISTS kardex_completed_at",
                "ALTER TABLE orders DROP COLUMN IF EXISTS kardex_duration_seconds",
                "ALTER TABLE orders DROP COLUMN IF EXISTS sga_completed_at",
                "ALTER TABLE orders DROP COLUMN IF EXISTS sga_duration_seconds",
                "ALTER TABLE orders DROP COLUMN IF EXISTS source_updated_at",
                "ALTER TABLE orders DROP COLUMN IF EXISTS last_imported_at",
                "DROP TABLE IF EXISTS customer_addresses",
                "DROP TABLE IF EXISTS product_images",
                "DROP TABLE IF EXISTS product_relations",
                "DROP TABLE IF EXISTS inventory",
                "DROP TABLE IF EXISTS integration_cursors",
            ):
                conn.execute(text(statement))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_products_search_trgm ON products USING gin (normalized_search gin_trgm_ops)"))
    from .seed import seed
    seed()


if __name__ == "__main__":
    main()
