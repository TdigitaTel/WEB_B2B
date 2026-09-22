from datetime import datetime, timezone
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import audit, create_access_token, current_user, require_roles, verify_password
from .db import get_db
from .erp_db import fetch_product_image, image_media_type
from .models import (
    Cart, CartItem, Customer, DeliveryNote, IntegrationOutbox, Invoice, Notification,
    MaterialArea, MaterialFamily, MaterialProductType, MaterialSubfamily, Order, OrderItem,
    OrderStatus, OrderStatusHistory, Product, ProfessionalRegistrationRequest, Store, SyncStatus, User,
)
from .schemas import CartItemIn, CartItemUpdate, LoginIn, OrderCreate, StatusChange
from .services import PostgresCatalogService, PostgresPriceService, PostgresStockService, product_view

app = FastAPI(title="Bermúdez B2B API", version="1.0.0", openapi_url="/api/v1/openapi.json", docs_url="/docs")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def customer_for(user: User, db: Session) -> Customer:
    if not user.customer_id:
        raise HTTPException(403, "Esta operación requiere una cuenta de cliente")
    customer = db.get(Customer, user.customer_id)
    if not customer or not customer.active:
        raise HTTPException(403, "Cliente inactivo")
    return customer


def active_cart(user: User, db: Session) -> Cart:
    cart = db.scalar(select(Cart).where(Cart.user_id == user.id, Cart.status == "ACTIVE").order_by(Cart.id.desc()))
    if not cart:
        customer = customer_for(user, db)
        cart = Cart(customer_id=customer.id, user_id=user.id, store_id=customer.usual_store_id, status="ACTIVE")
        db.add(cart); db.flush()
    return cart


def cart_payload(cart: Cart, user: User, db: Session) -> dict:
    customer = customer_for(user, db)
    price_service = PostgresPriceService()
    rows = db.execute(select(CartItem, Product).join(Product, Product.id == CartItem.product_id).where(CartItem.cart_id == cart.id).order_by(CartItem.id)).all()
    items, subtotal = [], Decimal("0")
    for item, product in rows:
        price = price_service.price_for(product, customer)
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
    result = {"id": order.public_id, "number": order.order_number, "status": order.status.value,
              "store": store.name, "store_code": store.code, "customer_reference": order.customer_reference,
              "job_name": order.job_name, "notes": order.notes, "subtotal": float(order.subtotal),
              "tax_total": float(order.tax_total), "total": float(order.total), "created_at": order.created_at}
    if include_items:
        result["items"] = [{"sku": item.sku, "description": item.description, "quantity": float(item.quantity),
                            "unit": item.unit, "unit_price": float(item.unit_price), "line_total": float(item.line_total)}
                           for item in db.scalars(select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id)).all()]
        result["history"] = [{"status": h.status.value, "note": h.note, "created_at": h.created_at}
                             for h in db.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id == order.id).order_by(OrderStatusHistory.created_at)).all()]
    return result


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/v1/auth/login")
def login(data: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == data.email.lower()))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Email o contraseña incorrectos")
    user.last_login_at = datetime.now(timezone.utc)
    audit(db, user, "LOGIN", "USER", user.public_id)
    token = create_access_token(user)
    response.set_cookie("b2b_access", token, httponly=True, samesite="lax", secure=False, max_age=8 * 3600)
    db.commit()
    return {"user": {"id": user.public_id, "name": user.full_name, "email": user.email, "role": user.role}, "access_token": token}


