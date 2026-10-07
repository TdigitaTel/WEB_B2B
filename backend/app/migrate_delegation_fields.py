"""Separa empresa y delegación sin cambiar los registros existentes."""
from sqlalchemy import inspect, text


def migrate_delegation_fields(engine):
    if engine.dialect.name != 'postgresql':
        return
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL lock_timeout = '15s'"))
        conn.execute(text('SELECT pg_advisory_xact_lock(20261007)'))
        for table, old in [('orders','store_id'),('users','store_id'),('carts','store_id'),('customers','usual_store_id')]:
            inspector=inspect(conn)
            if not inspector.has_table(table):
                continue
            columns={column['name'] for column in inspector.get_columns(table)}
            if old not in columns:
                continue
            invalid=conn.execute(text(f'''SELECT count(*) FROM "{table}"
                WHERE "{old}" IS NOT NULL AND "{old}" !~ '^[0-9]+:[^:]+$' ''')).scalar_one()
            if invalid:
                raise RuntimeError(f'{table}: {invalid} referencias sin empresa:delegación válida; migración cancelada')
            conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS company_code INTEGER'))
            conn.execute(text(f'''UPDATE "{table}" SET company_code=split_part("{old}", ':', 1)::integer,
                "{old}"=split_part("{old}", ':', 2) WHERE "{old}" IS NOT NULL'''))
            conn.execute(text(f'ALTER TABLE "{table}" RENAME COLUMN "{old}" TO delegation_code'))
            conn.execute(text(f'ALTER TABLE "{table}" ADD CONSTRAINT ck_{table}_delegation_company CHECK ((delegation_code IS NULL) = (company_code IS NULL))'))

            if table == 'orders':
                conn.execute(text('ALTER TABLE orders ALTER COLUMN company_code SET NOT NULL'))
                conn.execute(text('DROP INDEX IF EXISTS ix_orders_store_created'))
                conn.execute(text('CREATE INDEX ix_orders_store_created ON orders(company_code, delegation_code, created_at)'))
