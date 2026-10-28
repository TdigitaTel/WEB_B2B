from .operator_permissions import can_operate_delegation, delegation_scope
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from functools import lru_cache
from io import BytesIO
import json
import logging
import secrets
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import func, select, text, update, or_
from sqlalchemy.orm import Session

from .auth import audit, create_access_token, current_user, hash_password, require_roles, verify_password
from .category_import import router as category_import_router
from .category_visibility import router as category_visibility_router, image_router as category_image_router, image_urls, hidden_areas, hidden_codes, visible_catalog_codes, unclassified_area_ids, UNCLASSIFIED_CODE
from .config import settings
from .pickup import immediate_ready_at, immediate_available, next_open_date, scheduled_date_open, scheduled_ready_at, assign_attention_deadline
from .db import get_db
from .schemas import PickupChange, PickupSettingsIn, DeliveryConfirmation, WebOrderRegistrationChange, UserDisplayPreferences
from .exit_orders import upsert_exit_order
from .kardex_timing import fetch_kardex_timings, sales_order_number
from .order_timeline import exit_events, sync_history, instant, dispatch_timing, is_web_order
from .delegations import fetch_delegations, resolve_delegation
from .erp_db import (
    fetch_catalog_articles, fetch_catalog_articles_by_codes, fetch_catalog_brands,
    fetch_customer, fetch_customer_delivery_notes, fetch_customer_delivery_statuses, fetch_customer_invoices,
    fetch_delivery_statuses_for_orders,
    fetch_customer_favorite_articles, fetch_product_image, fetch_product_prices,
    fetch_product_stock, fetch_product_stocks, image_media_type,
)
from .exit_db import fetch_customer_exit_orders, fetch_exit_orders_live
from .image_admin import router as image_admin_router
from .image_missing import record_missing_product_image
from .models import (
    OperatorAccess, PickupSettings, AuthSession, Cart, CartItem, Customer, IntegrationOutbox, Notification,
    MaterialArea, MaterialFamily, MaterialProductType, MaterialSubfamily, Order, OrderItem,
    OrderStatusHistory, Product, ProfessionalRegistrationRequest, SyncStatus, User,
)
from .schemas import CartItemIn, CartItemUpdate, CustomerAccessReset, ExternalStatusChange, LoginIn, OrderCreate, PasswordChange, StatusChange
from .services import PostgresCatalogService, ensure_catalog_products, product_view

app = FastAPI(title="Bermúdez B2B API", version="1.0.0", openapi_url="/api/v1/openapi.json", docs_url="/docs")
app.include_router(category_import_router)
app.include_router(category_visibility_router)
app.include_router(category_image_router)
app.include_router(image_admin_router)
from .customer_delivery import delivery_enabled, validate_delivery
from .customer_access import router as customer_access_router
app.include_router(customer_access_router)
from .operator_access import router as operator_access_router
app.include_router(operator_access_router)
from .search_settings import router as search_settings_router, get_search_config
app.include_router(search_settings_router)
from .qr_access import router as qr_access_router
app.include_router(qr_access_router)
from .subusers import router as subusers_router
from .account_permissions import identity, principal_for
from .price_visibility import protect_payload
app.include_router(subusers_router)
from .replenishment import router as replenishment_router
app.include_router(replenishment_router)
from .login_appearance import router as login_appearance_router
app.include_router(login_appearance_router)
logger = logging.getLogger(__name__)

@lru_cache(maxsize=2000)
def exit_customer_name(code: str) -> str:
    customer = fetch_customer(code)
    return (customer or {}).get("trade_name") or (customer or {}).get("legal_name") or code
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def prevent_private_cache(request: Request, call_next):
    response = await call_next(request)
    if (hasattr(request.state, "document_permissions")
            and (request.state.hide_prices or not all(request.state.document_permissions.values()))
            and "application/json" in response.headers.get("content-type", "")):
        raw = b"".join([chunk async for chunk in response.body_iterator])
        protected = protect_payload(json.loads(raw), request.state.document_permissions, request.state.hide_prices)
        headers = {key: value for key, value in response.headers.items() if key.lower() not in {"content-length", "content-type"}}
        response = Response(json.dumps(protected, ensure_ascii=False), status_code=response.status_code, headers=headers, media_type="application/json")
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, private"
    return response


def live_delegations():
    try:
        return fetch_delegations()
    except Exception as exc:
        logger.exception("No se pudieron consultar las delegaciones de EXIT")
        raise HTTPException(503, "No se pudieron consultar las delegaciones en EXIT") from exc


def get_delegation(reference, company_code=None):
    try:
        return resolve_delegation(reference, live_delegations(), company_code=company_code)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


def delegation_name(reference, company_code=None):
    delegation = get_delegation(reference, company_code)
    return delegation.name if delegation else reference


def customer_code_for(user: User, db: Session) -> str:
    if user.erp_customer_code:
        return user.erp_customer_code
    if user.customer_id:
        legacy = db.get(Customer, user.customer_id)
        if legacy:
            return legacy.erp_id
    raise HTTPException(403, "Esta operación requiere una cuenta de cliente EXITERP")


def customer_for(user: User, db: Session) -> dict:
    principal_for(user, db)
    code = customer_code_for(user, db)
    try:
        customer = fetch_customer(code)
    except Exception as exc:
        logger.exception("Error consultando el cliente %s en EXITERP", code)
        raise HTTPException(503, "No se pudo consultar el cliente en EXITERP") from exc
    if not customer:
        raise HTTPException(403, "El cliente no existe o no está disponible en EXITERP")
    return customer


def legacy_customer_id(user: User) -> int | None:
    """Solo conserva la relación histórica de pedidos anteriores; no aporta datos maestros."""
    return user.customer_id


def active_cart(user: User, db: Session) -> Cart:
    customer_code = customer_code_for(user, db)
    cart = db.scalar(select(Cart).where(Cart.user_id == user.id, Cart.status == "ACTIVE").order_by(Cart.id.desc()))
    if not cart:
        cart = Cart(customer_id=legacy_customer_id(user), customer_code=customer_code, user_id=user.id, status="ACTIVE")
        db.add(cart); db.flush()
    elif not cart.customer_code:
        cart.customer_code = customer_code
    return cart


def _erp_articles(products: list[Product]) -> dict[str, dict]:
    try:
        articles = fetch_catalog_articles_by_codes([product.sku for product in products])
    except Exception as exc:
        logger.exception("Error consultando artículos EXIT para el carrito")
        raise HTTPException(503, "No se pudieron consultar los artículos en EXIT") from exc
    missing = [product.sku for product in products if product.sku not in articles]
    if missing:
        raise HTTPException(409, f"Artículos no disponibles en EXIT: {', '.join(missing[:8])}")
    return articles


def _erp_unit_prices(products: list[Product], articles: dict[str, dict] | None = None) -> dict[str, Decimal]:
    articles = articles or _erp_articles(products)
    return {sku: Decimal(str(values["price_without_tax"])) for sku, values in articles.items()}


def cart_payload(cart: Cart, user: User, db: Session) -> dict:
    rows = db.execute(select(CartItem, Product).join(Product, Product.id == CartItem.product_id).where(CartItem.cart_id == cart.id).order_by(CartItem.id)).all()
    articles = _erp_articles([product for _, product in rows]) if rows else {}
    prices = _erp_unit_prices([product for _, product in rows], articles) if rows else {}
    items, subtotal = [], Decimal("0")
    for item, product in rows:
        price = prices[product.sku]
        article = articles[product.sku]
        has_homologated_name = bool(
            product.short_description and product.source_system != "EXIT_CATALOG"
            and product.classification_status not in {None, "", "SIN_CLASIFICAR"}
        )
        line = (price * item.quantity).quantize(Decimal("0.01")); subtotal += line
        items.append({"id": item.id, "product_id": product.public_id, "sku": product.sku,
                      "name": product.short_description if has_homologated_name else article["description"],
                      "quantity": float(item.quantity), "unit": article["unit"],
                      "unit_price": float(price), "line_total": float(line)})
    store = get_delegation(cart.delegation_code, cart.company_code) if cart.store_id else None
    return {"delivery_enabled": delivery_enabled(db, customer_code_for(user, db)), "id": cart.public_id, "store": {"id": store.public_id, "name": store.name} if store else None,
            "items": items, "line_count": len(items), "subtotal": float(subtotal),
            "tax_total": float((subtotal * Decimal("0.21")).quantize(Decimal("0.01"))),
            "total": float((subtotal * Decimal("1.21")).quantize(Decimal("0.01")))}


def order_payload(order: Order, db: Session, include_items: bool = False, history_for_operator: bool = False) -> dict:
    store = get_delegation(order.delegation_code, order.company_code)
    customer_name = order.customer_code or "Cliente EXITERP"
    if order.customer_code:
        try:
            erp_customer = fetch_customer(order.customer_code)
            if erp_customer:
                customer_name = erp_customer["trade_name"] or erp_customer["legal_name"] or order.customer_code
        except Exception:
            logger.exception("No se pudo enriquecer el pedido con el cliente EXITERP %s", order.customer_code)
    creator = db.get(User, order.user_id) if order.user_id else None
    result = {"id": order.public_id, "number": order.order_number, "server_now": datetime.now(timezone.utc),
              "store": store.name if store else order.store_id, "store_code": store.code if store else order.delegation_code, "company_code": order.company_code, "delegation_code": order.delegation_code, "customer_code": order.customer_code, "customer_reference": order.customer_reference,
              "fulfillment_method": order.fulfillment_method, "delivery_address": order.delivery_address, "pickup_date": order.pickup_date, "attention_deadline_at": order.attention_deadline_at, "preparation_minutes_snapshot": order.preparation_minutes_snapshot, "job_name": order.job_name, "notes": order.notes, "subtotal": float(order.subtotal),
              "tax_total": float(order.tax_total), "total": float(order.total), "created_at": order.created_at,
              "customer": customer_name, "created_by": order.creator_user_name or (creator.full_name if creator else "Integración EXIT"),
              "principal_user_name": order.principal_user_name or (principal_for(creator, db).full_name if creator and not creator.parent_user_id else None),
              "creator_user_name": order.creator_user_name or (creator.full_name if creator else "Integración EXIT"),
              "nro_pedido_exit": order.nro_pedido_exit, "fecha_registro_exit": order.fecha_registro_exit, "delivered_at": order.delivered_at,
              "origen_pedido": order.origen_pedido, "is_web_order": order.origen_pedido == "B2B", "estado_registro_exit": order.estado_registro_exit}
    if include_items:
        result["items"] = []
        for item in db.scalars(select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id)).all():
            served = (item.served_quantity if item.served_quantity is not None else
                      max(Decimal("0"), item.quantity - item.pending_quantity)
                      if item.pending_quantity is not None else Decimal("0"))
            pending = (item.pending_quantity if item.pending_quantity is not None
                       else max(Decimal("0"), item.quantity - served))
            result["items"].append({"sku": item.sku, "description": item.description,
                                    "quantity": float(item.quantity), "served_quantity": float(served),
                                    "pending_quantity": float(pending), "unit": item.unit,
                                    "unit_price": float(item.unit_price), "line_total": float(item.line_total),
                                    "fulfillment_zone": item.fulfillment_zone or "OTROS"})
        history = db.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id == order.id).order_by(OrderStatusHistory.created_at)).all()
        result["history_enabled"] = settings.show_order_status_history or history_for_operator
        if result["history_enabled"]:
            result["history"] = [{"estado_registro_exit": h.estado_registro_exit, "source": h.source, "note": h.note, "created_at": h.created_at, "date_only": h.estado_registro_exit == "FACTURADO"} for h in sorted(history, key=lambda event: instant(event.created_at), reverse=True)]
        result["documents"] = []
        current_state = order.estado_registro_exit.strip().upper()
        visible_stage = {
            "BORRADOR": "BORRADOR", "PENDIENTE": "PENDIENTE",
            "BLOQUEADO": "EN_PROCESAMIENTO", "REGISTRADO": "EN_PROCESAMIENTO", "EN_PROCESO": "EN_PROCESAMIENTO", "EN_PREPARACION": "EN_PROCESAMIENTO",
            "ATENDIDO": "PENDIENTE_RECOJO", "ENTREGADO": "ENTREGADO", "FACTURADO": "FACTURADO",
        }.get(current_state, "PENDIENTE")
        stage_position = {"BORRADOR": 0, "PENDIENTE": 0, "EN_PROCESAMIENTO": 1, "PENDIENTE_RECOJO": 2, "ENTREGADO": 3, "FACTURADO": 4}
        pending_dates = [event.created_at for event in history if event.estado_registro_exit == "PENDIENTE"]
        draft_dates = [event.created_at for event in history if event.estado_registro_exit == "BORRADOR"]
        processing_dates = [event.created_at for event in history if event.estado_registro_exit in {"BLOQUEADO", "REGISTRADO", "EN_PROCESO", "EN_PREPARACION"}]
        pickup_dates = [event.created_at for event in history if event.estado_registro_exit == "ATENDIDO"]
        result["attended_at"] = max(pickup_dates, key=instant) if pickup_dates else None
        if order.origen_pedido != "B2B" and not result["delivered_at"]:
            result["delivered_at"] = max((h.created_at for h in history if h.source == "EXIT" and h.estado_registro_exit == "ENTREGADO"), key=instant, default=None)
        delivered_dates = [event.created_at for event in history if event.estado_registro_exit == "ENTREGADO" and event.source == "WEB"]
        invoice_dates = [event.created_at for event in history if event.estado_registro_exit == "FACTURADO"]
        stage_dates = {
            **({"BORRADOR": min(draft_dates)} if draft_dates else {}),
            "PENDIENTE": max(pending_dates) if pending_dates else None,
            "EN_PROCESAMIENTO": min(processing_dates) if processing_dates and stage_position[visible_stage] >= 1 else None,
            "PENDIENTE_RECOJO": max(pickup_dates) if pickup_dates and stage_position[visible_stage] >= 2 else None,
            "ENTREGADO": order.delivered_at or (max(delivered_dates) if delivered_dates and stage_position[visible_stage] >= 3 else None),
            "FACTURADO": max(invoice_dates) if invoice_dates and stage_position[visible_stage] >= 4 else None,
        }
        result["workflow"] = [{"etapa": etapa, "completed_at": completed_at, "date_only": etapa == "FACTURADO"} for etapa, completed_at in stage_dates.items()]
    return result


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/v1/auth/login")
def login(data: LoginIn, response: Response, db: Session = Depends(get_db)):
    identifier = data.email.strip().lower()
    candidates = db.scalars(select(User).where((func.lower(User.email) == identifier) | (func.lower(User.access_code) == identifier) | User.id.in_(select(OperatorAccess.user_id).where(func.lower(OperatorAccess.exit_code) == identifier)) | ((func.lower(User.erp_customer_code) == identifier) & User.role.in_(["CLIENTE", "CLIENTE_ADMIN"]) & User.parent_user_id.is_(None)))).all()
    valid = [candidate for candidate in candidates if candidate.active and verify_password(data.password, candidate.password_hash)]
    user = valid[0] if len(valid) == 1 else None
    if not user:
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    return complete_login(user, response, db)