@app.post("/api/v1/auth/logout")
def logout(response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    audit(db, user, "LOGOUT", "USER", user.public_id); db.commit(); response.delete_cookie("b2b_access")
    return {"ok": True}


@app.get("/api/v1/account")
def account(user: User = Depends(current_user), db: Session = Depends(get_db)):
    customer = db.get(Customer, user.customer_id) if user.customer_id else None
    return {"user": {"name": user.full_name, "email": user.email, "role": user.role},
            "customer": {"id": customer.public_id, "erp_id": customer.erp_id, "legal_name": customer.legal_name,
                         "trade_name": customer.trade_name, "tax_id": customer.tax_id, "discount_pct": float(customer.discount_pct),
                         "billing_address": customer.billing_address} if customer else None}


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
    return {"items": [product_view(p, customer, db) for p in rows], "total": total, "page": page, "page_size": page_size}


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
    return [{"id": p.public_id, "sku": p.sku, "name": p.short_description,
             "price": float(PostgresPriceService().price_for(p, customer)),
             "area_id": p.material_area_id, "family_id": p.material_family_id,
             "subfamily_id": p.material_subfamily_id,
             "product_type_id": p.material_product_type_id} for p in rows]


@app.get("/api/v1/products/{product_id}")
def product_detail(product_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    product = db.scalar(select(Product).where(Product.public_id == product_id, Product.active.is_(True)))
    if not product: raise HTTPException(404, "Producto no encontrado")
    return product_view(product, customer_for(user, db), db)


@app.get("/api/v1/products/{product_id}/image")
def product_image(product_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    customer_for(user, db)
    product = db.scalar(select(Product).where(Product.public_id == product_id, Product.active.is_(True)))
    if not product:
        raise HTTPException(404, "Producto no encontrado")
    try:
        data = fetch_product_image(product.sku)
    except Exception:
        raise HTTPException(503, "No se pudo consultar la imagen en el ERP")
    if not data:
        raise HTTPException(404, "Imagen no disponible")
    return Response(content=data, media_type=image_media_type(data), headers={"Cache-Control": "private, max-age=86400"})


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
    customer = customer_for(user, db); cart = active_cart(user, db)
    store = db.scalar(select(Store).where(Store.public_id == data.store_id, Store.active.is_(True)))
    if not store: raise HTTPException(404, "Tienda no encontrada")
    rows = db.execute(select(CartItem, Product).join(Product, Product.id == CartItem.product_id).where(CartItem.cart_id == cart.id)).all()
    if not rows: raise HTTPException(400, "El pedido está vacío")
    order = Order(order_number=f"TMP-{cart.public_id[:20]}", customer_id=customer.id, user_id=user.id, store_id=store.id,
                  status=OrderStatus.sent, customer_reference=data.customer_reference, job_name=data.job_name, notes=data.notes,
                  subtotal=0, tax_total=0, total=0, sync_status=SyncStatus.pending)
    db.add(order); db.flush(); order.order_number = f"WEB-{datetime.now().year}-{order.id:07d}"
    subtotal = Decimal("0")
    for cart_item, product in rows:
        price = PostgresPriceService().price_for(product, customer); line = (price * cart_item.quantity).quantize(Decimal("0.01")); subtotal += line
        db.add(OrderItem(order_id=order.id, product_id=product.id, sku=product.sku, description=product.short_description,
                         quantity=cart_item.quantity, unit=product.unit, unit_price=price, discount_pct=customer.discount_pct,
                         tax_rate=product.tax_rate, line_total=line))
        db.delete(cart_item)
    order.subtotal = subtotal; order.tax_total = (subtotal * Decimal("0.21")).quantize(Decimal("0.01")); order.total = order.subtotal + order.tax_total
    db.add(OrderStatusHistory(order_id=order.id, status=order.status, changed_by_user_id=user.id, note="Pedido enviado desde el portal"))
    db.add(Notification(customer_id=customer.id, user_id=user.id, title="Pedido recibido", message=f"Hemos recibido el pedido {order.order_number}."))
    db.add(IntegrationOutbox(aggregate_type="ORDER", aggregate_id=order.public_id, event_type="ORDER_CREATED",
                             payload={"order_number": order.order_number, "customer_erp_id": customer.erp_id, "store": store.code}, sync_status=SyncStatus.pending))
    cart.status = "CONVERTED"
    audit(db, user, "ORDER_CREATED", "ORDER", order.public_id, {"number": order.order_number, "store": store.code})
    db.commit(); return order_payload(order, db, True)


@app.get("/api/v1/orders")
def orders(user: User = Depends(current_user), db: Session = Depends(get_db)):
    customer = customer_for(user, db)
    rows = db.scalars(select(Order).where(Order.customer_id == customer.id).order_by(Order.created_at.desc()).limit(100)).all()
    return [order_payload(o, db) for o in rows]


@app.get("/api/v1/orders/{order_id}")
def order_detail(order_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    customer = customer_for(user, db)
    order = db.scalar(select(Order).where(Order.public_id == order_id, Order.customer_id == customer.id))
    if not order: raise HTTPException(404, "Pedido no encontrado")
    return order_payload(order, db, True)


@app.post("/api/v1/orders/{order_id}/repeat")
def repeat_order(order_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    customer = customer_for(user, db)
    order = db.scalar(select(Order).where(Order.public_id == order_id, Order.customer_id == customer.id))
    if not order: raise HTTPException(404, "Pedido no encontrado")
    old_items = db.scalars(select(OrderItem).where(OrderItem.order_id == order.id)).all(); cart = active_cart(user, db)
    for old in old_items:
        existing = db.scalar(select(CartItem).where(CartItem.cart_id == cart.id, CartItem.product_id == old.product_id))
        if existing: existing.quantity += old.quantity
        else: db.add(CartItem(cart_id=cart.id, product_id=old.product_id, quantity=old.quantity))
    audit(db, user, "ORDER_REPEATED", "ORDER", order.public_id); db.commit(); return cart_payload(cart, user, db)


@app.get("/api/v1/delivery-notes")
def delivery_notes(user: User = Depends(current_user), db: Session = Depends(get_db)):
    customer = customer_for(user, db)
    rows = db.scalars(select(DeliveryNote).where(DeliveryNote.customer_id == customer.id).order_by(DeliveryNote.created_at.desc())).all()
    return [{"id": x.public_id, "number": x.number, "total": float(x.total), "created_at": x.created_at} for x in rows]


@app.get("/api/v1/invoices")
def invoices(user: User = Depends(current_user), db: Session = Depends(get_db)):
    customer = customer_for(user, db)
    rows = db.scalars(select(Invoice).where(Invoice.customer_id == customer.id).order_by(Invoice.created_at.desc())).all()
    return [{"id": x.public_id, "number": x.number, "due_date": x.due_date, "subtotal": float(x.subtotal),
             "tax_total": float(x.tax_total), "total": float(x.total), "status": x.status} for x in rows]


ALLOWED_TRANSITIONS = {
    OrderStatus.sent: {OrderStatus.received, OrderStatus.cancelled},
    OrderStatus.received: {OrderStatus.preparing, OrderStatus.cancelled},
    OrderStatus.preparing: {OrderStatus.partial, OrderStatus.ready, OrderStatus.cancelled},
    OrderStatus.partial: {OrderStatus.preparing, OrderStatus.ready},
    OrderStatus.ready: {OrderStatus.delivered},
}


@app.get("/api/v1/store/orders")
def store_orders(user: User = Depends(require_roles("OPERADOR_TIENDA", "ADMIN")), db: Session = Depends(get_db)):
    stmt = select(Order).order_by(Order.created_at.desc()).limit(200)
    if user.role == "OPERADOR_TIENDA": stmt = stmt.where(Order.store_id == user.store_id)
    return [order_payload(o, db, True) for o in db.scalars(stmt).all()]


@app.post("/api/v1/store/orders/{order_id}/transitions")
def transition(order_id: str, data: StatusChange, user: User = Depends(require_roles("OPERADOR_TIENDA", "ADMIN")), db: Session = Depends(get_db)):
    order = db.scalar(select(Order).where(Order.public_id == order_id))
    if not order or (user.role == "OPERADOR_TIENDA" and order.store_id != user.store_id): raise HTTPException(404, "Pedido no encontrado")
    try: new_status = OrderStatus(data.status)
    except ValueError as exc: raise HTTPException(422, "Estado no válido") from exc
    if new_status not in ALLOWED_TRANSITIONS.get(order.status, set()): raise HTTPException(409, f"No se puede pasar de {order.status.value} a {new_status.value}")
    order.status = new_status; db.add(OrderStatusHistory(order_id=order.id, status=new_status, changed_by_user_id=user.id, note=data.note))
    db.add(Notification(customer_id=order.customer_id, title=f"Pedido {order.order_number}", message=f"Nuevo estado: {new_status.value.replace('_', ' ')}"))
    audit(db, user, "ORDER_STATUS_CHANGED", "ORDER", order.public_id, {"status": new_status.value}); db.commit()
    return order_payload(order, db, True)
