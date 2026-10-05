"""Conserva las referencias locales y retira la maestra stores en una transacción."""
from sqlalchemy import String, inspect, literal, text

from .delegations import fetch_delegations, normalized_name

REFERENCES = (("orders", "store_id"), ("users", "store_id"),
              ("carts", "store_id"), ("customers", "usual_store_id"))


def match_legacy_store(store, delegations):
    by_code = [d for d in delegations if d.code == store["code"]]
    by_name = [d for d in delegations if normalized_name(d.name) == normalized_name(store["name"])]
    matches = [d for d in by_code if d in by_name] or by_code or by_name
    if len(matches) != 1:
        raise RuntimeError(
            f"No hay correspondencia única en EXIT para {store['code']} / {store['name']}. "
            "No se ha eliminado stores ni cambiado sus referencias."
        )
    return matches[0]


def migrate_delegations(engine):
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL lock_timeout = '15s'"))
        conn.execute(text("SET LOCAL statement_timeout = '120s'"))
        conn.execute(text("SELECT pg_advisory_xact_lock(20261006)"))
        inspector = inspect(conn)
        if not inspector.has_table("stores", schema="public"):
            return
        legacy = conn.execute(text("SELECT id, code, name FROM public.stores")).mappings().all()
        mapping = {}
        existing_refs = []
        for table, column in REFERENCES:
            if not inspector.has_table(table, schema="public"):
                continue
            if column not in {c["name"] for c in inspector.get_columns(table, schema="public")}:
                continue
            refs = conn.execute(text(f'SELECT DISTINCT "{column}" FROM public."{table}" WHERE "{column}" IS NOT NULL')).scalars().all()
            existing_refs.append((table, column, refs))
        referenced = {ref for _, _, refs in existing_refs for ref in refs}
        delegations = fetch_delegations() if referenced else []
        for store in legacy:
            if store["id"] in referenced:
                mapping[store["id"]] = match_legacy_store(store, delegations).id
        if referenced - set(mapping):
            raise RuntimeError("Existen referencias a stores sin ficha; migración cancelada")
        quote = conn.dialect.identifier_preparer.quote
        for table, column, refs in existing_refs:
            for fk in inspector.get_foreign_keys(table, schema="public"):
                if fk["referred_table"] == "stores" and column in fk["constrained_columns"]:
                    conn.execute(text(f'ALTER TABLE public."{table}" DROP CONSTRAINT {quote(fk["name"])}'))
            clauses = []
            for old in refs:
                target = str(literal(mapping[old], type_=String()).compile(
                    dialect=conn.dialect, compile_kwargs={"literal_binds": True}))
                clauses.append(f"WHEN {int(old)} THEN {target}")
            expression = f'CASE "{column}" {" ".join(clauses)} ELSE NULL END' if clauses else "NULL"
            conn.execute(text(
                f'ALTER TABLE public."{table}" ALTER COLUMN "{column}" TYPE varchar(40) USING {expression}'
            ))
        # DROP sin CASCADE: una dependencia desconocida cancela toda la transacción.
        conn.execute(text("DROP TABLE public.stores"))
        conn.execute(text("""CREATE TABLE IF NOT EXISTS public.schema_migrations (
            version varchar(100) PRIMARY KEY, checksum varchar(64) NOT NULL,
            applied_at timestamptz NOT NULL DEFAULT now())"""))
        conn.execute(text("""INSERT INTO public.schema_migrations(version, checksum)
            VALUES ('20261005_exit_delegations', 'exit-delegations-v1')
            ON CONFLICT (version) DO NOTHING"""))
    print("Delegaciones migradas a referencias EXIT; tabla stores retirada.")


if __name__ == "__main__":
    from .db import engine
    migrate_delegations(engine)
