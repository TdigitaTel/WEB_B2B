"""Accesos web para usuarios de MCusuarios. Credenciales independientes de EXIT."""
from datetime import datetime, timedelta, timezone
import secrets
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, func, update
from sqlalchemy.exc import IntegrityError
from .auth import audit, hash_password, require_roles
from .config import settings
from .db import get_db
from .models import User, OperatorAccess, AuthSession, CustomerQrAccess
from .exit_users import fetch_exit_users, fetch_exit_user
from .operator_permissions import MODULES
from .delegations import fetch_delegations

router = APIRouter(prefix='/api/v1/store/operator-access', tags=['Accesos de usuarios'])
manager = require_roles('ADMIN', 'OPERADOR_TIENDA')
logger = logging.getLogger(__name__)

class AccessIn(BaseModel):
    code: str = Field(min_length=1, max_length=200)
    active: bool = True
    company_code: int
    delegation_code: str = Field(min_length=1, max_length=40)
    permissions: dict[str, bool]
    delegation_ids: list[str] = Field(default_factory=list, max_length=200)

    @field_validator('permissions')
    @classmethod
    def valid_permissions(cls, value):
        if set(value) - set(MODULES):
            raise ValueError('Opción de permisos desconocida')
        if not any(value.values()):
            raise ValueError('Selecciona al menos una opción de la web')
        return {key: value.get(key, False) for key in MODULES}

class PasswordIn(BaseModel):
    code: str = Field(min_length=1, max_length=200)
    password: str | None = Field(None, min_length=6, max_length=200)


def lookup(code):
    try:
        row = fetch_exit_user(code.strip())
    except Exception as exc:
        logger.exception('Error consultando CodigoUsuario, NombreCorto y Correo de MCUsuarios')
        raise HTTPException(503, 'No se pudo consultar MCUsuarios de EXIT (CodigoUsuario, NombreCorto, Correo). Revisa la conexión y el registro de la API.') from exc
    if not row:
        raise HTTPException(404, 'El usuario no existe o su código no es único en MCusuarios')
    return row


def revoke(db, account):
    db.execute(update(AuthSession).where(AuthSession.user_id == account.id).values(revoked=True))
    db.execute(update(CustomerQrAccess).where(CustomerQrAccess.user_id == account.id).values(active=False))


def linked(db, code):
    return db.scalar(select(OperatorAccess).where(func.lower(OperatorAccess.exit_code) == code.strip().lower()).with_for_update())


def user_payload(source, account=None, access=None):
    return {**source, 'configured': access is not None, 'enabled': bool(account and account.active), 'login': account.access_code or account.email if account else source['username'],
            'company_code': account.company_code if account else None, 'delegation_code': account.delegation_code if account else None,
            'permissions': {key: access.permissions.get(key) is True for key in MODULES} if access else dict.fromkeys(MODULES, False),
            'delegation_ids': access.permissions.get('delegation_ids', []) if access else [],
            'must_change_password': bool(account and account.must_change_password)}


def commit(db):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, 'El código o el usuario de acceso ya está asignado. Actualiza la lista.') from exc


