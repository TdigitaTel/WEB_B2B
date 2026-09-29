"""Lectura de pedidos pendientes desde EXIT/SQL Server."""
from datetime import datetime, timezone
from decimal import Decimal

from .erp_db import _discovered_column, _identifier, connect_sqlserver
from .erp_schema import EXIT_SALES_ORDER
from .exit_orders import ExitOrderInput, ExitOrderLineInput

HEADER_CANDIDATES = {
    "year": ("EjercicioPedido", "Ejercicio"),
    "series": ("SeriePedido", "Serie"),
    "number": ("NumeroPedido", "NumeroPedidoVenta", "Numero"),
    "customer": ("CodigoCliente", "Cliente"),
    "warehouse": ("CodigoAlmacen", "Almacen"),
    "status": ("StatusPedido",),
    "pending_pct": ("PorcentajePendiente",),
    "date": ("FechaPedido", "Fecha"),
    "reference": ("SuPedido", "ReferenciaCliente", "Referencia"),
    "notes": ("Observaciones", "Comentario", "Comentarios"),
    "subtotal": ("ImporteLiquido", "BaseImponible", "ImporteNeto"),
    "total": ("ImporteTotal", "TotalPedido", "Total"),
}
DETAIL_CANDIDATES = {
    "year": ("EjercicioPedido", "Ejercicio"),
    "series": ("SeriePedido", "Serie"),
    "number": ("NumeroPedido", "NumeroPedidoVenta", "Numero"),
    "line": ("Orden", "NumeroLinea", "Linea"),
    "sku": ("CodigoArticulo", "Articulo"),
    "description": ("DescripcionArticulo", "DescripcionLinea", "Descripcion"),
    "quantity": ("UnidadesPedidas", "Unidades", "Cantidad"),
    "unit_price": ("Precio", "PrecioVenta", "PrecioArticulo"),
    "discount_pct": ("PorcentajeDescuento1", "Descuento", "Descuento1"),
    "tax_rate": ("PorcentajeIva", "PorcentajeIVA", "IVA"),
    "line_total": ("ImporteLiquido", "ImporteNeto", "ImporteLinea"),
    "zone": ("ex_tipopedvlinkardex", "Ex_TipoPedVLinKardex"),
}
STORE_MAP = {"0": "ALM", "00": "ALM", "1": "COR", "01": "COR", "2": "FER", "02": "FER", "4": "SAN", "04": "SAN", "5": "SAX", "05": "SAX"}


def _columns(connection, table: str, candidates: dict[str, tuple[str, ...]]) -> dict[str, str | None]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=%s AND LOWER(TABLE_NAME)=LOWER(%s)",
            (EXIT_SALES_ORDER["schema"], table),
        )
        existing = {str(row["COLUMN_NAME"]).lower(): str(row["COLUMN_NAME"]) for row in cursor.fetchall()}
    return {field: next((existing[name.lower()] for name in names if name.lower() in existing), None) for field, names in candidates.items()}


def inspect_exit_order_schema() -> dict:
    with connect_sqlserver() as connection:
        return {
            "header": _columns(connection, EXIT_SALES_ORDER["header_table"], HEADER_CANDIDATES),
            "detail": _columns(connection, EXIT_SALES_ORDER["detail_table"], DETAIL_CANDIDATES),
        }


def _required(columns: dict[str, str | None], fields: tuple[str, ...], table: str):
    missing = [field for field in fields if not columns.get(field)]
    if missing:
        raise RuntimeError(f"No se pudieron identificar en {table}: {', '.join(missing)}")


def _select(alias: str, columns: dict[str, str | None], field: str) -> str:
    column = columns.get(field)
    return f"{alias}.{_discovered_column(column)} AS [{field}]" if column else f"NULL AS [{field}]"


def _key(row: dict) -> tuple[str, str, str]:
    return tuple(str(row.get(field) or "").strip() for field in ("year", "series", "number"))


def _decimal(value) -> Decimal:
    return Decimal(str(value or 0))


