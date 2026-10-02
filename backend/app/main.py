from datetime import date, datetime, timezone
from decimal import Decimal
from functools import lru_cache
from io import BytesIO
import logging
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import audit, create_access_token, current_user, hash_password, require_roles, verify_password
from .config import settings
from .db import get_db
from .erp_db import (
    fetch_customer, fetch_customer_delivery_notes, fetch_customer_delivery_statuses, fetch_customer_invoices,
    fetch_delivery_statuses_for_orders,
    fetch_product_image, fetch_product_price, fetch_product_prices,
    fetch_product_stock, fetch_product_stocks, image_media_type,
)
from .exit_db import fetch_customer_exit_orders, fetch_exit_orders_live
from .models import (
    Cart, CartItem, Customer, IntegrationOutbox, Notification,
    MaterialArea, MaterialFamily, MaterialProductType, MaterialSubfamily, Order, OrderItem,
    OrderStatusHistory, Product, ProfessionalRegistrationRequest, Store, SyncStatus, User,
)
from .schemas import CartItemIn, CartItemUpdate, CustomerAccessReset, ExternalStatusChange, LoginIn, OrderCreate, PasswordChange, StatusChange
from .services import PostgresCatalogService, product_view

app = FastAPI(title="Bermúdez B2B API", version="1.0.0", openapi_url="/api/v1/openapi.json", docs_url="/docs")
logger = logging.getLogger(__name__)

@lru_cache(maxsize=2000)
def exit_customer_name(code: str) -> str:
    customer = fetch_customer(code)
    return (customer or {}).get("trade_name") or (customer or {}).get("legal_name") or code
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def customer_code_for(user: User, db: Session) -> str:
    if user.erp_customer_code:
        return user.erp_customer_code
    if user.customer_id:
        legacy = db.get(Customer, user.customer_id)
        if legacy:
            return legacy.erp_id
    raise HTTPException(403, "Esta operación requiere una cuenta de cliente EXITERP")


def customer_for(user: User, db: Session) -> dict:
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


def _erp_unit_prices(products: list[Product]) -> dict[str, Decimal]:
    try:
        prices = fetch_product_prices([product.sku for product in products])
    except Exception as exc:
        logger.exception("Error consultando precios ERP para el carrito")
        raise HTTPException(503, "No se pudieron consultar los precios del ERP") from exc
    missing = [product.sku for product in products if product.sku not in prices]
    if missing:
        raise HTTPException(409, f"Falta el precio ERP de: {', '.join(missing[:8])}")
    return {sku: Decimal(str(values["without_tax"])) for sku, values in prices.items()}


def cart_payload(cart: Cart, user: User, db: Session) -> dict:
    rows = db.execute(select(CartItem, Product).join(Product, Product.id == CartItem.product_id).where(CartItem.cart_id == cart.id).order_by(CartItem.id)).all()
    prices = _erp_unit_prices([product for _, product in rows]) if rows else {}
    items, subtotal = [], Decimal("0")
    for item, product in rows:
        price = prices[product.sku]
        line = (price * item.quantity).quantize(Decimal("0.01")); subtotal += line
        items.append({"id": item.id, "product_id": product.public_id, "sku": product.sku, "name": product.short_description,
                      "quantity": float(item.quantity), "unit": product.unit, "unit_price": float(price), "line_total": float(line)})
    store = db.get(Store, cart.store_id) if cart.store_id else None
    return {"id": cart.public_id, "store": {"id": store.public_id, "name": store.name} if store else None,
            "items": items, "line_count": len(items), "subtotal": float(subtotal),
            "tax_total": float((subtotal * Decimal("0.21")).quantize(Decimal("0.01"))),
            "total": float((subtotal * Decimal("1.21")).quantize(Decimal("0.01")))}