@router.get('')
def listing(q: str = Query('', max_length=200), page: int = Query(1, ge=1), enabled_only: bool = False,
            user: User = Depends(manager), db=Depends(get_db)):
    size = 25
    try:
        if enabled_only:
            statement = select(OperatorAccess, User).join(User, User.id == OperatorAccess.user_id).where(User.active.is_(True))
            if q.strip():
                term = q.strip().lower()
                statement = statement.where(func.lower(OperatorAccess.exit_code).contains(term, autoescape=True) | func.lower(User.email).contains(term, autoescape=True) | func.lower(User.full_name).contains(term, autoescape=True))
            total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
            items = [user_payload({'code': access.exit_code, 'username': account.access_code or account.email, 'name': account.full_name, 'email': account.email if '@' in account.email else ''}, account, access)
                     for access, account in db.execute(statement.order_by(OperatorAccess.exit_code).offset((page-1)*size).limit(size))]
        else:
            try:
                result = fetch_exit_users(q, page, size)
            except Exception as exc:
                logger.exception('Fallo consultando MCUsuarios: CodigoUsuario, NombreCorto, Correo')
                raise HTTPException(503, 'No se pudo consultar MCUsuarios de EXIT (CodigoUsuario, NombreCorto, Correo). Revisa la conexión y el registro de la API.') from exc
            total = result['total']; items = []
            codes = [row['code'] for row in result['items']]
            accounts = {access.exit_code.casefold(): (account, access) for access, account in db.execute(select(OperatorAccess, User).join(User, User.id == OperatorAccess.user_id).where(OperatorAccess.exit_code.in_(codes)))} if codes else {}
            for source in result['items']:
                items.append(user_payload(source, *accounts.get(source['code'].casefold(), (None, None))))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception('Error consultando los accesos web en PostgreSQL')
        raise HTTPException(503, 'No se pudieron consultar los accesos web en PostgreSQL. Revisa el registro de la API.') from exc
    warning = None
    try:
        delegations = fetch_delegations()
    except Exception:
        logger.exception('Usuarios cargados, pero fallo al consultar las delegaciones de EXIT')
        delegations = []
        warning = 'Usuarios cargados. No se pudieron consultar las sedes de EXIT; no se puede guardar la asignación de sede hasta recuperar esa consulta.'
    return {'items': items, 'total': total, 'page_size': size, 'modules': MODULES, 'warning': warning,
            'delegations': [{'company': d.company, 'code': d.code, 'name': d.name} for d in delegations]}


@router.put('')
def save(data: AccessIn, user: User = Depends(manager), db=Depends(get_db)):
    source = lookup(data.code)
    try:
        stores = fetch_delegations()
        valid_store = any(d.company == data.company_code and d.code == data.delegation_code for d in stores)
        valid_ids = {f'{d.company}:{d.code}' for d in stores}
        if set(data.delegation_ids) - valid_ids:raise HTTPException(422, 'Selecciona delegaciones válidas de EXIT')
    except HTTPException:raise
    except Exception as exc:
        raise HTTPException(503, 'No se pudieron consultar las sedes de EXIT') from exc
    if not valid_store:
        raise HTTPException(422, 'Selecciona una sede válida de EXIT')
    access = linked(db, source['code'])
    account = db.get(User, access.user_id) if access else None
    if account and account.id == user.id and (not data.active or not data.permissions.get('users')):
        raise HTTPException(409, 'No puedes deshabilitar tu propio acceso ni quitarte la gestión de usuarios')
    password = None
    login = source['username'].strip()
    email = (source.get('email') or login).strip().lower()
    if not login or len(login)>40 or not email or len(email)>200:
        raise HTTPException(422, 'NombreCorto debe tener entre 1 y 40 caracteres y Correo un máximo de 200')
    collision_query = select(User.id).where((func.lower(User.email).in_([login.lower(),email])) | (func.lower(User.access_code).in_([login.lower(),email])))
    if account:collision_query = collision_query.where(User.id != account.id)
    if db.scalar(collision_query):
        raise HTTPException(409, 'NombreCorto o Correo ya pertenece a otra cuenta; revisa los datos en EXIT')
    if account is None:
        password = secrets.token_urlsafe(12)
        account = User(email=email, access_code=login, full_name=source['name'][:160] or login,
                       role='OPERADOR_TIENDA', password_hash=hash_password(password), must_change_password=True,
                       initial_password_expires_at=datetime.now(timezone.utc)+timedelta(hours=settings.initial_password_ttl_hours))
        db.add(account)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, 'El usuario o correo de acceso ya pertenece a otra cuenta') from exc
        access = OperatorAccess(user_id=account.id, exit_code=source['code'], permissions={})
        db.add(access)
    account.email = email
    account.access_code = login
    account.company_code = data.company_code; account.delegation_code = data.delegation_code
    account.full_name = source['name'][:160] or source['username']
    account.active = data.active
    access.permissions = {**data.permissions, 'delegation_ids': sorted(set(data.delegation_ids))}
    revoke(db, account)
    audit(db, user, 'OPERATOR_ACCESS_SAVED', 'USER', account.public_id, {'exit_code': source['code'], 'active': data.active, 'permissions': data.permissions, 'delegation_ids': data.delegation_ids, 'company': data.company_code, 'delegation': data.delegation_code})
    commit(db)
    return {**user_payload(source, account, access), 'initial_password': password}


