from sqlalchemy import text

from .db import Base, engine
from . import models  # noqa: F401


def main():
    from .migrate_delegations import migrate_delegations
    migrate_delegations(engine)
    from .migrate_delegation_fields import migrate_delegation_fields
    migrate_delegation_fields(engine)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO catalog_area_visibility (area_id, code, name, visible) SELECT id, code, name, true FROM material_areas WHERE true ON CONFLICT (area_id) DO NOTHING"))
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
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS parent_user_id INTEGER REFERENCES users(id)",
                "CREATE INDEX IF NOT EXISTS ix_users_parent_user_id ON users(parent_user_id)",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS access_code VARCHAR(40)",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS contact_phone VARCHAR(40)",
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_access_code ON users(access_code)",
                "UPDATE users SET access_code = 'SU-' || LPAD(id::text, GREATEST(8, LENGTH(id::text)), '0') WHERE parent_user_id IS NOT NULL AND access_code IS NULL",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS can_view_prices BOOLEAN NOT NULL DEFAULT TRUE",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS can_view_delivery_notes BOOLEAN NOT NULL DEFAULT TRUE",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS can_view_invoices BOOLEAN NOT NULL DEFAULT TRUE",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS can_manage_preferences BOOLEAN NOT NULL DEFAULT TRUE",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS own_orders_only BOOLEAN NOT NULL DEFAULT FALSE",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS principal_user_id INTEGER REFERENCES users(id)",
                "CREATE INDEX IF NOT EXISTS ix_orders_principal_user_id ON orders(principal_user_id)",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS principal_user_name VARCHAR(160)",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS creator_user_name VARCHAR(160)",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT FALSE",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS show_delivery_note_images BOOLEAN NOT NULL DEFAULT FALSE",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS show_order_images BOOLEAN NOT NULL DEFAULT FALSE",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS initial_password_expires_at TIMESTAMPTZ",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS initial_password_ciphertext TEXT",
                "CREATE INDEX IF NOT EXISTS ix_users_erp_customer_code ON users(erp_customer_code)",
                "UPDATE users u SET erp_customer_code = c.erp_id FROM customers c WHERE u.customer_id = c.id AND u.erp_customer_code IS NULL",
                "ALTER TABLE carts ADD COLUMN IF NOT EXISTS customer_code VARCHAR(40)",
                "ALTER TABLE carts ALTER COLUMN customer_id DROP NOT NULL",
                "CREATE INDEX IF NOT EXISTS ix_carts_customer_code ON carts(customer_code)",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_code VARCHAR(40)",
                "ALTER TABLE orders ALTER COLUMN customer_id DROP NOT NULL",
                "CREATE INDEX IF NOT EXISTS ix_orders_customer_code ON orders(customer_code)",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS nro_pedido_exit VARCHAR(80)",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS exit_order_year INTEGER",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS exit_series VARCHAR(100)",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS exit_order_number VARCHAR(80)",
                "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS exit_line_number VARCHAR(40)",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS fecha_registro_exit TIMESTAMPTZ",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS pickup_date DATE",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS fulfillment_method VARCHAR(20) NOT NULL DEFAULT 'PICKUP'",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_address VARCHAR(500)",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS attention_deadline_at TIMESTAMPTZ",
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS preparation_minutes_snapshot INTEGER",
                "CREATE INDEX IF NOT EXISTS ix_orders_attention_deadline_at ON orders(attention_deadline_at)",
                "ALTER TABLE pickup_settings ADD COLUMN IF NOT EXISTS schedules JSON",
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
                "ALTER TABLE order_status_history ADD COLUMN IF NOT EXISTS estado_registro_exit VARCHAR(80)",
                "ALTER TABLE order_status_history ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'WEB' NOT NULL",
                "ALTER TABLE order_status_history ALTER COLUMN changed_by_user_id DROP NOT NULL",
                """DO $$ BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='orders' AND column_name='status') THEN
                        EXECUTE $sql$UPDATE orders SET estado_registro_exit = CASE status::text
                            WHEN 'draft' THEN 'BORRADOR' WHEN 'pending' THEN 'PENDIENTE'
                            WHEN 'sent' THEN 'PENDIENTE' WHEN 'registered' THEN 'REGISTRADO'
                            WHEN 'received' THEN 'REGISTRADO' WHEN 'processing' THEN 'EN_PROCESO'
                            WHEN 'preparing' THEN 'EN_PROCESO' WHEN 'partial' THEN 'EN_PROCESO'
                            WHEN 'attended' THEN 'ATENDIDO' WHEN 'ready' THEN 'ATENDIDO'
                            WHEN 'delivered' THEN 'ENTREGADO' WHEN 'invoiced' THEN 'FACTURADO'
                            ELSE COALESCE(estado_registro_exit, 'PENDIENTE') END
                            WHERE estado_registro_exit IS NULL OR estado_registro_exit = ''$sql$;
                    END IF;
                    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='order_status_history' AND column_name='status') THEN
                        EXECUTE $sql$UPDATE order_status_history SET estado_registro_exit = CASE status::text
                            WHEN 'draft' THEN 'BORRADOR' WHEN 'pending' THEN 'PENDIENTE'
                            WHEN 'sent' THEN 'PENDIENTE' WHEN 'registered' THEN 'REGISTRADO'
                            WHEN 'received' THEN 'REGISTRADO' WHEN 'processing' THEN 'EN_PROCESO'
                            WHEN 'preparing' THEN 'EN_PROCESO' WHEN 'partial' THEN 'EN_PROCESO'
                            WHEN 'attended' THEN 'ATENDIDO' WHEN 'ready' THEN 'ATENDIDO'
                            WHEN 'delivered' THEN 'ENTREGADO' WHEN 'invoiced' THEN 'FACTURADO'
                            ELSE 'PENDIENTE' END WHERE estado_registro_exit IS NULL$sql$;
                    END IF;
                END $$""",
                "UPDATE orders SET estado_registro_exit='PENDIENTE' WHERE estado_registro_exit IS NULL OR estado_registro_exit=''",
                "ALTER TABLE orders ALTER COLUMN estado_registro_exit SET DEFAULT 'PENDIENTE'",
                "ALTER TABLE orders ALTER COLUMN estado_registro_exit SET NOT NULL",
                "UPDATE order_status_history SET estado_registro_exit='PENDIENTE' WHERE estado_registro_exit IS NULL OR estado_registro_exit=''",
                "ALTER TABLE order_status_history ALTER COLUMN estado_registro_exit SET NOT NULL",
                "DROP INDEX IF EXISTS ix_orders_store_status_created",
                "DROP INDEX IF EXISTS ix_orders_status",
                "DROP INDEX IF EXISTS ix_order_status_history_status",
                "ALTER TABLE orders DROP COLUMN IF EXISTS status",
                "ALTER TABLE order_status_history DROP COLUMN IF EXISTS status",
                "DROP TYPE IF EXISTS orderstatus",
                "CREATE INDEX IF NOT EXISTS ix_order_status_history_order_created ON order_status_history(order_id, created_at)",
                "CREATE INDEX IF NOT EXISTS ix_order_status_history_estado_registro_exit ON order_status_history(estado_registro_exit)",
                "CREATE INDEX IF NOT EXISTS ix_order_items_fulfillment_zone ON order_items(fulfillment_zone)",
                "DROP INDEX IF EXISTS ux_orders_nro_pedido_exit",
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_orders_exit_key ON orders(company_code, exit_order_year, exit_series, exit_order_number)",
                "CREATE INDEX IF NOT EXISTS ix_orders_origen_pedido ON orders(origen_pedido)",
                "CREATE INDEX IF NOT EXISTS ix_orders_estado_registro_exit ON orders(estado_registro_exit)",
                "CREATE INDEX IF NOT EXISTS ix_orders_store_created ON orders(company_code, delegation_code, created_at)",
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
                "DROP TABLE IF EXISTS delivery_notes",
                "DROP TABLE IF EXISTS invoices",
            ):
                conn.execute(text(statement))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_products_search_trgm ON products USING gin (normalized_search gin_trgm_ops)"))
    from .seed import seed
    seed()
    if engine.dialect.name == "postgresql":
        # La sustitución se realiza solo después de verificar RPA en MCusuarios.
        # Un fallo de conexión no elimina el único acceso disponible.
        import logging
        from .db import SessionLocal
        from .operator_access import provision_rpa
        from .models import OperatorAccess, User
        from sqlalchemy import select, func
        with SessionLocal() as db:
            ready = db.scalar(select(OperatorAccess).join(User, User.id == OperatorAccess.user_id).where(func.lower(User.access_code) == 'rpa'))
            if ready is None or ready.permissions.get('all_delegations') is not True:
                try:
                    provision_rpa(db)
                except Exception:
                    db.rollback()
                    logging.getLogger(__name__).warning('No se pudo trasladar el operador a RPA. Revisar MCusuarios y ejecutar scripts/provision_rpa.py; se conserva el acceso anterior.', exc_info=True)



if __name__ == "__main__":
    main()
