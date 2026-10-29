"""Permisos de opciones para operadores, comprobados en cada petición."""
from fastapi import HTTPException
from .models import OperatorAccess

MODULES = {'orders': 'Pedidos', 'replenishment': 'Reposición', 'settings': 'Parámetros',
           'customers': 'Accesos de clientes', 'categories': 'Categorías e imágenes', 'users': 'Accesos de usuarios', 'all_delegations': 'Operar en todas las delegaciones'}


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
    if path == '/api/v1/store/sales-order-series/active' and method == 'GET':
        allowed=permissions_for(user,db)
        if not (allowed.get('orders') or allowed.get('settings')):
            raise HTTPException(403,'No tienes permiso para consultar series de pedidos')
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
        ('/api/v1/store/product-type-synonyms', 'settings'),
        ('/api/v1/store/sales-order-series', 'settings'),
        ('/api/v1/store/line-planning-settings', 'settings'),
        ('/api/v1/store/catalog-brands', 'settings'),
    ):
        if path == prefix or path.startswith(prefix + '/'):
            module = key; break
    if (path == '/api/v1/pickup-settings' and method != 'GET') or (path.startswith('/api/v1/login-appearance') and method != 'GET') or (path.startswith('/api/v1/home-carousel') and method != 'GET'):
        module = 'settings'
    if module and not permissions_for(user, db).get(module):
        raise HTTPException(403, 'No tienes permiso para acceder a ' + MODULES[module])


def can_operate_delegation(user, db, company, delegation):
    if user.role == 'ADMIN':
        return True
    if user.role != 'OPERADOR_TIENDA':
        return False
    access = db.get(OperatorAccess, user.id)
    return bool(access and (access.permissions.get('all_delegations') is True or
        f'{company}:{delegation}' in access.permissions.get('delegation_ids', []))) or (user.company_code, user.delegation_code) == (company, delegation)


def delegation_scope(user, db):
    if user.role == 'ADMIN':return None
    access = db.get(OperatorAccess, user.id)
    if access and access.permissions.get('all_delegations') is True:return None
    ids = set(access.permissions.get('delegation_ids', [])) if access else set()
    if user.company_code is not None and user.delegation_code is not None:
        ids.add(f'{user.company_code}:{user.delegation_code}')
    return [tuple(value.split(':', 1)) for value in ids]