def order_payload(order: Order, db: Session, include_items: bool = False) -> dict:
    store = db.get(Store, order.store_id)
    customer_name = order.customer_code or "Cliente EXITERP"
    if order.customer_code:
        try:
            erp_customer = fetch_customer(order.customer_code)
            if erp_customer:
                customer_name = erp_customer["trade_name"] or erp_customer["legal_name"] or order.customer_code
        except Exception:
            logger.exception("No se pudo enriquecer el pedido con el cliente EXITERP %s", order.customer_code)
    creator = db.get(User, order.user_id)
    result = {"id": order.public_id, "number": order.order_number,
              "store": store.name, "store_code": store.code, "customer_code": order.customer_code, "customer_reference": order.customer_reference,
              "job_name": order.job_name, "notes": order.notes, "subtotal": float(order.subtotal),
              "tax_total": float(order.tax_total), "total": float(order.total), "created_at": order.created_at,
              "customer": customer_name, "created_by": creator.full_name if creator else "Integración EXIT",
              "nro_pedido_exit": order.nro_pedido_exit, "fecha_registro_exit": order.fecha_registro_exit,
              "origen_pedido": order.origen_pedido, "estado_registro_exit": order.estado_registro_exit}
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
        result["history_enabled"] = settings.show_order_status_history
        if settings.show_order_status_history:
            result["history"] = [{"estado_registro_exit": h.estado_registro_exit, "source": h.source, "note": h.note, "created_at": h.created_at} for h in history]
        result["documents"] = []
        current_state = order.estado_registro_exit.strip().upper()
        visible_stage = {
            "BORRADOR": "PENDIENTE", "PENDIENTE": "PENDIENTE",
            "REGISTRADO": "EN_PROCESAMIENTO", "EN_PROCESO": "EN_PROCESAMIENTO",
            "ATENDIDO": "PENDIENTE_RECOJO", "ENTREGADO": "ENTREGADO", "FACTURADO": "FACTURADO",
        }.get(current_state, "PENDIENTE")
        stage_position = {"PENDIENTE": 0, "EN_PROCESAMIENTO": 1, "PENDIENTE_RECOJO": 2, "ENTREGADO": 3, "FACTURADO": 4}
        pending_dates = [event.created_at for event in history if event.estado_registro_exit in {"BORRADOR", "PENDIENTE"}]
        processing_dates = [event.created_at for event in history if event.estado_registro_exit in {"REGISTRADO", "EN_PROCESO"}]
        pickup_dates = [event.created_at for event in history if event.estado_registro_exit == "ATENDIDO"]
        delivered_dates = [event.created_at for event in history if event.estado_registro_exit == "ENTREGADO"]
        invoice_dates = [event.created_at for event in history if event.estado_registro_exit == "FACTURADO"]
        fallback_date = order.fecha_registro_exit or order.updated_at or order.created_at
        if not processing_dates and stage_position[visible_stage] >= 1:
            processing_dates = [fallback_date]
        if not pickup_dates and stage_position[visible_stage] >= 2:
            pickup_dates = [fallback_date]
        stage_dates = {
            "PENDIENTE": max(pending_dates) if pending_dates else order.created_at,
            "EN_PROCESAMIENTO": max(processing_dates) if processing_dates and stage_position[visible_stage] >= 1 else None,
            "PENDIENTE_RECOJO": max(pickup_dates) if pickup_dates and stage_position[visible_stage] >= 2 else None,
            "ENTREGADO": max(delivered_dates) if delivered_dates and stage_position[visible_stage] >= 3 else None,
            "FACTURADO": max(invoice_dates) if invoice_dates and stage_position[visible_stage] >= 4 else None,
        }
        result["workflow"] = [{"etapa": etapa, "completed_at": completed_at} for etapa, completed_at in stage_dates.items()]
    return result


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/v1/auth/login")
def login(data: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == data.email.strip().lower()))
    if not user or not user.active or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    customer = None
    if user.role not in {"OPERADOR_TIENDA", "ADMIN"}:
        customer = customer_for(user, db)
    user.last_login_at = datetime.now(timezone.utc)
    audit(db, user, "LOGIN", "USER", user.public_id)
    token = create_access_token(user)
    response.set_cookie("b2b_access", token, httponly=True, samesite="lax", secure=False, max_age=8 * 3600)
    db.commit()
    display_name = (customer or {}).get("trade_name") or (customer or {}).get("legal_name") or user.full_name
    return {"user": {"id": user.public_id, "name": display_name, "email": user.email, "role": user.role}, "access_token": token}


