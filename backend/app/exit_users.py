"""Lectura de la maestra MCusuarios. Nunca consulta ni modifica claves de EXIT."""
from .erp_db import connect_sqlserver, _discovered_column

COLUMNS = {
    'code': ('CodigoUsuario', 'IdUsuario', 'Usuario'),
    'username': ('Usuario', 'Login', 'NombreUsuario', 'CodigoUsuario'),
    'name': ('Nombre', 'NombreCompleto', 'NombreUsuario', 'Descripcion', 'Usuario'),
}


def fetch_exit_users(query='', page=1, page_size=25, exact_code=None, exact_identity=None):
    with connect_sqlserver() as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s', ('dbo', 'MCusuarios'))
            existing = {str(row['COLUMN_NAME']).lower(): str(row['COLUMN_NAME']) for row in cursor.fetchall()}
            columns = {key: next((existing[name.lower()] for name in names if name.lower() in existing), None) for key, names in COLUMNS.items()}
            if not all(columns.values()):
                raise RuntimeError('No se identificaron código, usuario y nombre en dbo.MCusuarios; revisar el mapa de campos')
            expressions = {key: f"LTRIM(RTRIM(CONVERT(nvarchar(200), {_discovered_column(column)})))" for key, column in columns.items()}
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
            cursor.execute('SELECT COUNT(*) AS total FROM dbo.MCusuarios WHERE ' + where, tuple(params))
            total = int(cursor.fetchone()['total'])
            projection = ', '.join(f'{value} AS [{key}]' for key, value in expressions.items())
            cursor.execute(f'SELECT {projection} FROM dbo.MCusuarios WHERE {where} ORDER BY {expressions["code"]} OFFSET %s ROWS FETCH NEXT %s ROWS ONLY', tuple(params + [(page - 1) * page_size, page_size]))
            items = [{key: str(row[key] or '').strip() for key in expressions} for row in cursor.fetchall()]
            if len({row['code'].casefold() for row in items}) != len(items):
                raise RuntimeError('Hay códigos repetidos en MCusuarios; revisar su clave antes de habilitar accesos')
            return {'items': items, 'total': total}


def fetch_exit_user(code):
    rows = fetch_exit_users(exact_code=code, page_size=2)['items']
    return rows[0] if len(rows) == 1 else None
