"""Read-only Kardex elapsed time aggregated by sales order."""
import logging
from datetime import datetime
from .erp_db import connect_sqlserver
from .order_timeline import instant

logger = logging.getLogger(__name__)

def parse_date(value):
    if isinstance(value, datetime):
        return instant(value)
    value = str(value or '').strip()
    if not value:
        return None
    try:
        return instant(datetime.fromisoformat(value.replace('Z', '+00:00')))
    except ValueError:
        for fmt in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M:%S.%f',
                    '%Y%m%d%H%M%S', '%Y%m%d %H:%M:%S', '%d/%m/%Y'):
            try:
                return instant(datetime.strptime(value, fmt))
            except ValueError:
                pass
    logger.warning('KARDEX_DATE_INVALID value=%r', value)
    return None

def aggregate(inputs, outputs):
    starts = [stamp for row in inputs if (stamp := parse_date(row.get('FECHA_CREACION')))]
    if not starts:
        return {}
    # Each Kardex task belonging to the sales order must explicitly be complete.
    tasks = {str(row['ORDEN']).strip() for row in inputs}
    finished = set()
    ends = []
    for row in outputs:
        stamp = parse_date(row.get('FECHA_MOVIMIENTO'))
        if stamp:
            ends.append(stamp)
            if str(row.get('ORDEN_COMPLETA', '')).strip() in ('1', '-1'):
                finished.add(str(row['ORDEN']).strip())
    start = min(starts)
    closed = max(ends) if tasks and tasks <= finished and ends else None
    invalid = bool(closed and closed < start)
    return {'kardex_started_at': start, 'kardex_closed_at': closed if not invalid else None,
            'kardex_date_error': invalid}

def sales_order_number(reference):
    """EXIT references contain year/series; Kardex INFO3 contains only the number."""
    return str(reference).strip().replace("~", "/").split("/")[-1]

def fetch_kardex_timings(numbers):
    numbers = list(dict.fromkeys(str(number).strip() for number in numbers))
    result = {}
    if not numbers:
        return result
    try:
        with connect_sqlserver() as cn:
            with cn.cursor() as cur:
                for offset in range(0, len(numbers), 400):
                    batch = numbers[offset:offset + 400]
                    placeholders = ','.join(['%s'] * len(batch))
                    groups = []
                    for table, fields in (
                        ('EX_KDX_INPUT', 'INFO3, ORDEN, FECHA_CREACION'),
                        ('EX_KDX_OUTPUT', 'INFO3, ORDEN, FECHA_MOVIMIENTO, ORDEN_COMPLETA'),
                    ):
                        cur.execute(f'SELECT {fields} FROM dbo.{table} WHERE LTRIM(RTRIM(INFO3)) IN ({placeholders})', tuple(batch))
                        grouped = {}
                        for row in cur.fetchall():
                            grouped.setdefault(str(row['INFO3']).strip(), []).append(row)
                        groups.append(grouped)
                    for number in batch:
                        result[number] = aggregate(groups[0].get(number, []), groups[1].get(number, []))
    except Exception:
        logger.exception('KARDEX_TIMING_QUERY_FAILED')
    return result
