"""Delegaciones vivas de EXIT; las referencias locales no son una maestra."""
from dataclasses import dataclass
import unicodedata

from .erp_db import connect_sqlserver


@dataclass(frozen=True)
class Delegation:
    company: int
    code: str
    name: str
    address: str
    warehouse_code: str
    warehouse_name: str

    @property
    def id(self) -> str:
        return f"{self.company}:{self.code}"

    @property
    def public_id(self) -> str:
        return self.id


def fetch_delegations() -> list[Delegation]:
    with connect_sqlserver() as connection:
        cursor = connection.cursor()
        cursor.execute("""
            SELECT d.CodigoEmpresa AS company, d.IdDelegacion AS code,
                   d.Delegacion AS name,
                   d.EX_DomicilioDelegacion AS address,
                   d.CodigoAlmacen AS warehouse_code,
                   a.Almacen AS warehouse_name
            FROM dbo.delegaciones d
            LEFT JOIN dbo.almacenes a
              ON a.CodigoEmpresa = d.CodigoEmpresa
             AND a.CodigoAlmacen = d.CodigoAlmacen
            ORDER BY d.Delegacion, d.CodigoEmpresa, d.IdDelegacion
        """)
        return [Delegation(
            company=int(row["company"]), code=str(row["code"] or "").strip(),
            name=str(row["name"] or "").strip(), address=str(row["address"] or "").strip(),
            warehouse_code=str(row["warehouse_code"] or "").strip(),
            warehouse_name=str(row["warehouse_name"] or "").strip(),
        ) for row in cursor.fetchall() if str(row["code"] or "").strip()]


def resolve_delegation(reference: str | None, rows: list[Delegation] | None = None) -> Delegation | None:
    if not reference:
        return None
    rows = fetch_delegations() if rows is None else rows
    exact = [row for row in rows if row.id == str(reference)]
    matches = exact or [row for row in rows if row.code == str(reference)]
    if len(matches) > 1:
        raise ValueError("El código de delegación pertenece a varias empresas; usa empresa:delegación")
    return matches[0] if matches else None


def normalized_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return "".join(c for c in value if c.isalnum() and not unicodedata.combining(c))