@app.post("/api/v1/auth/logout")
def logout(response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    audit(db, user, "LOGOUT", "USER", user.public_id); db.commit(); response.delete_cookie("b2b_access")
    return {"ok": True}


@app.get("/api/v1/account")
def account(user: User = Depends(current_user), db: Session = Depends(get_db)):
    customer = None if user.role in {"OPERADOR_TIENDA", "ADMIN"} else customer_for(user, db)
    display_name = (customer or {}).get("trade_name") or (customer or {}).get("legal_name") or user.full_name
    return {"user": {"id": user.public_id, "name": display_name, "email": user.email, "role": user.role},
            "customer": customer}


@app.patch("/api/v1/account/password")
def change_password(data: PasswordChange, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, "La contraseña actual no es correcta")
    if data.current_password == data.new_password:
        raise HTTPException(400, "La contraseña nueva debe ser diferente")
    user.password_hash = hash_password(data.new_password)
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
    return [{"id": s.public_id, "code": s.code, "name": s.name, "address": s.address} for s in db.scalars(select(Store).where(Store.active.is_(True)).order_by(Store.name)).all()]


@app.get("/api/v1/products")
def products(q: str = "", family: str | None = None, area_id: int | None = None,
             family_id: int | None = None, subfamily_id: int | None = None,
             product_type_id: int | None = None, page: int = 1,
             page_size: int = Query(24, le=100), user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    customer = customer_for(user, db)
    rows, total = PostgresCatalogService(db).search(
        q, page, page_size, family, area_id, family_id, subfamily_id, product_type_id
    )
    product_codes = [product.sku for product in rows]
    try:
        stocks = fetch_product_stocks(product_codes)
    except Exception:
        logger.exception("Error consultando stock ERP para el catalogo")
        raise HTTPException(503, "No se pudo consultar el stock en el ERP")
    try:
        prices = fetch_product_prices(product_codes)
    except Exception:
        logger.exception("Error consultando precios ERP para el catalogo")
        prices = {}
    return {"items": [product_view(p, customer, db, stocks.get(p.sku, []), prices.get(p.sku)) for p in rows], "total": total, "page": page, "page_size": page_size}


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
        .join(MaterialFamily, MaterialFamily.area_id == MaterialArea.id)
        .join(MaterialSubfamily, MaterialSubfamily.family_id == MaterialFamily.id)
        .join(MaterialProductType, MaterialProductType.subfamily_id == MaterialSubfamily.id)
        .join(Product, Product.material_product_type_id == MaterialProductType.id)
        .where(Product.active.is_(True))
        .group_by(MaterialArea.id, MaterialFamily.id, MaterialSubfamily.id, MaterialProductType.id)
        .order_by(MaterialArea.name, MaterialFamily.name, MaterialSubfamily.name, MaterialProductType.name)
    ).all()
    areas: dict[int, dict] = {}
    for area_id, area_code, area_name, family_id, family_code, family_name, subfamily_id, subfamily_code, subfamily_name, type_id, type_code, type_name, count in rows:
        area = areas.setdefault(area_id, {"id": area_id, "code": area_code, "name": area_name, "count": 0, "families": {}})
        family = area["families"].setdefault(family_id, {"id": family_id, "code": family_code, "name": family_name, "count": 0, "subfamilies": {}})
        subfamily = family["subfamilies"].setdefault(subfamily_id, {"id": subfamily_id, "code": subfamily_code, "name": subfamily_name, "count": 0, "product_types": []})
        subfamily["product_types"].append({"id": type_id, "code": type_code, "name": type_name, "count": count})
        subfamily["count"] += count
        family["count"] += count
        area["count"] += count
    result = []
    for area in areas.values():
        area["families"] = list(area["families"].values())
        for family in area["families"]:
            family["subfamilies"] = list(family["subfamilies"].values())
        result.append(area)
    return result


@app.get("/api/v1/search/suggestions")
def suggestions(q: str = Query(min_length=2), user: User = Depends(current_user), db: Session = Depends(get_db)):
    customer = customer_for(user, db)
    rows, _ = PostgresCatalogService(db).search(q, 1, 8, None)
    try:
        prices = fetch_product_prices([p.sku for p in rows])
    except Exception:
        logger.exception("Error consultando precios ERP para sugerencias")
        prices = {}
    return [{"id": p.public_id, "sku": p.sku, "name": p.short_description,
             "price": float(prices.get(p.sku, {}).get("with_tax", 0)),
             "area_id": p.material_area_id, "family_id": p.material_family_id,
             "subfamily_id": p.material_subfamily_id,
             "product_type_id": p.material_product_type_id} for p in rows]


@app.get("/api/v1/products/{product_id}")
def product_detail(product_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    product = db.scalar(select(Product).where(Product.public_id == product_id, Product.active.is_(True)))
    if not product: raise HTTPException(404, "Producto no encontrado")
    try:
        stock = fetch_product_stock(product.sku)
    except Exception:
        logger.exception("Error consultando stock ERP para SKU %s", product.sku)
        raise HTTPException(503, "No se pudo consultar el stock en el ERP")
    try:
        price = fetch_product_price(product.sku)
    except Exception:
        logger.exception("Error consultando precios ERP para SKU %s", product.sku)
        price = None
    return product_view(product, customer_for(user, db), db, stock, price)


@app.get("/api/v1/products/{product_id}/image")
def product_image(product_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    customer_for(user, db)
    product = db.scalar(select(Product).where(Product.public_id == product_id, Product.active.is_(True)))
    if not product:
        raise HTTPException(404, "Producto no encontrado")
    source = settings.product_image_source.lower().strip()
    if source not in {"auto", "postgres", "sqlserver"}:
        raise HTTPException(500, "PRODUCT_IMAGE_SOURCE debe ser auto, postgres o sqlserver")
    if source != "sqlserver" and product.image_data:
        return Response(content=product.image_data, media_type=product.image_media_type or image_media_type(product.image_data),
                        headers={"Cache-Control": "private, max-age=86400", "X-Image-Source": "postgres"})
    if source == "postgres":
        raise HTTPException(404, "Imagen no disponible en PostgreSQL")
    try:
        data = fetch_product_image(product.sku)
    except Exception:
        logger.exception("Error consultando imagen ERP para SKU %s", product.sku)
        raise HTTPException(503, "No se pudo consultar la imagen en el ERP")
    if not data:
        raise HTTPException(404, "Imagen no disponible")
    return Response(content=data, media_type=image_media_type(data), headers={"Cache-Control": "private, max-age=86400", "X-Image-Source": "sqlserver"})


@app.get("/api/v1/cart")
def get_cart(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return cart_payload(active_cart(user, db), user, db)


@app.post("/api/v1/cart/items", status_code=201)
def add_cart_item(data: CartItemIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    product = db.scalar(select(Product).where(Product.public_id == data.product_id, Product.active.is_(True)))
    if not product: raise HTTPException(404, "Producto no encontrado")
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
    customer = customer_for(user, db); customer_code = customer_code_for(user, db); cart = active_cart(user, db)
    store = db.scalar(select(Store).where(Store.public_id == data.store_id, Store.active.is_(True)))
    if not store: raise HTTPException(404, "Tienda no encontrada")
    rows = db.execute(select(CartItem, Product).join(Product, Product.id == CartItem.product_id).where(CartItem.cart_id == cart.id)).all()
    if not rows: raise HTTPException(400, "El pedido está vacío")
    prices = _erp_unit_prices([product for _, product in rows])
    warehouse_by_store = {"ALM": "00", "COR": "01", "FER": "02", "STG": "04", "SAN": "05"}
    warehouse_code = warehouse_by_store.get(store.code.strip().upper(), store.code.strip())
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
    order = Order(order_number=f"TMP-{cart.public_id[:20]}", customer_id=legacy_customer_id(user), customer_code=customer_code, user_id=user.id, store_id=store.id,
                  origen_pedido="B2B", estado_registro_exit=initial_status,
                  customer_reference=data.customer_reference, job_name=data.job_name, notes=data.notes,
                  subtotal=0, tax_total=0, total=0, sync_status=SyncStatus.pending)
    db.add(order); db.flush(); order.order_number = f"WEB-{datetime.now().year}-{order.id:07d}"
    subtotal = Decimal("0")
    for cart_item, product in rows:
        price = prices[product.sku]; line = (price * cart_item.quantity).quantize(Decimal("0.01")); subtotal += line
        db.add(OrderItem(order_id=order.id, product_id=product.id, sku=product.sku, description=product.short_description,
                         quantity=cart_item.quantity, unit=product.unit, unit_price=price, discount_pct=Decimal("0"),
                         tax_rate=product.tax_rate, line_total=line))
        db.delete(cart_item)
    order.subtotal = subtotal; order.tax_total = (subtotal * Decimal("0.21")).quantize(Decimal("0.01")); order.total = order.subtotal + order.tax_total
    history_note = "Pedido guardado como borrador" if data.draft else "Pedido enviado desde el portal"
    db.add(OrderStatusHistory(order_id=order.id, estado_registro_exit=initial_status, changed_by_user_id=user.id, source="WEB", note=history_note))
    if not data.draft:
        db.add(Notification(customer_id=legacy_customer_id(user), customer_code=customer_code, user_id=user.id, title="Pedido recibido", message=f"Hemos recibido el pedido {order.order_number}."))
        db.add(IntegrationOutbox(aggregate_type="ORDER", aggregate_id=order.public_id, event_type="ORDER_CREATED",
                                 payload={"order_number": order.order_number, "customer_erp_id": customer_code, "store": store.code}, sync_status=SyncStatus.pending))
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
    order = db.scalar(select(Order).where(Order.public_id == order_id, condition))
    if not order:
        raise HTTPException(404, "Pedido no encontrado")
    return order


@app.post("/api/v1/orders/{order_id}/submit")
def submit_draft_order(order_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    order = customer_order(order_id, user, db)
    if order.estado_registro_exit != "BORRADOR":
        raise HTTPException(409, "Solo se puede enviar un pedido que esté en borrador")
    order.estado_registro_exit = "PENDIENTE"
    order.sync_status = SyncStatus.pending
    store = db.get(Store, order.store_id)
    db.add(OrderStatusHistory(order_id=order.id, estado_registro_exit="PENDIENTE", changed_by_user_id=user.id, source="WEB", note="Borrador enviado desde el portal"))
    db.add(Notification(customer_id=legacy_customer_id(user), customer_code=order.customer_code, user_id=user.id,
                        title="Pedido recibido", message=f"Hemos recibido el pedido {order.order_number}."))
    db.add(IntegrationOutbox(aggregate_type="ORDER", aggregate_id=order.public_id, event_type="ORDER_CREATED",
                             payload={"order_number": order.order_number, "customer_erp_id": order.customer_code,
                                      "store": store.code if store else ""}, sync_status=SyncStatus.pending))
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
    all_local_rows = db.scalars(select(Order).where(condition).order_by(Order.created_at.desc()).limit(5000)).all()
    local_rows = [row for row in all_local_rows if start <= row.created_at.date() <= end]
    exit_rows = fetch_customer_exit_orders(customer_code, start, end)
    try:
        delivery_rows = fetch_customer_delivery_statuses(customer_code)
    except Exception:
        logger.exception("No se pudieron consultar los albaranes para actualizar el historial")
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
    def exit_workflow(record, current: str | None = None, delivery: dict | None = None) -> list[dict]:
        current = current or record.estado_registro_exit
        positions = {"PENDIENTE": 0, "REGISTRADO": 1, "EN_PROCESO": 1, "ATENDIDO": 2, "ENTREGADO": 3, "FACTURADO": 4}
        position = positions.get(current, 0)
        process_at = record.prepared_at or record.source_updated_at or record.recorded_at
        fallback = ((delivery or {}).get("invoiced_at") or (delivery or {}).get("delivered_at")
                    or (delivery or {}).get("attended_at") or process_at)
        dates = (record.recorded_at or process_at, process_at,
                 (delivery or {}).get("attended_at") or fallback,
                 (delivery or {}).get("delivered_at"),
                 (delivery or {}).get("invoiced_at"))
        return [{"etapa": stage, "completed_at": dates[index] if index <= position else None}
                for index, stage in enumerate(("PENDIENTE", "EN_PROCESAMIENTO", "PENDIENTE_RECOJO", "ENTREGADO", "FACTURADO"))]
    for record in exit_rows:
        external = record.exit_order_id.strip().upper()
        external_key = document_key(external)
        delivery = deliveries.get(external_key) or deliveries.get(external_key.split("/")[-1])
        effective_state = record.estado_registro_exit
        if delivery:
            if delivery["is_invoiced"]:
                effective_state = "FACTURADO"
            elif delivery["is_printed"]:
                effective_state = "ENTREGADO"
            else:
                effective_state = "ATENDIDO"
        local = by_exit.get(external) or by_exit.get(external.split("/")[-1])
        if not local and record.customer_reference:
            local = by_web.get(record.customer_reference.strip().upper())
            if local and not local.nro_pedido_exit:
                local.nro_pedido_exit = record.exit_order_id
                local.fecha_registro_exit = record.recorded_at
        if local:
            linked.add(local.id)
            existing_history = set(db.scalars(select(OrderStatusHistory.estado_registro_exit).where(
                OrderStatusHistory.order_id == local.id
            )).all())
            if record.prepared_at and "EN_PROCESO" not in existing_history:
                db.add(OrderStatusHistory(order_id=local.id, estado_registro_exit="EN_PROCESO", source="EXIT",
                                          note="Pedido preparado en EXIT", created_at=record.prepared_at))
            if delivery:
                document_events = [("ATENDIDO", delivery["attended_at"], f"Albarán {delivery['delivery_number']} generado")]
                if delivery["is_printed"] and delivery["delivered_at"]:
                    document_events.append(("ENTREGADO", delivery["delivered_at"], f"Albarán {delivery['delivery_number']} impreso"))
                if delivery["is_invoiced"] and delivery["invoiced_at"]:
                    document_events.append(("FACTURADO", delivery["invoiced_at"], f"Albarán {delivery['delivery_number']} facturado"))
                sequence = ["PENDIENTE", "REGISTRADO", "EN_PROCESO", "ATENDIDO", "ENTREGADO", "FACTURADO"]
                current_index = sequence.index(local.estado_registro_exit) if local.estado_registro_exit in sequence else 0
                if effective_state in sequence and current_index > sequence.index(effective_state):
                    effective_state = local.estado_registro_exit
                for status, occurred_at, note in document_events:
                    if sequence.index(status) > current_index:
                        db.add(OrderStatusHistory(order_id=local.id, estado_registro_exit=status, source="EXIT",
                                                  note=note, created_at=occurred_at))
                if sequence.index(effective_state) > current_index:
                    local.estado_registro_exit = effective_state
            payload = order_payload(local, db, True)
            payload.update({"nro_pedido_exit": record.exit_order_id, "exit_number": record.exit_order_id,
                            "web_number": local.order_number, "number": record.exit_order_id,
                            "fecha_registro_exit": record.recorded_at, "estado_registro_exit": effective_state,
                            "customer_reference": record.customer_reference or local.customer_reference,
                            "notes": record.notes or local.notes, "subtotal": float(record.subtotal),
                            "tax_total": float(record.tax_total), "total": float(record.total),
                            "created_at": record.recorded_at or local.created_at,
                            "created_by": record.source_created_by or payload["created_by"], "local_order": True,
                            "workflow": exit_workflow(record, effective_state, delivery),
                            "items": [{"sku": line.sku, "description": line.description, "quantity": float(line.quantity),
                                       "served_quantity": float(line.served_quantity or 0),
                                       "pending_quantity": float(line.pending_quantity or 0), "unit": line.unit,
                                       "unit_price": float(line.unit_price),
                                       "line_total": float(line.line_total or line.quantity * line.unit_price),
                                       "fulfillment_zone": line.fulfillment_zone} for line in record.lines]})
        else:
            payload = {"id": f"exit:{record.exit_order_id}", "number": record.exit_order_id,
                       "exit_number": record.exit_order_id, "web_number": None, "nro_pedido_exit": record.exit_order_id,
                       "local_order": False, "store": "Almeiras", "store_code": record.store_code,
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
                            "unit_price": float(line.unit_price),
                            "line_total": float(line.line_total or line.quantity * line.unit_price),
                            "fulfillment_zone": line.fulfillment_zone} for line in record.lines],
                       "documents": [], "history_enabled": False, "workflow": exit_workflow(record, effective_state, delivery)}
        result.append(payload)
    for row in local_rows:
        if row.id in linked:
            continue
        delivery = None
        if row.nro_pedido_exit:
            key = document_key(row.nro_pedido_exit)
            delivery = deliveries.get(key) or deliveries.get(key.split("/")[-1])
        if delivery:
            sequence = ["PENDIENTE", "REGISTRADO", "EN_PROCESO", "ATENDIDO", "ENTREGADO", "FACTURADO"]
            target = "FACTURADO" if delivery["is_invoiced"] else "ENTREGADO" if delivery["is_printed"] else "ATENDIDO"
            current_index = sequence.index(row.estado_registro_exit) if row.estado_registro_exit in sequence else 0
            events = [("ATENDIDO", delivery["attended_at"], f"Albarán {delivery['delivery_number']} generado")]
            if delivery["is_printed"] and delivery["delivered_at"]:
                events.append(("ENTREGADO", delivery["delivered_at"], f"Albarán {delivery['delivery_number']} impreso"))
            if delivery["is_invoiced"] and delivery["invoiced_at"]:
                events.append(("FACTURADO", delivery["invoiced_at"], f"Albarán {delivery['delivery_number']} facturado"))
            for status, occurred_at, note in events:
                if sequence.index(status) > current_index:
                    db.add(OrderStatusHistory(order_id=row.id, estado_registro_exit=status, source="EXIT", note=note, created_at=occurred_at))
            if sequence.index(target) > current_index:
                row.estado_registro_exit = target
        payload = order_payload(row, db, True)
        payload.update({"web_number": row.order_number, "exit_number": row.nro_pedido_exit,
                        "local_order": True})
        result.append(payload)
    db.commit()
    requested = state.strip().upper()
    groups = {"BORRADOR": {"BORRADOR"}, "PENDIENTE": {"BORRADOR", "PENDIENTE"},
              "EN_PROCESAMIENTO": {"REGISTRADO", "EN_PROCESO"},
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
    order = db.scalar(select(Order).where(Order.public_id == order_id, condition))
    if not order: raise HTTPException(404, "Pedido no encontrado")
    return order_payload(order, db, True)


@app.post("/api/v1/orders/{order_id}/repeat")
def repeat_order(order_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    customer_for(user, db); customer_code = customer_code_for(user, db)
    condition = Order.customer_code == customer_code
    if user.customer_id:
        condition = condition | (Order.customer_id == user.customer_id)
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
    return fetch_customer_invoices(customer_code_for(user, db), 1000, document_number, date_from, date_to)


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


INTEGRATION_STATUS_SEQUENCE = ["PENDIENTE", "REGISTRADO", "EN_PROCESO", "ATENDIDO", "ENTREGADO", "FACTURADO"]


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
        (User.erp_customer_code == code) | (func.lower(User.email) == code.lower())
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
    valid = {"BORRADOR", *INTEGRATION_STATUS_SEQUENCE}
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
    if requested not in INTEGRATION_STATUS_SEQUENCE:
        allowed = ", ".join(INTEGRATION_STATUS_SEQUENCE)
        raise HTTPException(422, f"Estado no válido. Valores admitidos: {allowed}")
    source = data.source.strip().upper()
    if not source:
        raise HTTPException(422, "El origen de la actualización es obligatorio")

    current = order.estado_registro_exit
    if current == "BORRADOR":
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

    recorded = []
    for status in INTEGRATION_STATUS_SEQUENCE[current_index + 1:requested_index + 1]:
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
    "REGISTRADO": {"EN_PROCESO"},
    "EN_PROCESO": {"ATENDIDO"},
    "ATENDIDO": {"ENTREGADO"},
    "ENTREGADO": {"FACTURADO"},
}


@app.get("/api/v1/store/orders")
def store_orders(view: str = Query("active_kardex", pattern="^(active_kardex|active_sga|attended|web)$"),
                 date_from: date | None = None, date_to: date | None = None,
                 state: str = Query("PENDIENTE"),
                 user: User = Depends(require_roles("OPERADOR_TIENDA", "ADMIN"))):
    records = fetch_exit_orders_live(view, date_from, date_to)
    delivery_by_order: dict[str, dict] = {}
    if view == "web" and records:
        for delivery in fetch_delivery_statuses_for_orders([record.exit_order_id for record in records]):
            key = str(delivery["order_number"]).replace("~", "/").upper()
            delivery_by_order.setdefault(key, delivery)
    def operational_state(record) -> str:
        delivery = delivery_by_order.get(record.exit_order_id.upper())
        if delivery and delivery["is_invoiced"]:
            return "FACTURADO"
        if delivery and delivery["is_printed"]:
            return "ENTREGADO"
        if delivery:
            return "ATENDIDO"
        if record.estado_registro_exit == "ATENDIDO":
            return "ATENDIDO"
        served = [line.served_quantity or Decimal("0") for line in record.lines]
        return "EN_PROCESO" if any(quantity > 0 for quantity in served) else "PENDIENTE"
    if view == "web" and state.strip().upper() not in {"", "TODOS"}:
        requested = state.strip().upper()
        groups = {"EN_PROCESAMIENTO": {"EN_PROCESO"}, "PENDIENTE_RECOJO": {"ATENDIDO"}}
        accepted = groups.get(requested, {requested})
        records = [record for record in records if operational_state(record) in accepted]
    customer_names: dict[str, str] = {}
    for code in dict.fromkeys(record.customer_code for record in records):
        try:
            customer_names[code] = exit_customer_name(code)
        except Exception:
            customer_names[code] = code
    return [{
        "id": record.exit_order_id, "number": record.order_number,
        "store": "Almeiras", "store_code": "00", "customer_code": record.customer_code,
        "customer": customer_names.get(record.customer_code, record.customer_code),
        "created_by": record.source_created_by or "EXIT", "created_at": record.recorded_at,
        "customer_reference": record.customer_reference, "auxiliary_reference": record.auxiliary_reference,
        "is_web_order": "PEDIDOGENERADOWEBB2B" in "".join(str(record.auxiliary_reference or "").upper().split()),
        "notes": record.notes,
        "subtotal": float(record.subtotal), "tax_total": float(record.tax_total), "total": float(record.total),
        "nro_pedido_exit": record.exit_order_id, "fecha_registro_exit": record.recorded_at,
        "origen_pedido": "EXIT", "estado_registro_exit": operational_state(record),
        "items": [{"sku": line.sku, "description": line.description, "quantity": float(line.quantity),
                   "served_quantity": float(line.served_quantity or 0),
                   "pending_quantity": float(line.pending_quantity or 0), "unit": line.unit,
                   "unit_price": float(line.unit_price), "line_total": float(line.line_total or 0),
                   "fulfillment_zone": line.fulfillment_zone} for line in record.lines],
    } for record in records]


@app.post("/api/v1/store/orders/{order_id}/transitions")
def transition(order_id: str, data: StatusChange, user: User = Depends(require_roles("OPERADOR_TIENDA", "ADMIN")), db: Session = Depends(get_db)):
    order = db.scalar(select(Order).where(Order.public_id == order_id))
    if not order or (user.role == "OPERADOR_TIENDA" and order.store_id != user.store_id): raise HTTPException(404, "Pedido no encontrado")
    new_status = data.estado_registro_exit.strip().upper()
    if new_status not in ALLOWED_TRANSITIONS.get(order.estado_registro_exit, set()):
        raise HTTPException(409, f"No se puede pasar de {order.estado_registro_exit} a {new_status}")
    order.estado_registro_exit = new_status
    db.add(OrderStatusHistory(order_id=order.id, estado_registro_exit=new_status, changed_by_user_id=user.id, source="WEB", note=data.note))
    db.add(IntegrationOutbox(aggregate_type="ORDER", aggregate_id=order.public_id, event_type="ORDER_STATUS_CHANGED",
                             payload={"order_number": order.order_number, "nro_pedido_exit": order.nro_pedido_exit, "estado_registro_exit": new_status}, sync_status=SyncStatus.pending))
    db.add(Notification(customer_id=order.customer_id, customer_code=order.customer_code, title=f"Pedido {order.order_number}", message=f"Nuevo estado: {new_status.replace('_', ' ')}"))
    audit(db, user, "ORDER_STATUS_CHANGED", "ORDER", order.public_id, {"estado_registro_exit": new_status}); db.commit()
    return order_payload(order, db, True)
