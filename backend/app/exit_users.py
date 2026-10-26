"""Maestra de usuarios EXIT: CodigoUsuario, NombreCorto y Correo de MCUsuarios."""
from .erp_db import connect_sqlserver


def fetch_exit_users(query='', page=1, page_size=25, exact_code=None, exact_identity=None):
    # Campos exactos facilitados: no requiere permisos de metadatos ni busca columnas alternativas.
    expressions = {
        'code': 'LTRIM(RTRIM(CONVERT(nvarchar(200), m.CodigoUsuario)))',
        'username': 'LTRIM(RTRIM(CONVERT(nvarchar(200), m.NombreCorto)))',
        'email': 'LTRIM(RTRIM(CONVERT(nvarchar(200), m.Correo)))',
    }
    conditions = [f"NULLIF({expressions['code']}, '') IS NOT NULL"]
    params = []
    if exact_code is not None:
        conditions.append(expressions['code'] + ' = %s'); params.append(exact_code)
    if exact_identity is not None:
        conditions.append('(' + expressions['code'] + ' = %s OR ' + expressions['username'] + ' = %s)')
        params.extend([exact_identity, exact_identity])
    if query.strip():
        term = query.strip().replace('~', '~~').replace('%', '~%').replace('_', '~_').replace('[', '~[')
        conditions.append('(' + ' OR '.join(f"{value} LIKE %s ESCAPE '~'" for value in expressions.values()) + ')')
        params.extend(['%' + term + '%'] * len(expressions))
    where = ' AND '.join(conditions)
    with connect_sqlserver() as connection, connection.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) AS total FROM MCUsuarios m WHERE ' + where, tuple(params))
        total = int(cursor.fetchone()['total'])
        cursor.execute(f'''SELECT m.CodigoUsuario AS code, m.NombreCorto AS username, m.Correo AS email
            FROM MCUsuarios m WHERE {where}
            ORDER BY {expressions['code']} OFFSET %s ROWS FETCH NEXT %s ROWS ONLY''',
            tuple(params + [(page - 1) * page_size, page_size]))
        items = []
        for row in cursor.fetchall():
            item = {key: '' if row[key] is None else str(row[key]).strip() for key in expressions}
            item['username'] = item['username'] or item['code']
            item['name'] = item['username']
            items.append(item)
        if len({row['code'].casefold() for row in items}) != len(items):
            raise RuntimeError('Hay códigos repetidos en MCUsuarios; revisar su clave antes de habilitar accesos')
        return {'items': items, 'total': total}


def fetch_exit_user(code):
    rows = fetch_exit_users(exact_code=code, page_size=2)['items']
    return rows[0] if len(rows) == 1 else None