@router.post('/password')
def password(data: PasswordIn, user: User = Depends(manager), db=Depends(get_db)):
    source = lookup(data.code)
    access = linked(db, source['code'])
    account = db.get(User, access.user_id) if access else None
    if not account or not account.active:
        raise HTTPException(409, 'Habilita primero el acceso del usuario')
    if account.id == user.id:
        raise HTTPException(409, 'Para cambiar tu propia contraseña utiliza Mi cuenta')
    value = data.password or secrets.token_urlsafe(12)
    account.password_hash = hash_password(value)
    account.must_change_password = True
    account.initial_password_ciphertext = None
    account.initial_password_expires_at = datetime.now(timezone.utc)+timedelta(hours=settings.initial_password_ttl_hours)
    revoke(db, account)
    audit(db, user, 'OPERATOR_PASSWORD_RESET', 'USER', account.public_id, {'exit_code': source['code']})
    commit(db)
    return {'login': account.access_code or account.email, 'initial_password': value, 'expires_at': account.initial_password_expires_at}


def provision_rpa(db):
    """Traslado inicial, una sola vez. Se verifica RPA en EXIT antes de tocar el acceso antiguo."""
    rows = fetch_exit_users(exact_identity='RPA', page_size=2)['items']
    matches = [row for row in rows if row['username'].casefold() == 'rpa' or row['code'].casefold() == 'rpa']
    if len(matches) != 1:
        raise RuntimeError('No se encontró un único usuario RPA en MCusuarios')
    source = matches[0]
    existing = linked(db, source['code'])
    if existing:
        if existing.permissions.get('all_delegations') is not True:
            existing.permissions = {**existing.permissions, 'all_delegations': True}
            account = db.get(User, existing.user_id)
            revoke(db, account)
            audit(db, None, 'OPERATOR_RPA_ALL_DELEGATIONS', 'USER', account.public_id, {'exit_code': source['code']})
            db.commit()
        return False  # Conserva contraseña, estado activo y permisos de las opciones.
    legacy = db.scalar(select(User).where(func.lower(User.email) == 'operador@bermudez.test'))
    email = (source.get('email') or 'rpa').strip().lower()
    if len(email)>200:raise RuntimeError('El correo de RPA supera 200 caracteres')
    collision_query = select(User.id).where((func.lower(User.email).in_(['rpa',email])) | (func.lower(User.access_code).in_(['rpa',email])))
    if legacy:collision_query = collision_query.where(User.id != legacy.id)
    collisions = db.scalar(collision_query)
    if collisions:
        raise RuntimeError('RPA ya está asignado a otra cuenta; revisar sin sobrescribirla')
    stores = fetch_delegations()
    if not stores:
        raise RuntimeError('EXIT no devuelve delegaciones para RPA')
    account = legacy or User(role='OPERADOR_TIENDA', email='rpa', password_hash='', full_name='RPA')
    if legacy and legacy.role != 'OPERADOR_TIENDA':
        raise RuntimeError('La cuenta anterior no es un operador')
    store = next((d for d in stores if legacy and (d.company, d.code) == (legacy.company_code, legacy.delegation_code)), stores[0])
    account.email = email; account.access_code = 'RPA'; account.full_name = source['name'][:160] or 'RPA'
    account.company_code = store.company; account.delegation_code = store.code
    account.password_hash = hash_password('123456'); account.active = True
    account.must_change_password = True
    account.initial_password_ciphertext = None
    account.initial_password_expires_at = None
    db.add(account); db.flush()
    db.add(OperatorAccess(user_id=account.id, exit_code=source['code'], permissions=dict.fromkeys(MODULES, True)))
    revoke(db, account)
    audit(db, None, 'OPERATOR_RPA_MIGRATED', 'USER', account.public_id, {'exit_code': source['code'], 'legacy_reused': legacy is not None})
    db.commit()
    return True
