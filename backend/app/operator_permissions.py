"""Permisos de opciones para operadores, comprobados en cada petición."""
from fastapi import HTTPException
from .models import OperatorAccess

MODULES = {'orders': 'Pedidos', 'replenishment': 'Reposición', 'settings': 'Parámetros',
           'customers': 'Accesos de clientes', 'categories': 'Categorías e imágenes', 'users': 'Accesos de usuarios'}


def permissions_for(user, db):
    if user.role not in {'ADMIN', 'OPERADOR_TIENDA'}:
        return {}
    if user.role == 'ADMIN':
        return dict.fromkeys(MODULES, True)
    access = db.get(OperatorAccess, user.id)
    # Compatibilidad mientras se trasladan cuentas existentes; las cuentas nuevas
    # tienen siempre un registro y deniegan por defecto los módulos no asignados.
    if access is None:
        return dict.fromkeys(MODULES, True)
    return {key: access.permissions.get(key) is True for key in MODULES}


def check_operator_path(user, db, path, method):
    if user.role not in {'OPERADOR_TIENDA', 'ADMIN'}:
        return
    module = None
    for prefix, key in (
        ('/api/v1/store/operator-access', 'users'),
        ('/api/v1/store/orders', 'orders'),
        ('/api/v1/store/replenishment', 'replenishment'),
        ('/api/v1/store/customer-access', 'customers'),
        ('/api/v1/store/catalog-categories', 'categories'),
        ('/api/v1/store/category-visibility', 'categories'),
        ('/api/v1/store/catalog-images', 'categories'),
        ('/api/v1/store/search-settings', 'settings'),
        ('/api/v1/store/catalog-brands', 'settings'),
    ):
        if path == prefix or path.startswith(prefix + '/'):
            module = key; break
    if (path == '/api/v1/pickup-settings' and method != 'GET') or (path.startswith('/api/v1/login-appearance') and method != 'GET'):
        module = 'settings'
    if module and not permissions_for(user, db).get(module):
        raise HTTPException(403, 'No tienes permiso para acceder a ' + MODULES[module])
