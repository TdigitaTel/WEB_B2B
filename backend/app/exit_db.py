"""Lectura de pedidos pendientes desde EXIT/SQL Server."""
from datetime import date, datetime, time as dt_time, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal

from .erp_db import _discovered_column, _identifier, connect_sqlserver
from .erp_schema import EXIT_SALES_ORDER
from .exit_orders import ExitOrderInput, ExitOrderLineInput

HEADER_CANDIDATES = {
    "year": ("EjercicioPedido", "Ejercicio"),
    "series": ("SeriePedido", "Serie"),
    "number": ("NumeroPedido", "NumeroPedidoVenta", "Numero"),
    "customer": ("CodigoCliente", "Cliente"),
    "delegation": ("IdDelegacion",),
    "status": ("StatusPedido",),
    "pending_pct": ("PorcentajePendiente",),
    "date": ("FechaPedido", "Fecha"),
    "recorded_date": ("FechaGrabacion",),
    "recorded_time": ("HoraGrabacion",),
    "created_by": ("NombreCorto", "WebUsuario", "CodigoUsuario"),
    "updated_at": ("FechaUltimaModificacion", "FechaModificacion"),
    "reference": ("SuPedidoNumero", "SuPedido", "ReferenciaInterna", "ReferenciaCliente", "Referencia"),
    "notes": ("Observaciones", "Comentario", "Comentarios"),
    "subtotal": ("BaseImponible", "ImporteNetoLineas", "ImporteNeto"),
    "total": ("ImporteLiquido", "ImporteFactura", "ImporteTotal", "TotalPedido", "Total"),
}
DETAIL_CANDIDATES = {
    "year": ("EjercicioPedido", "Ejercicio"),
    "series": ("SeriePedido", "Serie"),
    "number": ("NumeroPedido", "NumeroPedidoVenta", "Numero"),
    "line": ("Orden", "NumeroLinea", "Linea"),
    "sku": ("CodigoArticulo", "Articulo"),
    "description": ("DescripcionArticulo", "DescripcionLinea", "Descripcion"),
    "quantity": ("Unidades", "UnidadesPedidas", "Cantidad"),
    "served_quantity": ("UnidadesServidas",),
    "pending_quantity": ("UnidadesPendientesDeServir", "UnidadesPendientesdeServir", "UnidadesPendientes", "UnidadesPendientes2_"),
    "unit_price": ("Precio", "PrecioVenta", "PrecioArticulo"),
    "discount_pct": ("PorcentajeDescuento1", "Descuento", "Descuento1"),
    "tax_rate": ("PorcentajeIva", "PorcentajeIVA", "IVA"),
    "line_total": ("ImporteLiquido", "ImporteNeto", "ImporteLinea"),
    "zone": ("ex_tipopedvlinkardex", "Ex_TipoPedVLinKardex"),
}

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
        result = {
            "resolved_header": _columns(connection, EXIT_SALES_ORDER["header_table"], HEADER_CANDIDATES),
            "resolved_detail": _columns(connection, EXIT_SALES_ORDER["detail_table"], DETAIL_CANDIDATES),
        }
        with connection.cursor() as cursor:
            for label, table in (("header", EXIT_SALES_ORDER["header_table"]), ("detail", EXIT_SALES_ORDER["detail_table"])):
                cursor.execute(
                    "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA=%s AND LOWER(TABLE_NAME)=LOWER(%s) ORDER BY ORDINAL_POSITION",
                    (EXIT_SALES_ORDER["schema"], table),
                )
                result[f"raw_{label}_columns"] = cursor.fetchall()
            cursor.execute(
                "SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE FROM INFORMATION_SCHEMA.TABLES "
                "WHERE LOWER(TABLE_NAME) LIKE %s ORDER BY TABLE_SCHEMA, TABLE_NAME",
                ("pedidoventa%",),
            )
            result["available_pedido_venta_tables"] = cursor.fetchall()
        return result


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