def complete_login(user: User, response: Response, db: Session):
    if user.must_change_password and user.initial_password_expires_at and user.initial_password_expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
        raise HTTPException(401, "La clave inicial ha caducado. Contacta con Bermúdez Ulloa")
    customer = None
    if user.role not in {"OPERADOR_TIENDA", "ADMIN"}:
        customer = customer_for(user, db)
    user.last_login_at = datetime.now(timezone.utc)
    audit(db, user, "LOGIN", "USER", user.public_id)
    token = create_access_token(user, db)
    response.set_cookie("b2b_access", token, httponly=True, samesite="lax", secure=False)
    db.commit()
    display_name = user.full_name if user.parent_user_id else ((customer or {}).get("trade_name") or (customer or {}).get("legal_name") or user.full_name)
    return {"user": {**identity(user, db), "id": user.public_id, "name": display_name, "email": user.email, "role": user.role, "idle_timeout_seconds": settings.session_idle_timeout_minutes * 60, "must_change_password": user.must_change_password, "show_delivery_note_images": user.show_delivery_note_images, "show_order_images": user.show_order_images}, "access_token": token}


@app.post("/api/v1/auth/logout")
def logout(request: Request, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    request.state.auth_session.revoked = True
    audit(db, user, "LOGOUT", "USER", user.public_id); db.commit(); response.delete_cookie("b2b_access")
    return {"ok": True}


@app.post("/api/v1/auth/activity")
def session_activity(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    request.state.auth_session.last_activity_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@app.get("/api/v1/account")
def account(user: User = Depends(current_user), db: Session = Depends(get_db)):
    customer = None if user.role in {"OPERADOR_TIENDA", "ADMIN"} else customer_for(user, db)
    display_name = user.full_name if user.parent_user_id else ((customer or {}).get("trade_name") or (customer or {}).get("legal_name") or user.full_name)
    return {"user": {**identity(user, db), "id": user.public_id, "name": display_name, "email": user.email, "role": user.role, "idle_timeout_seconds": settings.session_idle_timeout_minutes * 60, "must_change_password": user.must_change_password, "show_delivery_note_images": user.show_delivery_note_images, "show_order_images": user.show_order_images},
            "customer": customer}


@app.patch("/api/v1/account/preferences")
def update_display_preferences(data: UserDisplayPreferences, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.show_delivery_note_images = data.show_delivery_note_images
    user.show_order_images = data.show_order_images
    audit(db, user, "USER_DISPLAY_PREFERENCES_CHANGED", "USER", user.public_id, data.model_dump())
    db.commit()
    return data.model_dump()


@app.patch("/api/v1/account/password")
def change_password(data: PasswordChange, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, "La contraseña actual no es correcta")
    if data.current_password == data.new_password:
        raise HTTPException(400, "La contraseña nueva debe ser diferente")
    if user.must_change_password and len(data.new_password) < 12:
        raise HTTPException(422, "Utiliza al menos 12 caracteres para la nueva contraseña")
    user.password_hash = hash_password(data.new_password)
    user.must_change_password = False
    user.initial_password_expires_at = None
    user.initial_password_ciphertext = None
    db.execute(update(AuthSession).where(AuthSession.user_id == user.id, AuthSession.id != request.state.auth_session.id).values(revoked=True))
    audit(db, user, "PASSWORD_CHANGED", "USER", user.public_id)
    db.commit()
    return {"ok": True}


@app.post("/api/v1/registration-requests", status_code=201)
def registration(data: dict, db: Session = Depends(get_db)):
    required = ["legal_name", "tax_id", "contact_name", "email", "phone"]
    if not all(data.get(field) for field in required) or not data.get("accepted_terms"):
        raise HTTPException(422, "Completa los datos y acepta las condiciones")
    row = ProfessionalRegistrationRequest(**{field: data[field] for field in required}, accepted_terms=True)
    db.add(row); db.commit()
    return {"id": row.public_id, "status": row.status}


@app.get("/api/v1/stores")
def stores(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [{"id": s.id, "code": s.code, "name": s.name, "address": s.address,
             "company_code": s.company, "warehouse_code": s.warehouse_code,
             "warehouse_name": s.warehouse_name} for s in live_delegations()]


@app.get("/api/v1/store/catalog-brands")
def catalog_brands(user: User = Depends(require_roles("OPERADOR_TIENDA", "ADMIN"))):
    try:
        return fetch_catalog_brands()
    except Exception as exc:
        logger.exception("No se pudieron consultar las marcas de EXIT")
        raise HTTPException(503, "No se pudieron consultar las marcas de EXIT") from exc


@app.get("/api/v1/products")
def products(q: str = "", family: str | None = None, area_id: int | None = None,
             family_id: int | None = None, subfamily_id: int | None = None,
             product_type_id: int | None = None, page: int = 1,
             page_size: int = Query(24, le=100), user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    customer = customer_for(user, db)
    classification_codes = PostgresCatalogService(db).classification_codes(
        family, area_id, family_id, subfamily_id, product_type_id
    )
    if area_id and db.scalar(select(MaterialArea.code).where(MaterialArea.id == area_id)) == UNCLASSIFIED_CODE:
        classification_codes = list(db.scalars(select(Product.sku).where(
            Product.material_area_id.is_(None) | Product.material_area_id.in_(unclassified_area_ids(db)))).all())
    classification_codes = visible_catalog_codes(db, classification_codes)
    try:
        articles, total = fetch_catalog_articles(q, page, page_size, classification_codes, excluded_codes=hidden_codes(db), search_config=get_search_config(db))
    except Exception as exc:
        logger.exception("Error consultando la maestra de artículos EXIT")
        raise HTTPException(503, "No se pudo consultar el catálogo en EXIT") from exc
    products_by_code = ensure_catalog_products(db, articles)
    product_codes = [article["article_code"] for article in articles]
    try:
        stocks = fetch_product_stocks(product_codes)
    except Exception:
        logger.exception("Error consultando stock ERP para el catalogo")
        raise HTTPException(503, "No se pudo consultar el stock en el ERP")
    return {
        "items": [
            product_view(
                products_by_code[article["article_code"]], customer, db,
                stocks.get(article["article_code"], []), None, article,
            )
            for article in articles
        ],
        "total": total, "page": page, "page_size": page_size,
    }


@app.get("/api/v1/catalog/favorites")
def favorite_products(limit: int = Query(8, ge=1, le=24), user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    customer = customer_for(user, db)
    customer_code = customer_code_for(user, db)
    try:
        purchases = fetch_customer_favorite_articles(customer_code, limit)
    except Exception as exc:
        logger.exception("Error consultando los artículos favoritos del cliente %s", customer_code)
        raise HTTPException(503, "No se pudieron consultar los materiales favoritos en EXIT") from exc

    purchased_units = {row["article_code"]: row["purchased_units"] for row in purchases}
    excluded = set(hidden_codes(db))
    codes = visible_catalog_codes(db, [code for code in purchased_units if code not in excluded])
    if not codes:
        return {"items": [], "total": 0}
    try:
        articles_by_code = fetch_catalog_articles_by_codes(codes)
    except Exception as exc:
        logger.exception("Error consultando los artículos favoritos en EXIT")
        raise HTTPException(503, "No se pudieron consultar los materiales favoritos en EXIT") from exc
    articles = [articles_by_code[code] for code in codes if code in articles_by_code]
    products_by_code = ensure_catalog_products(db, articles)
    product_codes = [article["article_code"] for article in articles]
    try:
        stocks = fetch_product_stocks(product_codes)
    except Exception as exc:
        logger.exception("Error consultando stock ERP para materiales favoritos")
        raise HTTPException(503, "No se pudo consultar el stock en el ERP") from exc
    items = []
    for article in articles:
        code = article["article_code"]
        product = products_by_code[code]
        item = product_view(product, customer, db, stocks.get(code, []), None, article)
        item["purchased_units"] = purchased_units[code]
        items.append(item)
    return {"items": items, "total": len(items)}


@app.get("/api/v1/catalog/classification")
def catalog_classification(user: User = Depends(current_user), db: Session = Depends(get_db)):
    customer_for(user, db)
    rows = db.execute(
        select(
            MaterialArea.id, MaterialArea.code, MaterialArea.name,
            MaterialFamily.id, MaterialFamily.code, MaterialFamily.name,
            MaterialSubfamily.id, MaterialSubfamily.code, MaterialSubfamily.name,
            MaterialProductType.id, MaterialProductType.code, MaterialProductType.name,
            func.count(Product.id),
        )
        .outerjoin(MaterialFamily, MaterialFamily.area_id == MaterialArea.id)
        .outerjoin(MaterialSubfamily, MaterialSubfamily.family_id == MaterialFamily.id)
        .outerjoin(MaterialProductType, MaterialProductType.subfamily_id == MaterialSubfamily.id)
        .outerjoin(Product, (Product.material_product_type_id == MaterialProductType.id) & Product.active.is_(True))
        .where(MaterialArea.id.not_in(hidden_areas(db)),
               MaterialArea.id.not_in(unclassified_area_ids(db)) | (MaterialArea.code == UNCLASSIFIED_CODE))
        .group_by(MaterialArea.id, MaterialFamily.id, MaterialSubfamily.id, MaterialProductType.id)
        .order_by(MaterialArea.name, MaterialFamily.name, MaterialSubfamily.name, MaterialProductType.name)
    ).all()
    areas: dict[int, dict] = {}
    category_images = image_urls(db)
    area_counts = dict(db.execute(select(Product.material_area_id, func.count(Product.id))
        .where(Product.active.is_(True)).group_by(Product.material_area_id)).all())
    unclassified_ids = set(db.scalars(unclassified_area_ids(db)).all())
    unclassified_count = sum(count for area_id, count in area_counts.items() if area_id is None or area_id in unclassified_ids)
    for area_id, area_code, area_name, family_id, family_code, family_name, subfamily_id, subfamily_code, subfamily_name, type_id, type_code, type_name, count in rows:
        area = areas.setdefault(area_id, {"id": area_id, "code": area_code, "name": area_name, "image_url": category_images.get(area_id), "count": 0, "families": {}})
        area["count"] = unclassified_count if area_code == UNCLASSIFIED_CODE else area_counts.get(area_id, 0)
        if family_id is None:
            continue
        family = area["families"].setdefault(family_id, {"id": family_id, "code": family_code, "name": family_name, "count": 0, "subfamilies": {}})
        if subfamily_id is None:
            continue
        subfamily = family["subfamilies"].setdefault(subfamily_id, {"id": subfamily_id, "code": subfamily_code, "name": subfamily_name, "count": 0, "product_types": []})
        if type_id is None:
            continue
        subfamily["product_types"].append({"id": type_id, "code": type_code, "name": type_name, "count": count})
        subfamily["count"] += count
        family["count"] += count
    result = []
    for area in areas.values():
        area["families"] = list(area["families"].values())
        for family in area["families"]:
            family["subfamilies"] = list(family["subfamilies"].values())
        result.append(area)
    return result


@app.get("/api/v1/search/suggestions")
def suggestions(q: str = Query(min_length=2), user: User = Depends(current_user), db: Session = Depends(get_db)):
    customer_for(user, db)
    try:
        articles, _ = fetch_catalog_articles(q, 1, 8, visible_catalog_codes(db), excluded_codes=hidden_codes(db), search_config=get_search_config(db))
    except Exception as exc:
        logger.exception("Error consultando sugerencias en EXIT")
        raise HTTPException(503, "No se pudieron consultar las sugerencias en EXIT") from exc
    products_by_code = ensure_catalog_products(db, articles)
    result = []
    for article in articles:
        product = products_by_code[article["article_code"]]
        has_homologated_name = bool(
            product.short_description and product.source_system != "EXIT_CATALOG"
            and product.classification_status not in {None, "", "SIN_CLASIFICAR"}
        )
        result.append({
            "id": product.public_id, "sku": article["article_code"],
            "name": product.short_description if has_homologated_name else article["description"],
            "price": float(article["price_with_tax"]),
            "area_id": product.material_area_id, "family_id": product.material_family_id,
            "subfamily_id": product.material_subfamily_id,
            "product_type_id": product.material_product_type_id,
        })
    return result


@app.get("/api/v1/products/{product_id}")
def product_detail(product_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    product = db.scalar(select(Product).where(Product.public_id == product_id))
    if not product: raise HTTPException(404, "Producto no encontrado")
    try:
        article = fetch_catalog_articles_by_codes([product.sku]).get(product.sku)
    except Exception as exc:
        logger.exception("Error consultando artículo EXIT para SKU %s", product.sku)
        raise HTTPException(503, "No se pudo consultar el producto en EXIT") from exc
    if not article:
        raise HTTPException(404, "Producto no disponible en EXIT")
    try:
        stock = fetch_product_stock(product.sku)
    except Exception:
        logger.exception("Error consultando stock ERP para SKU %s", product.sku)
        raise HTTPException(503, "No se pudo consultar el stock en el ERP")
    return product_view(product, customer_for(user, db), db, stock, None, article)


@app.get("/api/v1/pickup-settings")
def pickup_settings(user: User = Depends(current_user), db: Session = Depends(get_db)):
    config = db.get(PickupSettings, 1)
    tomorrow = datetime.now(ZoneInfo("Europe/Madrid")).date() + timedelta(days=1)
    return {"preparation_minutes": config.preparation_minutes if config else 60, "minimum_date": tomorrow.isoformat(), "schedules": config.schedules or {} if config else {}}


@app.get("/api/v1/pickup-availability")
def pickup_availability(company: int, delegation: str, scheduled_date: date | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    config = pickup_settings(user, db)
    following = next_open_date(db, company, delegation)
    ready = immediate_ready_at(db, company, delegation)
    scheduled = scheduled_ready_at(db, company, delegation, scheduled_date) if scheduled_date else None
    return {"scheduled_ready_at": scheduled.isoformat() if scheduled else None, **config, "immediate_available": ready is not None, "immediate_ready_at": ready.isoformat() if ready else None, "minimum_date": following.isoformat() if following else None}


@app.patch("/api/v1/pickup-settings")
def update_pickup_settings(data: PickupSettingsIn, user: User = Depends(require_roles("OPERADOR_TIENDA", "ADMIN")), db: Session = Depends(get_db)):
    config = db.get(PickupSettings, 1)
    if not config:
        config = PickupSettings(id=1)
        db.add(config)
    if data.schedules is not None:
        allowed = {row.id for row in fetch_delegations()}
        if set(data.schedules) - allowed:
            raise HTTPException(422, "Sede no válida")
        config.schedules = {key: [day.model_dump() for day in days] for key, days in data.schedules.items()}
    config.preparation_minutes = data.preparation_minutes
    audit(db, user, "PICKUP_SETTINGS_UPDATED", "SETTINGS", "pickup", {"preparation_minutes": data.preparation_minutes})
    db.commit()
    return pickup_settings(user, db)


@app.get("/api/v1/products/by-sku/{sku}/visual")
def product_visual_by_sku(sku: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    customer_for(user, db)
    product = db.scalar(select(Product).where(Product.sku == sku))
    return {"family": (product.family if product else None) or "Sin clasificar"}


@app.get("/api/v1/products/by-sku/{sku}/image")
def product_image_by_sku(sku: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    customer_for(user, db)
    product = db.scalar(select(Product).where(Product.sku == sku))
    if not product:
        raise HTTPException(404, "Imagen no disponible")
    return product_image(product.public_id, user, db)


@app.get("/api/v1/products/{product_id}/image")
def product_image(product_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    customer_for(user, db)
    product = db.scalar(select(Product).where(Product.public_id == product_id))
    if not product:
        raise HTTPException(404, "Producto no encontrado")
    source = settings.product_image_source.lower().strip()
    if source not in {"auto", "postgres", "sqlserver"}:
        raise HTTPException(500, "PRODUCT_IMAGE_SOURCE debe ser auto, postgres o sqlserver")
    if source != "sqlserver" and product.image_data:
        return Response(content=product.image_data, media_type=product.image_media_type or image_media_type(product.image_data),
                        headers={"Cache-Control": "private, max-age=86400", "X-Image-Source": "postgres"})
    if not product.image_data:
        record_missing_product_image(db, product, "Sin imagen validada en PostgreSQL")
    if source == "postgres":
        raise HTTPException(404, "Imagen no disponible en PostgreSQL")
    try:
        data = fetch_product_image(product.sku)
    except Exception:
        logger.exception("Error consultando imagen ERP para SKU %s", product.sku)
        raise HTTPException(503, "No se pudo consultar la imagen en el ERP")
    if not data:
        record_missing_product_image(db, product, "Sin imagen en PostgreSQL ni en EXITERP")
        raise HTTPException(404, "Imagen no disponible")
    return Response(content=data, media_type=image_media_type(data), headers={"Cache-Control": "private, max-age=86400", "X-Image-Source": "sqlserver"})


@app.get("/api/v1/cart")
def get_cart(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return cart_payload(active_cart(user, db), user, db)


@app.post("/api/v1/cart/items", status_code=201)
def add_cart_item(data: CartItemIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    product = db.scalar(select(Product).where(Product.public_id == data.product_id))
    if not product: raise HTTPException(404, "Producto no encontrado")
    try:
        if product.sku not in fetch_catalog_articles_by_codes([product.sku]):
            raise HTTPException(409, "El producto ya no está activo en EXIT")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error validando el producto %s en EXIT", product.sku)
        raise HTTPException(503, "No se pudo validar el producto en EXIT") from exc
    cart = active_cart(user, db)
    item = db.scalar(select(CartItem).where(CartItem.cart_id == cart.id, CartItem.product_id == product.id))
    if item: item.quantity += data.quantity
    else: db.add(CartItem(cart_id=cart.id, product_id=product.id, quantity=data.quantity))
    audit(db, user, "CART_ITEM_ADDED", "PRODUCT", product.public_id, {"quantity": float(data.quantity)})
    db.commit(); return cart_payload(cart, user, db)


@app.patch("/api/v1/cart/items/{item_id}")
def update_cart_item(item_id: int, data: CartItemUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    cart = active_cart(user, db); item = db.scalar(select(CartItem).where(CartItem.id == item_id, CartItem.cart_id == cart.id))
    if not item: raise HTTPException(404, "Línea no encontrada")
    item.quantity = data.quantity; db.commit(); return cart_payload(cart, user, db)


@app.delete("/api/v1/cart/items/{item_id}")
def delete_cart_item(item_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    cart = active_cart(user, db); item = db.scalar(select(CartItem).where(CartItem.id == item_id, CartItem.cart_id == cart.id))
    if not item: raise HTTPException(404, "Línea no encontrada")
    db.delete(item); db.commit(); return cart_payload(cart, user, db)


@app.post("/api/v1/orders", status_code=201)
def create_order(data: OrderCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if data.pickup_date and data.pickup_date < datetime.now(ZoneInfo("Europe/Madrid")).date() + timedelta(days=1):
        raise HTTPException(422, "La recogida programada debe ser a partir de mañana")
    customer = customer_for(user, db); customer_code = customer_code_for(user, db); cart = active_cart(user, db)
    delivery_address = validate_delivery(db, customer_code, data.fulfillment_method, data.delivery_address)
    if data.delegation_code is not None and data.company_code is None:
        raise HTTPException(422, "Indica CodigoEmpresa junto a IdDelegacion")
    store = get_delegation(data.delegation_code or data.store_id, data.company_code)
    if not store: raise HTTPException(404, "Tienda no encontrada")
    if not data.draft and data.pickup_date and not scheduled_date_open(db, store.company, store.code, data.pickup_date):
        raise HTTPException(409, "La sede está cerrada en la fecha seleccionada")
    if not data.draft and not data.pickup_date and not immediate_available(db, store.company, store.code):
        raise HTTPException(409, "Recogida inmediata no disponible: selecciona una fecha programada")
    rows = db.execute(select(CartItem, Product).join(Product, Product.id == CartItem.product_id).where(CartItem.cart_id == cart.id)).all()
    if not rows: raise HTTPException(400, "El pedido está vacío")
    articles = _erp_articles([product for _, product in rows])
    prices = _erp_unit_prices([product for _, product in rows], articles)
    warehouse_code = store.warehouse_code
    if not warehouse_code:
        raise HTTPException(409, "La delegación no tiene CodigoAlmacen configurado en EXIT")
    stock_warning = None
    try:
        stocks = fetch_product_stocks([product.sku for _, product in rows])
        shortages = []
        for cart_item, product in rows:
            available = next((Decimal(str(item["available"])) for item in stocks.get(product.sku, [])
                              if str(item["store_code"]).strip() == warehouse_code), Decimal("0"))
            if available < cart_item.quantity:
                shortages.append({"sku": product.sku, "name": product.short_description,
                                  "requested": float(cart_item.quantity), "available": float(max(available, Decimal("0")))})
        if shortages:
            stock_warning = {"store": store.name, "items": shortages}
    except Exception:
        logger.exception("No se pudo comprobar el stock de recogida del pedido")
    initial_status = "BORRADOR" if data.draft else "PENDIENTE"
    principal = principal_for(user, db)
    order = Order(principal_user_id=principal.id, principal_user_name=principal.full_name, creator_user_name=user.full_name, order_number=f"TMP-{cart.public_id[:20]}", customer_id=legacy_customer_id(user), customer_code=customer_code, user_id=user.id, company_code=store.company, delegation_code=store.code,
                  origen_pedido="B2B", estado_registro_exit=initial_status,
                  fulfillment_method=data.fulfillment_method, delivery_address=delivery_address, pickup_date=data.pickup_date, customer_reference=data.customer_reference, job_name=data.job_name, notes=data.notes,
                  subtotal=0, tax_total=0, total=0, sync_status=SyncStatus.pending)
    if not data.draft:
        assign_attention_deadline(order, db)
    db.add(order); db.flush(); order.order_number = f"WEB-{datetime.now().year}-{order.id:07d}"
    subtotal = Decimal("0")
    for cart_item, product in rows:
        article = articles[product.sku]
        has_homologated_name = bool(
            product.short_description and product.source_system != "EXIT_CATALOG"
            and product.classification_status not in {None, "", "SIN_CLASIFICAR"}
        )
        description = product.short_description if has_homologated_name else article["description"]
        price = prices[product.sku]; line = (price * cart_item.quantity).quantize(Decimal("0.01")); subtotal += line
        db.add(OrderItem(order_id=order.id, product_id=product.id, sku=product.sku, description=description,
                         quantity=cart_item.quantity, unit=article["unit"], unit_price=price, discount_pct=Decimal("0"),
                         tax_rate=product.tax_rate, line_total=line))
        db.delete(cart_item)
    order.subtotal = subtotal; order.tax_total = (subtotal * Decimal("0.21")).quantize(Decimal("0.01")); order.total = order.subtotal + order.tax_total
    history_note = "Pedido guardado como borrador" if data.draft else "Pedido enviado desde el portal"
    db.add(OrderStatusHistory(order_id=order.id, estado_registro_exit=initial_status, changed_by_user_id=user.id, source="WEB", note=history_note))
    if not data.draft:
        db.add(Notification(customer_id=legacy_customer_id(user), customer_code=customer_code, user_id=user.id, title="Pedido recibido", message=f"Hemos recibido el pedido {order.order_number}."))
        db.add(IntegrationOutbox(aggregate_type="ORDER", aggregate_id=order.public_id, event_type="ORDER_CREATED",
                                 payload={"order_number": order.order_number, "customer_erp_id": customer_code, "store": store.code, "fulfillment_method": order.fulfillment_method, "delivery_address": order.delivery_address}, sync_status=SyncStatus.pending))
    cart.status = "CONVERTED"
    audit(db, user, "ORDER_CREATED", "ORDER", order.public_id, {"number": order.order_number, "store": store.code})
    db.commit()
    payload = order_payload(order, db, True)
    payload["stock_warning"] = stock_warning
    return payload


def customer_order(order_id: str, user: User, db: Session) -> Order:
    customer_for(user, db); customer_code = customer_code_for(user, db)
    condition = Order.customer_code == customer_code
    if user.customer_id:
        condition = condition | (Order.customer_id == user.customer_id)
    if user.own_orders_only:
        condition = condition & (Order.user_id == user.id)
    order = db.scalar(select(Order).where(Order.public_id == order_id, condition))
    if not order:
        raise HTTPException(404, "Pedido no encontrado")
    return order


@app.post("/api/v1/orders/{order_id}/submit")
def submit_draft_order(order_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    order = customer_order(order_id, user, db)
    if order.estado_registro_exit != "BORRADOR":
        raise HTTPException(409, "Solo se puede enviar un pedido que esté en borrador")
    validate_delivery(db, order.customer_code, order.fulfillment_method, order.delivery_address)
    if order.pickup_date:
        if not scheduled_date_open(db, order.company_code, order.delegation_code, order.pickup_date):
            raise HTTPException(409, "La sede está cerrada en la fecha seleccionada")
        if order.pickup_date <= datetime.now(ZoneInfo("Europe/Madrid")).date():
            raise HTTPException(409, "Actualiza la fecha de recogida antes de enviar el borrador")
    elif not immediate_available(db, order.company_code, order.delegation_code):
        raise HTTPException(409, "Recogida inmediata no disponible en el horario actual")
    assign_attention_deadline(order, db)
    order.estado_registro_exit = "PENDIENTE"
    order.sync_status = SyncStatus.pending
    store = get_delegation(order.delegation_code, order.company_code)
    db.add(OrderStatusHistory(order_id=order.id, estado_registro_exit="PENDIENTE", changed_by_user_id=user.id, source="WEB", note="Borrador enviado desde el portal"))
    db.add(Notification(customer_id=legacy_customer_id(user), customer_code=order.customer_code, user_id=user.id,
                        title="Pedido recibido", message=f"Hemos recibido el pedido {order.order_number}."))
    db.add(IntegrationOutbox(aggregate_type="ORDER", aggregate_id=order.public_id, event_type="ORDER_CREATED",
                             payload={"order_number": order.order_number, "customer_erp_id": order.customer_code,
                                      "store": store.code if store else "", "fulfillment_method": order.fulfillment_method, "delivery_address": order.delivery_address}, sync_status=SyncStatus.pending))
    audit(db, user, "ORDER_SUBMITTED", "ORDER", order.public_id, {"number": order.order_number})
    db.commit()
    return order_payload(order, db, True)


@app.delete("/api/v1/orders/{order_id}")
def delete_order(order_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    order = customer_order(order_id, user, db)
    deletable = order.estado_registro_exit in {"BORRADOR", "PENDIENTE"} and not order.nro_pedido_exit
    if not deletable:
        raise HTTPException(409, "Solo se pueden eliminar pedidos en borrador o pendientes que todavía no estén registrados en EXIT")
    number = order.order_number
    audit(db, user, "ORDER_DELETED", "ORDER", order.public_id, {"number": number, "estado_registro_exit": order.estado_registro_exit})
    for event in db.scalars(select(IntegrationOutbox).where(
        IntegrationOutbox.aggregate_type == "ORDER",
        IntegrationOutbox.aggregate_id == order.public_id,
    )).all():
        db.delete(event)
    db.delete(order)
    db.commit()
    return {"ok": True, "number": number}


@app.get("/api/v1/orders")
def orders(date_from: date | None = None, date_to: date | None = None,
           state: str = "PENDIENTE", user: User = Depends(current_user), db: Session = Depends(get_db)):
    customer_for(user, db); customer_code = customer_code_for(user, db)
    today = datetime.now().astimezone().date()
    start, end = date_from or today, date_to or date_from or today
    if start > end:
        raise HTTPException(422, "La fecha desde no puede ser posterior a la fecha hasta")
    condition = Order.customer_code == customer_code
    if user.customer_id:
        condition = condition | (Order.customer_id == user.customer_id)
    if user.own_orders_only:
        condition = condition & (Order.user_id == user.id)
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"order-history-customer:{customer_code}"})
    all_local_rows = db.scalars(select(Order).where(condition).order_by(Order.created_at.desc()).limit(5000)).all()
    local_rows = [row for row in all_local_rows if start <= row.created_at.date() <= end]
    exit_rows = fetch_customer_exit_orders(customer_code, start, end)
    notes_available = True
    try:
        delivery_rows = fetch_customer_delivery_statuses(customer_code)
    except Exception:
        logger.exception("No se pudieron consultar los albaranes para actualizar el historial")
        notes_available = False
        delivery_rows = []
    def document_key(value: str | None) -> str:
        normalized = str(value or "").replace("~", "/").replace("-", "/")
        return "/".join(part.strip().upper() for part in normalized.split("/") if part.strip())
    deliveries: dict[str, dict] = {}
    for delivery in delivery_rows:
        key = document_key(delivery.get("order_number"))
        if key and key not in deliveries:
            deliveries[key] = delivery
            deliveries.setdefault(key.split("/")[-1], delivery)
    by_exit: dict[str, Order] = {}
    by_web = {row.order_number.strip().upper(): row for row in all_local_rows}
    for row in all_local_rows:
        if row.nro_pedido_exit:
            raw = row.nro_pedido_exit.strip().upper()
            by_exit[raw] = row
            by_exit[raw.split("/")[-1]] = row
    linked: set[int] = set()
    result: list[dict] = []
    def exit_workflow(record, current: str | None = None, delivery: dict | None = None, web_order: bool | None = None) -> list[dict]:
        current = current or record.estado_registro_exit
        positions = {"PENDIENTE": 0, "BLOQUEADO": 1, "REGISTRADO": 1, "EN_PROCESO": 1, "EN_PREPARACION": 1, "ATENDIDO": 2, "ENTREGADO": 3, "FACTURADO": 4}
        position = positions.get(current, 0)
        event_dates = {state: stamp for state, stamp, _ in exit_events(record, delivery, web_order)}
        processing = [event_dates[state] for state in ('REGISTRADO', 'EN_PREPARACION') if state in event_dates]
        dates = (None, min(processing) if processing else None,
                 event_dates.get('ATENDIDO'), event_dates.get('ENTREGADO'), event_dates.get('FACTURADO'))
        return [{"etapa": stage, "completed_at": dates[index] if index <= position else None,
                 "date_only": stage == "FACTURADO"}
                for index, stage in enumerate(("PENDIENTE", "EN_PROCESAMIENTO", "PENDIENTE_RECOJO", "ENTREGADO", "FACTURADO"))]
    for record in exit_rows:
        external = record.exit_order_id.strip().upper()
        external_key = document_key(external)
        delivery = deliveries.get(external_key) or deliveries.get(external_key.split("/")[-1])
        effective_state = "EN_PREPARACION" if record.prepared_at else "REGISTRADO"
        if delivery:
            if delivery["is_invoiced"]:
                effective_state = "FACTURADO"
            else:
                effective_state = "ATENDIDO"
        local = by_exit.get(external) or by_exit.get(external.split("/")[-1])
        if not local and record.customer_reference:
            local = by_web.get(record.customer_reference.strip().upper())
            if local and not local.nro_pedido_exit:
                local.nro_pedido_exit = record.exit_order_id
                local.fecha_registro_exit = record.recorded_at
        if user.own_orders_only and (local is None or local.user_id != user.id):
            continue
        if local is None:
            local = upsert_exit_order(db, record, user)
            by_exit[external] = local
        if local:
            linked.add(local.id)
            local.fecha_registro_exit = record.recorded_at
            if record.prepared_at and not delivery:
                effective_state = "EN_PREPARACION"
            elif not delivery:
                effective_state = "REGISTRADO"
            web_order = is_web_order(record, local)
            if delivery and delivery["is_printed"] and not web_order and effective_state != "FACTURADO":
                effective_state = "ENTREGADO"
            sync_history(db, local, exit_events(record, delivery, web_order), web_order=web_order)
            if local.delivered_at and effective_state != "FACTURADO":
                effective_state = "ENTREGADO"
            local.estado_registro_exit = effective_state
            payload = order_payload(local, db, True)
            payload.update({"nro_pedido_exit": record.exit_order_id, "exit_number": record.exit_order_id,
                            "web_number": local.order_number if local.origen_pedido == "B2B" else None, "number": record.exit_order_id,
                            "fecha_registro_exit": record.recorded_at, "estado_registro_exit": effective_state,
                            "customer_reference": record.customer_reference or local.customer_reference,
                            "notes": record.notes or local.notes, "subtotal": float(record.subtotal),
                            "tax_total": float(record.tax_total), "total": float(record.total),
                            "created_at": record.recorded_at or local.created_at,
                            "created_by": payload["created_by"] if local.origen_pedido == "B2B" else (record.source_created_by or "EXIT"), "local_order": local.origen_pedido == "B2B",
                            "workflow": exit_workflow(record, effective_state, delivery, is_web_order(record, local)),
                            "items": [{"sku": line.sku, "description": line.description, "quantity": float(line.quantity),
                                       "served_quantity": float(line.served_quantity or 0),
                                       "pending_quantity": float(line.pending_quantity or 0), "unit": line.unit,
                                       "unit_price": float(line.unit_price), "discount_pct": float(line.discount_pct),
                                       "net_amount": float(line.net_amount) if line.net_amount is not None else None,
                                       "line_total": float(line.line_total if line.line_total is not None else line.quantity * line.unit_price),
                                       "fulfillment_zone": line.fulfillment_zone} for line in record.lines]})
        else:
            payload = {"id": f"exit:{record.exit_order_id}", "number": record.exit_order_id,
                       "exit_number": record.exit_order_id, "web_number": None, "nro_pedido_exit": record.exit_order_id,
                       "local_order": False, "store": delegation_name(record.store_code, record.company_code), "store_code": record.store_code, "company_code": record.company_code, "delegation_code": record.store_code,
                       "customer_code": record.customer_code, "customer": exit_customer_name(record.customer_code),
                       "customer_reference": record.customer_reference, "job_name": record.job_name,
                       "notes": record.notes, "subtotal": float(record.subtotal), "tax_total": float(record.tax_total),
                       "total": float(record.total), "created_at": record.recorded_at or record.source_updated_at,
                       "fecha_registro_exit": record.recorded_at, "origen_pedido": "EXIT",
                       "estado_registro_exit": effective_state,
                       "created_by": record.source_created_by or "EXIT", "items": [
                           {"sku": line.sku, "description": line.description, "quantity": float(line.quantity),
                            "served_quantity": float(line.served_quantity or 0),
                            "pending_quantity": float(line.pending_quantity or 0), "unit": line.unit,
                            "unit_price": float(line.unit_price), "discount_pct": float(line.discount_pct),
                                       "net_amount": float(line.net_amount) if line.net_amount is not None else None,
                            "line_total": float(line.line_total if line.line_total is not None else line.quantity * line.unit_price),
                            "fulfillment_zone": line.fulfillment_zone} for line in record.lines],
                       "documents": [], "history_enabled": settings.show_order_status_history,
                       "history": [{"estado_registro_exit": state, "created_at": stamp, "source": "EXIT", "note": note, "date_only": state == "FACTURADO"}
                                   for state, stamp, note in sorted(exit_events(record, delivery), key=lambda event: event[1], reverse=True)],
                       "workflow": exit_workflow(record, effective_state, delivery)}
        if local and local.delivered_at and payload.get("workflow"):
            for step in payload["workflow"]:
                if step["etapa"] == "ENTREGADO":
                    step["completed_at"] = local.delivered_at
        if local and payload.get("workflow"):
            web_pending = db.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id == local.id, OrderStatusHistory.estado_registro_exit == "PENDIENTE", OrderStatusHistory.source == "WEB")).all()
            payload["workflow"][0]["completed_at"] = max((h.created_at for h in web_pending), default=None)
        payload["auxiliary_reference"] = record.auxiliary_reference
        payload["is_web_order"] = bool(payload.get("is_web_order")) or "PEDIDOGENERADOWEBB2B" in "".join(str(record.auxiliary_reference or "").upper().split())
        result.append(payload)
    for row in local_rows:
        sync_history(db, row, [])
        if row.id in linked:
            continue
        delivery = None
        if row.nro_pedido_exit:
            key = document_key(row.nro_pedido_exit)
            delivery = deliveries.get(key) or deliveries.get(key.split("/")[-1])
        if delivery:
            sequence = ["PENDIENTE", "REGISTRADO", "EN_PROCESO", "EN_PREPARACION", "ATENDIDO", "ENTREGADO", "FACTURADO"]
            target = "FACTURADO" if delivery["is_invoiced"] else "ENTREGADO" if row.delivered_at or (row.origen_pedido != "B2B" and delivery["is_printed"]) else "ATENDIDO"
            current_index = sequence.index(row.estado_registro_exit) if row.estado_registro_exit in sequence else 0
            events = [("ATENDIDO", delivery["attended_at"], f"Albarán {delivery['delivery_number']} generado")]
            if row.origen_pedido != "B2B" and delivery["is_printed"] and delivery.get("delivered_at"):
                events.append(("ENTREGADO", delivery["delivered_at"], f"Albarán {delivery['delivery_number']} impreso"))
            if delivery["is_invoiced"] and delivery["invoiced_at"]:
                events.append(("FACTURADO", delivery["invoiced_at"], f"Albarán {delivery['delivery_number']} facturado"))
            for status, occurred_at, note in events:
                if sequence.index(status) > current_index:
                    db.add(OrderStatusHistory(order_id=row.id, estado_registro_exit=status, source="EXIT", note=note, created_at=occurred_at))
            if sequence.index(target) > current_index:
                row.estado_registro_exit = target
        payload = order_payload(row, db, True)
        payload.update({"web_number": row.order_number if row.origen_pedido == "B2B" else None, "exit_number": row.nro_pedido_exit,
                        "local_order": row.origen_pedido == "B2B"})
        result.append(payload)
    for payload in result:
        key = document_key(payload.get("exit_number") or payload.get("nro_pedido_exit"))
        matched = [row for row in delivery_rows if key and document_key(row.get("order_number")) == key]
        payload["delivery_notes"] = (delivery_notes_payload(matched) if notes_available else None) if user.can_view_delivery_notes else []
    db.commit()
    requested = state.strip().upper()
    groups = {"BORRADOR": {"BORRADOR"}, "PENDIENTE": {"BORRADOR", "PENDIENTE"},
              "EN_PROCESAMIENTO": {"BLOQUEADO", "REGISTRADO", "EN_PROCESO", "EN_PREPARACION"},
              "PENDIENTE_RECOJO": {"ATENDIDO"}, "ENTREGADO": {"ENTREGADO"}, "FACTURADO": {"FACTURADO"}}
    if requested not in {"", "TODOS"}:
        accepted = groups.get(requested, {requested})
        result = [item for item in result if str(item.get("estado_registro_exit") or "").upper() in accepted]
    return sorted(result, key=lambda item: str(item.get("created_at") or ""), reverse=True)


@app.get("/api/v1/orders/{order_id}")
def order_detail(order_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    customer_for(user, db); customer_code = customer_code_for(user, db)
    condition = Order.customer_code == customer_code
    if user.customer_id:
        condition = condition | (Order.customer_id == user.customer_id)
    if user.own_orders_only:
        condition = condition & (Order.user_id == user.id)
    order = db.scalar(select(Order).where(Order.public_id == order_id, condition))
    if not order: raise HTTPException(404, "Pedido no encontrado")
    return order_payload(order, db, True)


@app.post("/api/v1/orders/{order_id}/repeat")
def repeat_order(order_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    customer_for(user, db); customer_code = customer_code_for(user, db)
    condition = Order.customer_code == customer_code
    if user.customer_id:
        condition = condition | (Order.customer_id == user.customer_id)
    if user.own_orders_only:
        condition = condition & (Order.user_id == user.id)
    order = db.scalar(select(Order).where(Order.public_id == order_id, condition))
    if not order: raise HTTPException(404, "Pedido no encontrado")
    old_items = db.scalars(select(OrderItem).where(OrderItem.order_id == order.id)).all(); cart = active_cart(user, db)
    for old in old_items:
        existing = db.scalar(select(CartItem).where(CartItem.cart_id == cart.id, CartItem.product_id == old.product_id))
        if existing: existing.quantity += old.quantity
        else: db.add(CartItem(cart_id=cart.id, product_id=old.product_id, quantity=old.quantity))
    audit(db, user, "ORDER_REPEATED", "ORDER", order.public_id); db.commit(); return cart_payload(cart, user, db)


@app.get("/api/v1/delivery-notes")
def delivery_notes(document_number: str = "", date_from: date | None = None, date_to: date | None = None,
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    customer_for(user, db)
    return fetch_customer_delivery_notes(customer_code_for(user, db), 1000, document_number, date_from, date_to)


@app.get("/api/v1/invoices")
def invoices(document_number: str = "", date_from: date | None = None, date_to: date | None = None,
             user: User = Depends(current_user), db: Session = Depends(get_db)):
    customer_for(user, db)
    return fetch_customer_invoices(customer_code_for(user, db), 1000, document_number,
                                   None if document_number.strip() else date_from,
                                   None if document_number.strip() else date_to)


def customer_documents(kind: str, user: User, db: Session) -> tuple[str, list[dict]]:
    customer_for(user, db)
    code = customer_code_for(user, db)
    normalized = kind.strip().upper()
    if normalized == "ALBARAN":
        return normalized, fetch_customer_delivery_notes(code, 1000)
    if normalized == "FACTURA":
        return normalized, fetch_customer_invoices(code, 1000)
    raise HTTPException(404, "Tipo de documento no válido")


@app.get("/api/v1/documents/{kind}/{document_id}/file")
def document_file(kind: str, document_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    normalized, rows = customer_documents(kind, user, db)
    row = next((item for item in rows if item["id"] == document_id), None)
    if not row:
        raise HTTPException(404, "Documento no encontrado")
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    width, height = A4
    pdf.setTitle(f'{normalized} {row["number"]}')
    pdf.setFont("Helvetica-Bold", 18); pdf.drawString(45, height - 55, "Bermúdez Ulloa")
    pdf.setFont("Helvetica-Bold", 14); pdf.drawString(45, height - 88, f'{normalized} {row["number"]}')
    labels = [
        ("Fecha", row.get("created_at")), ("Estado", row.get("status")),
        ("Delegación", row.get("store_code")), ("Pedido relacionado", row.get("order_number")),
        ("Factura relacionada", row.get("invoice_number")), ("Vencimiento", row.get("due_date")),
        ("Base imponible", f'{row.get("subtotal", 0):.2f} EUR'),
        ("IVA", f'{row.get("tax_total", 0):.2f} EUR'), ("Total", f'{row.get("total", 0):.2f} EUR'),
    ]
    y = height - 125
    for label, value in labels:
        if value is None or value == "":
            continue
        if isinstance(value, (date, datetime)):
            value = value.strftime("%d/%m/%Y %H:%M")
        pdf.setFont("Helvetica-Bold", 10); pdf.drawString(45, y, f"{label}:")
        pdf.setFont("Helvetica", 10); pdf.drawString(175, y, str(value))
        y -= 22
    items = row.get("items") or []
    if items:
        y -= 8; pdf.setFont("Helvetica-Bold", 11); pdf.drawString(45, y, "Detalle despachado"); y -= 20
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(45, y, "Código"); pdf.drawString(110, y, "Descripción")
        pdf.drawRightString(410, y, "Cantidad"); pdf.drawRightString(475, y, "Precio"); pdf.drawRightString(550, y, "Importe")
        y -= 14
        for item in items:
            if y < 65:
                pdf.showPage(); y = height - 55
            description = str(item.get("description") or "")[:48]
            pdf.setFont("Helvetica", 7.5); pdf.drawString(45, y, str(item.get("sku") or ""))
            pdf.drawString(110, y, description); pdf.drawRightString(410, y, f'{item.get("quantity", 0):.2f}')
            pdf.drawRightString(475, y, f'{item.get("unit_price", 0):.2f}'); pdf.drawRightString(550, y, f'{item.get("net_amount", 0):.2f}')
            y -= 13
    pdf.setFont("Helvetica-Oblique", 8)
    pdf.drawString(45, 45, "Documento generado a partir de los datos disponibles en EXIT.")
    pdf.save(); output.seek(0)
    safe_number = "".join(character for character in str(row["number"]) if character.isalnum() or character in "-_")
    filename = f'{normalized.lower()}-{safe_number}.pdf'
    return StreamingResponse(output, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/v1/documents/export")
def export_documents(kind: str, q: str = "", date_from: date | None = None, date_to: date | None = None,
                     user: User = Depends(current_user), db: Session = Depends(get_db)):
    normalized, rows = customer_documents(kind, user, db)
    query = q.strip().lower()
    def included(row: dict) -> bool:
        raw_date = row.get("created_at")
        row_date = raw_date.date() if isinstance(raw_date, datetime) else raw_date
        searchable = " ".join(str(row.get(field) or "") for field in ("number", "order_number", "invoice_number", "status")).lower()
        return ((not query or query in searchable)
                and (not date_from or (row_date is not None and row_date >= date_from))
                and (not date_to or (row_date is not None and row_date <= date_to)))
    rows = [row for row in rows if included(row)]
    workbook = Workbook(); sheet = workbook.active; sheet.title = "Albaranes" if normalized == "ALBARAN" else "Facturas"
    headers = (["Número", "Fecha", "Estado", "Delegación", "Pedido", "Factura", "Vencimiento", "Base imponible", "IVA", "Total"]
               if normalized == "ALBARAN" else
               ["Número", "Fecha", "Delegación", "Vencimiento", "Base imponible", "IVA", "Total"])
    sheet.append(headers)
    for row in rows:
        sheet.append(([row.get("number"), row.get("created_at"), row.get("status"), row.get("store_code"),
                       row.get("order_number"), row.get("invoice_number"), row.get("due_date"),
                       row.get("subtotal"), row.get("tax_total"), row.get("total")]
                      if normalized == "ALBARAN" else
                      [row.get("number"), row.get("created_at"), row.get("store_code"), row.get("due_date"),
                       row.get("subtotal"), row.get("tax_total"), row.get("total")]))
    sheet.freeze_panes = "A2"; sheet.auto_filter.ref = sheet.dimensions
    for column, width in {"A":24,"B":20,"C":22,"D":14,"E":24,"F":24,"G":20,"H":18,"I":14,"J":16}.items():
        sheet.column_dimensions[column].width = width
    output = BytesIO(); workbook.save(output); output.seek(0)
    filename = "albaranes.xlsx" if normalized == "ALBARAN" else "facturas.xlsx"
    media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return StreamingResponse(output, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


INTEGRATION_STATUS_SEQUENCE = ["PENDIENTE", "REGISTRADO", "EN_PROCESO", "EN_PREPARACION", "ATENDIDO", "ENTREGADO", "FACTURADO"]


def require_integration_key(x_integration_key: str | None = Header(default=None)):
    configured = settings.integration_api_key.strip()
    if not configured:
        raise HTTPException(503, "La API de integración no está configurada")
    if not x_integration_key or not secrets.compare_digest(x_integration_key, configured):
        raise HTTPException(401, "Clave de integración incorrecta")


@app.put("/api/v1/integrations/customer-access")
def reset_customer_access(
    data: CustomerAccessReset,
    _: None = Depends(require_integration_key),
    db: Session = Depends(get_db),
):
    code = data.customer_code.strip()
    customer = fetch_customer(code)
    if not customer:
        raise HTTPException(404, "El cliente no existe en EXIT")
    user = db.scalar(select(User).where(
        ((User.erp_customer_code == code) | (func.lower(User.email) == code.lower())),
        User.parent_user_id.is_(None)
    ))
    if not user:
        user = User(email=code.lower(), full_name=code, password_hash="", role="CLIENTE_ADMIN",
                    erp_customer_code=code, customer_id=None, active=True)
        db.add(user)
    user.password_hash = hash_password(data.new_password)
    user.role = "CLIENTE_ADMIN"
    user.customer_id = None
    user.erp_customer_code = code
    user.active = True
    db.flush()
    audit(db, None, "CUSTOMER_ACCESS_RESET", "USER", user.public_id, {"customer_code": code})
    db.commit()
    return {"ok": True, "customer_code": code, "username": user.email}


def integration_order(db: Session, order_id: str | None = None, order_number: str | None = None) -> Order | None:
    """Localiza un pedido por UUID público, número B2B o número EXIT."""
    if order_id:
        identifier = order_id.strip()
        order = db.scalar(select(Order).where(Order.public_id == identifier))
        if not order and identifier.isdigit():
            order = db.get(Order, int(identifier))
        if order:
            return order
    if order_number:
        identifier = order_number.strip()
        return db.scalar(select(Order).where(
            (Order.order_number == identifier) | (Order.nro_pedido_exit == identifier)
        ))
    return None


@app.get("/api/v1/integrations/orders")
def integration_orders(
    estado_registro_exit: str = Query("PENDIENTE", description="Estado o estados separados por coma; usa TODOS para no filtrar"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    include_items: bool = Query(False),
    _: None = Depends(require_integration_key),
    db: Session = Depends(get_db),
):
    requested = {value.strip().upper() for value in estado_registro_exit.split(",") if value.strip()}
    valid = {"BORRADOR", "BLOQUEADO", *INTEGRATION_STATUS_SEQUENCE}
    if "TODOS" in requested:
        requested = set()
    invalid = requested - valid
    if invalid:
        raise HTTPException(422, f"Estado no válido: {', '.join(sorted(invalid))}")
    query = select(Order)
    count_query = select(func.count()).select_from(Order)
    if requested:
        query = query.where(Order.estado_registro_exit.in_(requested))
        count_query = count_query.where(Order.estado_registro_exit.in_(requested))
    total = db.scalar(count_query) or 0
    orders = db.scalars(query.order_by(Order.created_at.desc(), Order.id.desc()).offset(offset).limit(limit)).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "estados": sorted(requested) if requested else ["TODOS"],
        "items": [order_payload(order, db, include_items) for order in orders],
    }


@app.patch("/api/v1/integrations/orders/estado")
def update_order_status_from_integration(
    data: ExternalStatusChange,
    _: None = Depends(require_integration_key),
    db: Session = Depends(get_db),
):
    order = integration_order(db, data.order_id, data.order_number)
    if not order:
        raise HTTPException(404, "Pedido no encontrado")
    requested = data.estado_registro_exit.strip().upper()
    if requested not in {"BLOQUEADO", *INTEGRATION_STATUS_SEQUENCE}:
        allowed = ", ".join(INTEGRATION_STATUS_SEQUENCE)
        raise HTTPException(422, f"Estado no válido. Valores admitidos: {allowed}")
    if requested == "ENTREGADO" and not order.delivered_at:
        raise HTTPException(409, "La entrega debe confirmarse desde Operaciones WEB")
    source = data.source.strip().upper()
    if not source:
        raise HTTPException(422, "El origen de la actualización es obligatorio")

    current = order.estado_registro_exit.strip().upper()
    if requested == "BLOQUEADO":
        if current == "BLOQUEADO":
            return {"changed": False, "order": order_payload(order, db, True)}
        if current != "PENDIENTE":
            raise HTTPException(409, "Solo se puede bloquear un pedido PENDIENTE")
        statuses = ["BLOQUEADO"]
    else:
        if current == "BLOQUEADO":
            if requested != "REGISTRADO":
                raise HTTPException(409, "Un pedido BLOQUEADO solo puede recuperarse como REGISTRADO por esta API")
            current_index = INTEGRATION_STATUS_SEQUENCE.index("PENDIENTE")
        elif current == "BORRADOR":
            current_index = -1
        elif current in INTEGRATION_STATUS_SEQUENCE:
            current_index = INTEGRATION_STATUS_SEQUENCE.index(current)
        else:
            raise HTTPException(409, f"El pedido está en un estado no actualizable: {current}")
        requested_index = INTEGRATION_STATUS_SEQUENCE.index(requested)
        if requested_index < current_index:
            raise HTTPException(409, f"No se puede retroceder de {current} a {requested}")
        if requested_index == current_index:
            return {"changed": False, "order": order_payload(order, db, True)}
        statuses = INTEGRATION_STATUS_SEQUENCE[current_index + 1:requested_index + 1]

    if not order.delivered_at:
        statuses = [status for status in statuses if status != "ENTREGADO"]
    recorded = []
    for status in statuses:
        db.add(OrderStatusHistory(
            order_id=order.id,
            estado_registro_exit=status,
            changed_by_user_id=None,
            source=source,
            note=data.note or f"Estado actualizado por {source}",
            created_at=data.occurred_at or datetime.now(timezone.utc),
        ))
        recorded.append(status)
    order.estado_registro_exit = requested
    if data.nro_pedido_exit:
        order.nro_pedido_exit = data.nro_pedido_exit.strip()
        order.fecha_registro_exit = data.occurred_at or order.fecha_registro_exit or datetime.now(timezone.utc)
    audit(db, None, "ORDER_STATUS_CHANGED_BY_INTEGRATION", "ORDER", order.public_id,
          {"estado_registro_exit": requested, "source": data.source, "recorded": recorded})
    db.commit()
    return {"changed": True, "recorded_statuses": recorded, "order": order_payload(order, db, True)}


ALLOWED_TRANSITIONS = {
    "BORRADOR": {"PENDIENTE"},
    "PENDIENTE": {"REGISTRADO"},
    "REGISTRADO": {"EN_PROCESO", "EN_PREPARACION"},
    "EN_PREPARACION": {"ATENDIDO"},
    "EN_PROCESO": {"ATENDIDO"},
    "ATENDIDO": {"ENTREGADO"},
    "ENTREGADO": {"FACTURADO"},
}


def delivery_notes_payload(rows):
    """Cabeceras de todos los albaranes vinculados, sin líneas ni importes."""
    unique = {}
    for row in rows:
        number = str(row.get("delivery_number") or "").strip()
        if number:
            unique.setdefault(number, {"number": number, "created_at": instant(row.get("attended_at")),
                "status": "FACTURADO" if row.get("is_invoiced") else "EMITIDO" if row.get("is_printed") else "PENDIENTE_EMISION"})
    return list(unique.values())


def matches_order_reference(reference, order):
    def normalized(value):
        return "/".join(part.strip().upper() for part in str(value or "").replace("~", "/").replace("-", "/").split("/"))
    linked_key, order_key = normalized(reference), normalized(order.nro_pedido_exit)
    if not order_key:
        return False
    if "/" in order_key:
        return linked_key == order_key
    parts = linked_key.split("/")
    stamp = order.fecha_registro_exit or order.created_at
    return len(parts) == 3 and parts[-1] == order_key and stamp is not None and parts[0] == str(stamp.year)


def web_store_orders(db: Session, user: User, date_from: date | None, date_to: date | None, state: str, delegation: str = "00") -> list[dict]:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "La fecha desde no puede ser posterior a la fecha hasta")
    query = select(Order).where(Order.origen_pedido == "B2B")
    scope = delegation_scope(user, db)
    if scope is not None:
        query = query.where(or_(*[(Order.company_code == int(company)) & (Order.delegation_code == code) for company, code in scope]) if scope else Order.id == -1)
    if delegation.strip().upper() != "TODAS":
        reference = delegation.strip()
        if ':' in reference:
            company, code = reference.split(':', 1)
            if not company.isdigit():raise HTTPException(422, 'Empresa inválida')
            query = query.where(Order.company_code == int(company), Order.delegation_code == code)
        else:query = query.where(Order.delegation_code == reference)
    if date_from:
        query = query.where(func.date(Order.created_at) >= date_from)
    if date_to:
        query = query.where(func.date(Order.created_at) <= date_to)
    rows = list(db.scalars(query.order_by(Order.created_at.desc(), Order.id.desc())).all())
    linked = [row for row in rows if row.nro_pedido_exit and row.customer_code]
    exit_by_key = {}
    for code in dict.fromkeys(row.customer_code for row in linked):
        customer_rows = [row for row in linked if row.customer_code == code]
        try:
            records = fetch_customer_exit_orders(code, min(row.created_at.date() for row in customer_rows), datetime.now(timezone.utc).date())
            for record in records:
                exit_by_key[(code, record.exit_order_id.replace("~", "/").upper())] = record
        except Exception:
            logger.exception("No se pudieron enriquecer los pedidos WEB del cliente %s", code)
    deliveries = {}
    delivery_rows = {}
    notes_available = True
    if linked:
        try:
            for delivery in fetch_delivery_statuses_for_orders([row.nro_pedido_exit for row in linked]):
                key = str(delivery["order_number"]).replace("~", "/").upper()
                deliveries.setdefault(key, delivery)
                delivery_rows.setdefault(key, []).append(delivery)
        except Exception:
            notes_available = False
            logger.exception("No se pudieron consultar los albaranes; se conserva la entrega confirmada en WEB")
    # Los registros antiguos pueden guardar solo NumeroPedido, sin ejercicio/serie.
    customer_notes = {}
    fallback_failed = set()
    for code in dict.fromkeys(row.customer_code for row in linked
                             if not delivery_rows.get((row.nro_pedido_exit or "").replace("~", "/").upper())):
        try:
            customer_notes[code] = fetch_customer_delivery_statuses(code)
        except Exception:
            fallback_failed.add(code)
            logger.exception("No se pudieron consultar los albaranes del cliente %s", code)
    linked_notes = {}
    for row in linked:
        key = (row.nro_pedido_exit or "").replace("~", "/").strip().upper()
        matched = delivery_rows.get(key, [])
        if not matched:
            matched = [note for note in customer_notes.get(row.customer_code, [])
                       if matches_order_reference(note.get("order_number"), row)]
        linked_notes[row.id] = matched
    requested = state.strip().upper()
    groups = {"EN_PROCESAMIENTO": {"BLOQUEADO", "REGISTRADO", "EN_PROCESO", "EN_PREPARACION"}, "PENDIENTE_RECOJO": {"ATENDIDO"}}
    result = []
    for row in rows:
        sync_history(db, row, [])
        order_notes = linked_notes.get(row.id, [])
        delivery = order_notes[0] if order_notes else None
        if delivery:
            if delivery["is_invoiced"]:
                row.estado_registro_exit = "FACTURADO"
            elif row.delivered_at:
                row.estado_registro_exit = "ENTREGADO"
            else:
                row.estado_registro_exit = "ATENDIDO"
            sync_history(db, row, [("ATENDIDO", instant(delivery["attended_at"]), f"Albarán {delivery['delivery_number']} generado")] if delivery.get("attended_at") else [])
        payload = order_payload(row, db, include_items=True, history_for_operator=True)
        payload["delivery_notes"] = delivery_notes_payload(order_notes) if notes_available and row.customer_code not in fallback_failed else None
        record = exit_by_key.get((row.customer_code, (row.nro_pedido_exit or "").replace("~", "/").upper()))
        if record and (record.company_code, record.store_code) == (row.company_code, row.delegation_code):
            payload["fecha_registro_exit"] = record.recorded_at
            payload["auxiliary_reference"] = record.auxiliary_reference
        if row.delivered_at and row.estado_registro_exit != "FACTURADO":
            payload["estado_registro_exit"] = "ENTREGADO"
        actual = payload["estado_registro_exit"]
        if requested not in {"", "TODOS"} and actual not in groups.get(requested, {requested}):
            continue
        result.append(payload)
    if rows:
        db.commit()
    return result


@app.get("/api/v1/store/orders/delegations")
def order_delegations(user: User = Depends(require_roles("OPERADOR_TIENDA", "ADMIN")), db: Session = Depends(get_db)):
    return [row for row in stores(user, db) if can_operate_delegation(user, db, row['company_code'], row['code'])]


@app.get("/api/v1/store/orders")
def store_orders(view: str = Query("active_kardex", pattern="^(active_kardex|active_sga|attended|web)$"),
                 date_from: date | None = None, date_to: date | None = None,
                 state: str = Query("TODOS"),
                 delegation: str = Query("00", min_length=1, max_length=40),
                 user: User = Depends(require_roles("OPERADOR_TIENDA", "ADMIN")), db: Session = Depends(get_db)):
    if view == "web":
        return web_store_orders(db, user, date_from, date_to, state, delegation)
    try:
        records = fetch_exit_orders_live(view, date_from, date_to)
        records = [record for record in records if can_operate_delegation(user, db, record.company_code, record.store_code)]
    except Exception:
        if view != "web":
            raise
        logger.exception("No se pudo consultar EXIT; mostrando los pedidos WEB guardados")
        records = []
    kardex_timings = fetch_kardex_timings([sales_order_number(record.exit_order_id) for record in records])
    delivery_by_order: dict[str, dict] = {}
    all_delivery_rows: dict[str, list] = {}
    if records:
        for delivery in fetch_delivery_statuses_for_orders([record.exit_order_id for record in records]):
            key = str(delivery["order_number"]).replace("~", "/").upper()
            delivery_by_order.setdefault(key, delivery)
            all_delivery_rows.setdefault(key, []).append(delivery)
    keys = [key for record in records for key in (record.exit_order_id, record.customer_reference or "")]
    local_orders = list(db.scalars(select(Order).where((Order.nro_pedido_exit.in_(keys)) | (Order.order_number.in_(keys)))).all()) if keys else []
    local_by_key = {key.upper(): row for row in local_orders for key in (row.nro_pedido_exit, row.order_number) if key}
    def local_record(record):
        return local_by_key.get(record.exit_order_id.upper()) or local_by_key.get((record.customer_reference or "").upper())
    def operational_state(record) -> str:
        delivery = delivery_by_order.get(record.exit_order_id.upper())
        if delivery and delivery["is_invoiced"]:
            return "FACTURADO"
        local = local_record(record)
        if local and local.delivered_at:
            return "ENTREGADO"
        if delivery and delivery["is_printed"] and not is_web_order(record, local):
            return "ENTREGADO"
        if delivery:
            return "ATENDIDO"
        if record.estado_registro_exit == "ATENDIDO":
            return "ATENDIDO"
        served = [line.served_quantity or Decimal("0") for line in record.lines]
        return "EN_PROCESO" if any(quantity > 0 for quantity in served) else "PENDIENTE"
    if view in {"active_kardex", "active_sga"}:
        records = [record for record in records if operational_state(record) not in {"ENTREGADO", "FACTURADO"}]
    elif view == "attended":
        records = [record for record in records if operational_state(record) in {"ATENDIDO", "ENTREGADO", "FACTURADO"}]
    if view == "active_kardex":
        records = [record for record in records if any(
            step["stage"] == "EN_PREPARACION" and step["occurred_at"]
            for step in dispatch_timing(
                record, delivery_by_order.get(record.exit_order_id.upper()),
                kardex_started_at=kardex_timings.get(sales_order_number(record.exit_order_id), {}).get("kardex_started_at"),
            )["operational_workflow"]
        )]
    web_keys = {key.upper() for record in records for key in (record.exit_order_id, record.customer_reference or "") if key}
    if view == "web" and state.strip().upper() not in {"", "TODOS"}:
        requested = state.strip().upper()
        groups = {"EN_PROCESAMIENTO": {"EN_PROCESO"}, "PENDIENTE_RECOJO": {"ATENDIDO"}}
        accepted = groups.get(requested, {requested})
        records = [record for record in records if requested != "PENDIENTE" and (requested == "REGISTRADO" or operational_state(record) in accepted)]
    customer_names: dict[str, str] = {}
    for code in dict.fromkeys(record.customer_code for record in records):
        try:
            customer_names[code] = exit_customer_name(code)
        except Exception:
            customer_names[code] = code
    result = [{
        "id": record.exit_order_id, "number": record.order_number,
        "store": delegation_name(record.store_code, record.company_code), "store_code": record.store_code, "company_code": record.company_code, "delegation_code": record.store_code, "customer_code": record.customer_code,
        "customer": customer_names.get(record.customer_code, record.customer_code),
        "created_by": record.source_created_by or "EXIT", "created_at": record.recorded_at,
        "customer_reference": record.customer_reference, "auxiliary_reference": record.auxiliary_reference,
        "is_web_order": "PEDIDOGENERADOWEBB2B" in "".join(str(record.auxiliary_reference or "").upper().split()),
        "notes": record.notes,
        "subtotal": float(record.subtotal), "tax_total": float(record.tax_total), "total": float(record.total),
        "nro_pedido_exit": record.exit_order_id, "fecha_registro_exit": record.recorded_at,
        **dispatch_timing(record, delivery_by_order.get(record.exit_order_id.upper()),
                          kardex_started_at=kardex_timings.get(sales_order_number(record.exit_order_id), {}).get("kardex_started_at"),
                          delivered_at=local_record(record).delivered_at if local_record(record) else None,
                          web_order=is_web_order(record, local_record(record))),
        **kardex_timings.get(sales_order_number(record.exit_order_id), {}),
        "delivery_notes": delivery_notes_payload(all_delivery_rows.get(record.exit_order_id.upper(), [])),
        "delivery_order_id": local_record(record).public_id if local_record(record) else None,
        "delivered_at": (local_record(record).delivered_at if local_record(record) else None) or next((stamp for stage, stamp, _ in exit_events(record, delivery_by_order.get(record.exit_order_id.upper()), is_web_order(record, local_record(record))) if stage == "ENTREGADO"), None),
        "origen_pedido": "EXIT", "estado_registro_exit": operational_state(record),
        "items": [{"sku": line.sku, "description": line.description, "quantity": float(line.quantity),
                   "served_quantity": float(line.served_quantity or 0),
                   "pending_quantity": float(line.pending_quantity or 0), "unit": line.unit,
                   "unit_price": float(line.unit_price), "line_total": float(line.line_total or 0),
                   "fulfillment_zone": line.fulfillment_zone} for line in record.lines],
    } for record in records]


    return result


def operator_web_order(db: Session, order_id: str, user: User) -> Order:
    order = db.scalar(select(Order).where(Order.public_id == order_id, Order.origen_pedido == "B2B").with_for_update())
    if not order or not can_operate_delegation(user, db, order.company_code, order.delegation_code):
        raise HTTPException(404, "Pedido WEB no encontrado")
    return order


@app.get("/api/v1/store/orders/{order_id}/delivery-note")
def operator_order_delivery_note(order_id: str, number: str = Query(min_length=1, max_length=100),
        user: User = Depends(require_roles("OPERADOR_TIENDA", "ADMIN")), db: Session = Depends(get_db)):
    order = db.scalar(select(Order).where(Order.public_id == order_id, Order.origen_pedido == "B2B"))
    if not order or not can_operate_delegation(user, db, order.company_code, order.delegation_code) or not order.nro_pedido_exit or not order.customer_code:
        raise HTTPException(404, "Pedido EXIT no encontrado")
    def key(value):
        return str(value or "").replace("~", "/").replace("-", "/").strip().upper()
    wanted = key(number)
    try:
        documents = fetch_customer_delivery_notes(order.customer_code, 1000, number)
    except Exception as exc:
        raise HTTPException(503, "No se pudo consultar el albarán en EXIT") from exc
    for document in documents:
        if key(document.get("number")) == wanted and matches_order_reference(document.get("order_number"), order):
            return document
    raise HTTPException(404, "El albarán no pertenece a este pedido")


@app.patch("/api/v1/store/orders/{order_id}/pickup")
def change_web_pickup(order_id: str, data: PickupChange,
                      user: User = Depends(require_roles("OPERADOR_TIENDA", "ADMIN")), db: Session = Depends(get_db)):
    order = db.scalar(select(Order).where(Order.public_id == order_id, Order.origen_pedido == "B2B").with_for_update())
    if not order or not can_operate_delegation(user, db, order.company_code, order.delegation_code):
        raise HTTPException(404, "Pedido WEB no encontrado")
    if order.delivered_at or order.estado_registro_exit in {"ENTREGADO", "FACTURADO"}:
        raise HTTPException(409, "No se puede cambiar la recogida de un pedido ya entregado")
    if data.pickup_date and data.pickup_date <= datetime.now(ZoneInfo("Europe/Madrid")).date():
        raise HTTPException(422, "La fecha programada debe ser desde mañana")
    if data.pickup_date and not scheduled_date_open(db, order.company_code, order.delegation_code, data.pickup_date):
        raise HTTPException(422, "La sede está cerrada en esa fecha")
    before = order.pickup_date.isoformat() if order.pickup_date else "Inmediata"
    after = data.pickup_date.isoformat() if data.pickup_date else "Inmediata"
    if before != after or order.attention_deadline_at is None:
        previous_deadline = order.attention_deadline_at.isoformat() if order.attention_deadline_at else None
        order.pickup_date = data.pickup_date
        assign_attention_deadline(order, db, operator_override=data.pickup_date is None)
        local_deadline = order.attention_deadline_at.astimezone(ZoneInfo("Europe/Madrid")).strftime("%d/%m/%Y %H:%M")
        note = f"Recogida cambiada por operador: {before} → {after}. Límite de atención: {local_deadline}"
        db.add(OrderStatusHistory(order_id=order.id, estado_registro_exit=order.estado_registro_exit, changed_by_user_id=user.id, source="WEB", note=note))
        audit(db, user, "ORDER_PICKUP_CHANGED", "ORDER", order.public_id, {"previous": before, "pickup": after, "previous_attention_deadline_at": previous_deadline, "attention_deadline_at": order.attention_deadline_at.isoformat(), "preparation_minutes": order.preparation_minutes_snapshot})
        db.commit()
    return order_payload(order, db, True)


@app.patch("/api/v1/store/orders/{order_id}/registration")
def change_web_registration(order_id: str, data: WebOrderRegistrationChange,
                            user: User = Depends(require_roles("OPERADOR_TIENDA", "ADMIN")), db: Session = Depends(get_db)):
    order = operator_web_order(db, order_id, user)
    if data.state == "PENDIENTE" and (order.estado_registro_exit not in {"REGISTRADO", "BLOQUEADO"} or order.delivered_at):
        raise HTTPException(409, "Solo se puede volver a PENDIENTE desde REGISTRADO o BLOQUEADO y sin entrega confirmada")
    previous = {"state": order.estado_registro_exit, "exit_order_number": order.nro_pedido_exit, "exit_registered_at": order.fecha_registro_exit.isoformat() if order.fecha_registro_exit else None}
    number = (data.exit_order_number or "").strip().replace("~", "/").upper()
    if data.state == "REGISTRADO":
        if not number:
            raise HTTPException(422, "Introduce el número de pedido EXIT")
        duplicate = db.scalar(select(Order.id).where(Order.id != order.id, func.upper(func.replace(Order.nro_pedido_exit, "~", "/")) == number))
        if duplicate:
            raise HTTPException(409, "Ese número EXIT ya está vinculado a otro pedido")
        registered = data.exit_registered_at
        if registered is None:
            # Compatibilidad con integraciones existentes que solo envían número.
            registered = (order.fecha_registro_exit if order.estado_registro_exit == "REGISTRADO" and order.nro_pedido_exit == number else None) or datetime.now(timezone.utc)
            if registered.tzinfo is None:
                registered = registered.replace(tzinfo=timezone.utc)
        elif registered.tzinfo is None:
            # El formulario usa la hora de la sede, con independencia del navegador.
            local = registered.replace(tzinfo=ZoneInfo("Europe/Madrid"))
            if local.astimezone(timezone.utc).astimezone(ZoneInfo("Europe/Madrid")).replace(tzinfo=None) != registered:
                raise HTTPException(422, "La hora indicada no existe por el cambio de horario; revisa la fecha y hora EXIT")
            registered = local
        registered = registered.astimezone(timezone.utc)
        if registered > datetime.now(timezone.utc) + timedelta(minutes=1):
            raise HTTPException(422, "La fecha y hora de registro EXIT no pueden ser futuras")
        previous_registered = order.fecha_registro_exit
        if previous_registered and previous_registered.tzinfo is None:
            previous_registered = previous_registered.replace(tzinfo=timezone.utc)
        if order.estado_registro_exit == "REGISTRADO" and order.nro_pedido_exit == number and previous_registered == registered:
            return order_payload(order, db, True, history_for_operator=True)
        order.nro_pedido_exit = number
        order.fecha_registro_exit = registered
        order.sync_status = SyncStatus.synced
    else:
        order.nro_pedido_exit = None
        order.fecha_registro_exit = None
        order.sync_status = SyncStatus.pending
        for item in db.scalars(select(OrderItem).where(OrderItem.order_id == order.id)).all():
            item.served_quantity = Decimal("0")
            item.pending_quantity = item.quantity
    order.delivered_at = None
    order.estado_registro_exit = data.state
    events = list(db.scalars(select(IntegrationOutbox).where(IntegrationOutbox.aggregate_type == "ORDER", IntegrationOutbox.aggregate_id == order.public_id)).all())
    for event in events:
        event.sync_status = order.sync_status
        event.last_error = None
    if data.state == "PENDIENTE" and not any(event.event_type == "ORDER_CREATED" for event in events):
        db.add(IntegrationOutbox(aggregate_type="ORDER", aggregate_id=order.public_id, event_type="ORDER_CREATED", payload={"order_number": order.order_number, "customer_erp_id": order.customer_code, "store": order.delegation_code}, sync_status=SyncStatus.pending))
    history_note = (f"Registro manual en EXIT: {number}. Vínculo guardado por {user.full_name}" if data.state == "REGISTRADO" else
                    f"Vínculo EXIT actualizado manualmente: {previous['exit_order_number'] or 'sin vínculo'} → sin vínculo")
    db.add(OrderStatusHistory(order_id=order.id, estado_registro_exit=data.state, changed_by_user_id=user.id,
                             source="WEB", created_at=order.fecha_registro_exit if data.state == "REGISTRADO" else datetime.now(timezone.utc), note=history_note))
    audit(db, user, "ORDER_REGISTRATION_CHANGED", "ORDER", order.public_id, {"previous": previous, "state": data.state, "exit_order_number": order.nro_pedido_exit, "exit_registered_at": order.fecha_registro_exit.isoformat() if order.fecha_registro_exit else None})
    from sqlalchemy.exc import IntegrityError
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "No se pudo guardar el vínculo; comprueba que el número EXIT no esté duplicado")
    return order_payload(order, db, True, history_for_operator=True)


@app.delete("/api/v1/store/orders/{order_id}")
def delete_operator_web_order(order_id: str, user: User = Depends(require_roles("OPERADOR_TIENDA", "ADMIN")), db: Session = Depends(get_db)):
    order = operator_web_order(db, order_id, user)
    if order.estado_registro_exit != "PENDIENTE" or order.nro_pedido_exit:
        raise HTTPException(409, "Solo se pueden eliminar pedidos WEB pendientes sin vínculo EXIT")
    number = order.order_number
    audit(db, user, "ORDER_DELETED_BY_OPERATOR", "ORDER", order.public_id, {"number": number})
    for model, condition in (
        (IntegrationOutbox, (IntegrationOutbox.aggregate_type == "ORDER") & (IntegrationOutbox.aggregate_id == order.public_id)),
        (OrderItem, OrderItem.order_id == order.id),
        (OrderStatusHistory, OrderStatusHistory.order_id == order.id),
    ):
        for row in db.scalars(select(model).where(condition)).all():
            db.delete(row)
    db.flush()
    db.delete(order)
    db.commit()
    return {"ok": True, "number": number}


@app.post("/api/v1/store/orders/{order_id}/retry")
def retry_web_order(order_id: str, user: User = Depends(require_roles("OPERADOR_TIENDA", "ADMIN")), db: Session = Depends(get_db)):
    order = db.scalar(select(Order).where(Order.public_id == order_id).with_for_update())
    if not order or (not can_operate_delegation(user, db, order.company_code, order.delegation_code)):
        raise HTTPException(404, "Pedido no encontrado")
    if order.origen_pedido != "B2B" or order.nro_pedido_exit or order.delivered_at or order.estado_registro_exit not in {"PENDIENTE", "REGISTRADO", "EN_PROCESO"}:
        raise HTTPException(409, "Solo se pueden reactivar pedidos WEB sin registro en EXIT")
    try:
        records = fetch_exit_orders_live("web", order.created_at.date(), date.today(), customer_code=order.customer_code)
    except Exception:
        raise HTTPException(503, "No se pudo verificar EXIT. Reintenta cuando esté disponible para evitar duplicar el pedido")
    if any((record.customer_reference or "").strip().upper() == order.order_number.upper() for record in records):
        raise HTTPException(409, "El pedido ya existe en EXIT. Actualiza el listado antes de continuar")
    previous = order.estado_registro_exit
    order.estado_registro_exit = "PENDIENTE"
    order.sync_status = SyncStatus.pending
    event = db.scalar(select(IntegrationOutbox).where(IntegrationOutbox.aggregate_type == "ORDER", IntegrationOutbox.aggregate_id == order.public_id, IntegrationOutbox.event_type == "ORDER_CREATED").order_by(IntegrationOutbox.id.desc()).with_for_update())
    if event:
        event.sync_status = SyncStatus.pending
        event.last_error = None
    else:
        db.add(IntegrationOutbox(aggregate_type="ORDER", aggregate_id=order.public_id, event_type="ORDER_CREATED", payload={"order_number": order.order_number, "customer_erp_id": order.customer_code, "store": order.delegation_code}, sync_status=SyncStatus.pending))
    db.add(OrderStatusHistory(order_id=order.id, estado_registro_exit="PENDIENTE", changed_by_user_id=user.id, source="WEB", note="Procesamiento del robot habilitado nuevamente por operaciones"))
    audit(db, user, "ORDER_RETRY_REQUESTED", "ORDER", order.public_id, {"previous_state": previous})
    db.commit()
    return order_payload(order, db, True)


@app.post("/api/v1/store/orders/delivery")
def confirm_delivery(data: DeliveryConfirmation, user: User = Depends(require_roles("OPERADOR_TIENDA", "ADMIN")), db: Session = Depends(get_db)):
    order = db.scalar(select(Order).where((Order.public_id == data.order_id) | (Order.nro_pedido_exit == data.order_id)).with_for_update())
    if order is None:
        records = fetch_exit_orders_live("web", data.order_date, data.order_date)
        record = next((r for r in records if r.exit_order_id == data.order_id), None)
        if not record or "PEDIDOGENERADOWEBB2B" not in "".join(str(record.auxiliary_reference or "").upper().split()):
            raise HTTPException(404, "Pedido WEB no encontrado")
        store = resolve_delegation(record.store_code, company_code=record.company_code)
        if not store or (not can_operate_delegation(user, db, store.company, store.code)):
            raise HTTPException(404, "Pedido no encontrado")
        linked = db.scalar(select(Order).where(Order.order_number == record.customer_reference, Order.origen_pedido == "B2B")) if record.customer_reference else None
        if linked:
            record = record.model_copy(update={"web_order_number": linked.order_number})
        order = upsert_exit_order(db, record, user)
    if not can_operate_delegation(user, db, order.company_code, order.delegation_code):
        raise HTTPException(404, "Pedido no encontrado")
    if order.delivered_at:
        return order_payload(order, db, True)
    if order.estado_registro_exit != "ATENDIDO":
        raise HTTPException(409, "Solo se puede entregar un pedido en estado ATENDIDO")
    stamp = datetime.now(timezone.utc)
    order.delivered_at = stamp
    if order.estado_registro_exit != "FACTURADO":
        order.estado_registro_exit = "ENTREGADO"
    db.add(OrderStatusHistory(order_id=order.id, estado_registro_exit="ENTREGADO", changed_by_user_id=user.id,
                              source="WEB", note="Entrega confirmada en Operaciones", created_at=stamp))
    audit(db, user, "ORDER_DELIVERY_CONFIRMED", "ORDER", order.public_id, {"delivered_at": stamp.isoformat()})
    db.commit()
    return order_payload(order, db, True)


@app.post("/api/v1/store/orders/{order_id}/transitions")
def transition(order_id: str, data: StatusChange, user: User = Depends(require_roles("OPERADOR_TIENDA", "ADMIN")), db: Session = Depends(get_db)):
    order = db.scalar(select(Order).where(Order.public_id == order_id))
    if not order or (not can_operate_delegation(user, db, order.company_code, order.delegation_code)): raise HTTPException(404, "Pedido no encontrado")
    new_status = data.estado_registro_exit.strip().upper()
    if new_status not in ALLOWED_TRANSITIONS.get(order.estado_registro_exit, set()):
        raise HTTPException(409, f"No se puede pasar de {order.estado_registro_exit} a {new_status}")
    order.estado_registro_exit = new_status
    if new_status == "ENTREGADO" and not order.delivered_at:
        order.delivered_at = datetime.now(timezone.utc)
    db.add(OrderStatusHistory(order_id=order.id, estado_registro_exit=new_status, changed_by_user_id=user.id, source="WEB", note=data.note))
    db.add(IntegrationOutbox(aggregate_type="ORDER", aggregate_id=order.public_id, event_type="ORDER_STATUS_CHANGED",
                             payload={"order_number": order.order_number, "nro_pedido_exit": order.nro_pedido_exit, "estado_registro_exit": new_status}, sync_status=SyncStatus.pending))
    db.add(Notification(customer_id=order.customer_id, customer_code=order.customer_code, title=f"Pedido {order.order_number}", message=f"Nuevo estado: {new_status.replace('_', ' ')}"))
    audit(db, user, "ORDER_STATUS_CHANGED", "ORDER", order.public_id, {"estado_registro_exit": new_status}); db.commit()
    return order_payload(order, db, True)

from .line_planning import router as line_planning_router
app.include_router(line_planning_router)