def fetch_pending_exit_orders(limit: int = 200) -> list[ExitOrderInput]:
    """Obtiene StatusPedido=S y PorcentajePendiente<>100, separados por KARDEX/SGA."""
    header_table = EXIT_SALES_ORDER["header_table"]
    detail_table = EXIT_SALES_ORDER["detail_table"]
    schema = _identifier(EXIT_SALES_ORDER["schema"])
    with connect_sqlserver() as connection:
        header = _columns(connection, header_table, HEADER_CANDIDATES)
        detail = _columns(connection, detail_table, DETAIL_CANDIDATES)
        _required(header, ("year", "series", "number", "customer", "warehouse", "status", "pending_pct"), header_table)
        _required(detail, ("year", "series", "number", "sku", "quantity", "zone"), detail_table)
        hs = {key: _discovered_column(value) for key, value in header.items() if value}
        ds = {key: _discovered_column(value) for key, value in detail.items() if value}
        header_fields = ("year", "series", "number", "customer", "warehouse", "date", "reference", "notes", "subtotal", "total")
        header_sql = (
            f"SELECT TOP {max(1, min(limit, 1000))} {', '.join(_select('h', header, f) for f in header_fields)} "
            f"FROM {schema}.{_identifier(header_table)} h "
            f"WHERE LTRIM(RTRIM(CONVERT(varchar(20),h.{hs['status']})))=%s "
            f"AND COALESCE(h.{hs['pending_pct']},0)<>%s "
            f"ORDER BY h.{hs['year']} DESC,h.{hs['series']} DESC,h.{hs['number']} DESC"
        )
        with connection.cursor() as cursor:
            cursor.execute(header_sql, ("S", 100))
            headers = cursor.fetchall()
        if not headers:
            return []
        wanted = {_key(row) for row in headers}
        detail_fields = ("year", "series", "number", "line", "sku", "description", "quantity", "unit_price", "discount_pct", "tax_rate", "line_total", "zone")
        join = " AND ".join(
            f"LTRIM(RTRIM(CONVERT(varchar(100),d.{ds[field]})))=LTRIM(RTRIM(CONVERT(varchar(100),h.{hs[field]})))"
            for field in ("year", "series", "number")
        )
        detail_sql = (
            f"SELECT {', '.join(_select('d', detail, f) for f in detail_fields)} "
            f"FROM {schema}.{_identifier(detail_table)} d JOIN {schema}.{_identifier(header_table)} h ON {join} "
            f"WHERE LTRIM(RTRIM(CONVERT(varchar(20),h.{hs['status']})))=%s AND COALESCE(h.{hs['pending_pct']},0)<>%s"
        )
        with connection.cursor() as cursor:
            cursor.execute(detail_sql, ("S", 100))
            detail_rows = [row for row in cursor.fetchall() if _key(row) in wanted]

    lines_by_key: dict[tuple[str, str, str], list[ExitOrderLineInput]] = {key: [] for key in wanted}
    for row in detail_rows:
        quantity = _decimal(row.get("quantity"))
        if quantity <= 0:
            continue
        zone = str(row.get("zone") or "").strip().upper()
        if zone not in {"KARDEX", "SGA"}:
            zone = "OTROS"
        lines_by_key[_key(row)].append(ExitOrderLineInput(
            sku=str(row.get("sku") or "").strip(), description=str(row.get("description") or row.get("sku") or "").strip(),
            quantity=quantity, unit_price=_decimal(row.get("unit_price")),
            discount_pct=_decimal(row.get("discount_pct")), tax_rate=_decimal(row.get("tax_rate") or 21),
            line_total=_decimal(row.get("line_total")) if row.get("line_total") is not None else None,
            fulfillment_zone=zone,
        ))
    imported_at = datetime.now(timezone.utc)
    result = []
    for row in headers:
        year, series, number = _key(row)
        external_id = f"{year}/{series}/{number}"
        raw_store = str(row.get("warehouse") or "").strip().upper()
        result.append(ExitOrderInput(
            exit_order_id=external_id, order_number=f"EXIT-{year}-{series}-{number}"[:40],
            customer_code=str(row.get("customer") or "").strip(), store_code=STORE_MAP.get(raw_store, raw_store),
            status="ENVIADO", source_updated_at=imported_at, customer_reference=str(row.get("reference") or "").strip() or None,
            notes=str(row.get("notes") or "").strip() or None, subtotal=_decimal(row.get("subtotal")),
            tax_total=max(Decimal("0"), _decimal(row.get("total"))-_decimal(row.get("subtotal"))), total=_decimal(row.get("total")),
            lines=lines_by_key.get((year, series, number), []),
        ))
    return result