def _exit_datetime(date_value, time_value=None) -> datetime:
    if isinstance(date_value, datetime):
        base = date_value
    elif isinstance(date_value, date):
        base = datetime.combine(date_value, dt_time.min)
    else:
        base = datetime.now()
    hour = minute = second = 0
    if time_value is not None:
        if isinstance(time_value, datetime):
            hour, minute, second = time_value.hour, time_value.minute, time_value.second
        elif isinstance(time_value, dt_time):
            hour, minute, second = time_value.hour, time_value.minute, time_value.second
        else:
            raw = Decimal(str(time_value or 0))
            if Decimal("0") < raw < Decimal("1"):
                seconds = int(raw * Decimal("86400"))
                hour, remainder = divmod(seconds, 3600)
                minute, second = divmod(remainder, 60)
            else:
                digits = str(abs(int(raw))).zfill(6)[-6:]
                hour, minute, second = int(digits[:2]), int(digits[2:4]), int(digits[4:6])
                if hour > 23 or minute > 59 or second > 59:
                    hour = minute = second = 0
    return base.replace(hour=hour, minute=minute, second=second, microsecond=0, tzinfo=ZoneInfo("Europe/Madrid"))

def fetch_exit_orders_live(view: str = "active_kardex", date_from: date | None = None,
                           date_to: date | None = None, limit: int = 500) -> list[ExitOrderInput]:
    """Obtiene pedidos recientes de la delegación 00 con todas sus líneas.

    El nombre se conserva por compatibilidad con el demonio. La bandeja operativa
    decide qué pedidos siguen pendientes; la proyección histórica también necesita
    los pedidos servidos para enseñar su detalle completo al cliente.
    """
    header_table = EXIT_SALES_ORDER["header_table"]
    detail_table = EXIT_SALES_ORDER["detail_table"]
    schema = _identifier(EXIT_SALES_ORDER["schema"])
    with connect_sqlserver() as connection:
        header = _columns(connection, header_table, HEADER_CANDIDATES)
        detail = _columns(connection, detail_table, DETAIL_CANDIDATES)
        _required(header, ("year", "series", "number", "customer", "delegation", "status"), header_table)
        _required(detail, ("year", "series", "number", "sku", "quantity", "zone"), detail_table)
        hs = {key: _discovered_column(value) for key, value in header.items() if value}
        ds = {key: _discovered_column(value) for key, value in detail.items() if value}
        header_fields = ("year", "series", "number", "customer", "delegation", "status", "date", "recorded_date", "recorded_time", "created_by", "updated_at", "reference", "notes", "subtotal", "total")
        header_where = [f"LTRIM(RTRIM(CONVERT(varchar(20),h.{hs['delegation']})))=%s"]
        header_parameters: list = ["00"]
        if view == "attended":
            _required(header, ("recorded_date",), header_table)
            start = date_from or datetime.now(ZoneInfo("Europe/Madrid")).date()
            end = date_to or start
            header_where.extend((
                f"UPPER(LTRIM(RTRIM(CONVERT(varchar(20),h.{hs['status']}))))=%s",
                f"CONVERT(date,h.{hs['recorded_date']}) BETWEEN %s AND %s",
            ))
            header_parameters.extend(("S", start, end))
        else:
            header_where.append(
                f"COALESCE(UPPER(LTRIM(RTRIM(CONVERT(varchar(20),h.{hs['status']})))),'')<>%s"
            )
            header_parameters.append("S")
        header_sql = (
            f"SELECT TOP {max(1, min(limit, 1000))} {', '.join(_select('h', header, f) for f in header_fields)} "
            f"FROM {schema}.{_identifier(header_table)} h "
            f"WHERE {' AND '.join(header_where)} "
            f"ORDER BY h.{hs['year']} DESC,h.{hs['series']} DESC,h.{hs['number']} DESC"
        )
        with connection.cursor() as cursor:
            cursor.execute(header_sql, tuple(header_parameters))
            headers = cursor.fetchall()
        if view == "attended":
            headers = [row for row in headers if start <= _exit_datetime(
                row.get("recorded_date") or row.get("date"), row.get("recorded_time")
            ).date() <= end]
        else:
            headers = [row for row in headers if str(row.get("status") or "").strip().upper() != "S"]
        if not headers:
            return []
        wanted = {_key(row) for row in headers}
        detail_fields = ("year", "series", "number", "line", "sku", "description", "quantity", "served_quantity", "pending_quantity", "unit_price", "discount_pct", "tax_rate", "line_total", "zone")
        detail_rows = []
        wanted_list = list(wanted)
        for start in range(0, len(wanted_list), 200):
            batch = wanted_list[start:start + 200]
            conditions = []
            parameters = []
            for year, series, number in batch:
                conditions.append("(" + " AND ".join(
                    f"LTRIM(RTRIM(CONVERT(varchar(100),d.{ds[field]})))=%s"
                    for field in ("year", "series", "number")
                ) + ")")
                parameters.extend((year, series, number))
            detail_sql = (
                f"SELECT {', '.join(_select('d', detail, f) for f in detail_fields)} "
                f"FROM {schema}.{_identifier(detail_table)} d WHERE {' OR '.join(conditions)}"
            )
            with connection.cursor() as cursor:
                cursor.execute(detail_sql, tuple(parameters))
                detail_rows.extend(cursor.fetchall())

    lines_by_key: dict[tuple[str, str, str], list[ExitOrderLineInput]] = {key: [] for key in wanted}
    for row in detail_rows:
        quantity = _decimal(row.get("quantity"))
        if quantity <= 0:
            continue
        served_quantity = (_decimal(row.get("served_quantity"))
                           if row.get("served_quantity") is not None else None)
        pending_quantity = (_decimal(row.get("pending_quantity"))
                            if row.get("pending_quantity") is not None else None)
        if pending_quantity is None and served_quantity is not None:
            pending_quantity = max(Decimal("0"), quantity - served_quantity)
        zone = str(row.get("zone") or "").strip().upper()
        if zone != "KARDEX":
            zone = "SGA"
        lines_by_key[_key(row)].append(ExitOrderLineInput(
            sku=str(row.get("sku") or "").strip(), description=str(row.get("description") or row.get("sku") or "").strip(),
            quantity=quantity, served_quantity=served_quantity,
            pending_quantity=pending_quantity if pending_quantity is not None else quantity,
            unit_price=_decimal(row.get("unit_price")),
            discount_pct=_decimal(row.get("discount_pct")), tax_rate=_decimal(row.get("tax_rate") or 21),
            line_total=_decimal(row.get("line_total")) if row.get("line_total") is not None else None,
            fulfillment_zone=zone,
        ))
    imported_at = datetime.now(timezone.utc)
    result = []
    for row in headers:
        year, series, number = _key(row)
        external_id = f"{year}/{series}/{number}"
        recorded_at = _exit_datetime(row.get("recorded_date") or row.get("date"), row.get("recorded_time"))
        updated_at = row.get("updated_at")
        if isinstance(updated_at, datetime):
            updated_at = updated_at.replace(tzinfo=ZoneInfo("Europe/Madrid"))
        else:
            updated_at = imported_at
        source_status = str(row.get("status") or "").strip().upper()
        local_status = "ENTREGADO" if source_status == "S" else "ENVIADO"
        result.append(ExitOrderInput(
            exit_order_id=external_id, order_number=f"EXIT-{year}-{series}-{number}"[:40],
            customer_code=str(row.get("customer") or "").strip(), store_code="ALM",
            status=local_status, source_status=source_status, source_created_by=str(row.get("created_by") or "").strip() or None,
            source_updated_at=updated_at, recorded_at=recorded_at, customer_reference=str(row.get("reference") or "").strip() or None,
            notes=str(row.get("notes") or "").strip() or None, subtotal=_decimal(row.get("subtotal")),
            tax_total=max(Decimal("0"), _decimal(row.get("total"))-_decimal(row.get("subtotal"))), total=_decimal(row.get("total")),
            lines=lines_by_key.get((year, series, number), []),
        ))
    if view in {"active_kardex", "active_sga"}:
        zone = "KARDEX" if view == "active_kardex" else "SGA"
        result = [order for order in result if any(
            line.fulfillment_zone == zone and
            (line.served_quantity if line.served_quantity is not None
             else max(Decimal("0"), line.quantity - (line.pending_quantity or line.quantity))) < line.quantity
            for line in order.lines
        )]
    return result


def fetch_pending_exit_orders(limit: int = 200) -> list[ExitOrderInput]:
    """Compatibilidad temporal para utilidades antiguas; el tablero usa consulta directa."""
    return fetch_exit_orders_live("active_kardex", limit=limit)
