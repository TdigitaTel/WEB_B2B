"""Imprime tablas, columnas, claves y relaciones del PostgreSQL configurado."""

from sqlalchemy import inspect

from app.db import engine


def main() -> None:
    inspector = inspect(engine)
    for table in sorted(inspector.get_table_names()):
        print(f"\n[{table}]")
        pk = set((inspector.get_pk_constraint(table) or {}).get("constrained_columns") or [])
        unique_columns = {
            column
            for constraint in inspector.get_unique_constraints(table)
            for column in constraint.get("column_names") or []
        }
        foreign_keys = {
            column: f'{fk["referred_table"]}.{referred}'
            for fk in inspector.get_foreign_keys(table)
            for column, referred in zip(fk.get("constrained_columns") or [], fk.get("referred_columns") or [])
        }
        for column in inspector.get_columns(table):
            flags = []
            name = column["name"]
            if name in pk:
                flags.append("PK")
            if name in unique_columns:
                flags.append("UNIQUE")
            if name in foreign_keys:
                flags.append(f"FK->{foreign_keys[name]}")
            if not column.get("nullable", True):
                flags.append("NOT NULL")
            suffix = f' [{", ".join(flags)}]' if flags else ""
            print(f'- {name}: {column["type"]}{suffix}')


if __name__ == "__main__":
    main()
