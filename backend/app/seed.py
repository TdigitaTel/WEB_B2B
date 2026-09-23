import random
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from .auth import hash_password
from .config import settings
from .db import SessionLocal
from .models import (
    Brand, Category, Customer, CustomerAddress, DeliveryNote, Invoice, Inventory,
    Order, OrderItem, OrderStatus, OrderStatusHistory, Product, Store, SyncStatus, User,
)


STORES = [
    ("ALM", "Almeiras", "Av. de Almeiras, Culleredo"),
    ("COR", "A Coruña", "Zona San Diego, A Coruña"),
    ("SAX", "Sanxenxo", "Sanxenxo, Pontevedra"),
    ("FER", "Ferrol", "Ferrol, A Coruña"),
    ("SAN", "Santiago", "Santiago de Compostela"),
]

BRANDS = ["Genebre", "Arco", "Conex Bänninger", "Uponor", "Standard Hidráulica", "Caleffi", "Roca", "Gala", "Geberit", "Grohe", "Wilo", "Grundfos", "Saunier Duval", "Vaillant", "Ferroli", "Junkers Bosch", "Honeywell", "Bahco", "Rothenberger", "Itap"]

FAMILIES = {
    "Tubería": ("Conducción", ["Cobre", "Multicapa", "PVC", "PE-X", "Polietileno"], ["Ø12 mm", "Ø15 mm", "Ø18 mm", "Ø20 mm", "Ø22 mm", "Ø25 mm", "Ø28 mm", "Ø32 mm", "Ø40 mm", "Ø50 mm"]),
    "Racores": ("Conexión", ["Latón", "Multicapa", "Cobre", "Polietileno"], ["1/2\"", "3/4\"", "1\"", "Ø16", "Ø20", "Ø22", "Ø25", "Ø32"]),
    "Racores Marsella": ("Roscado", ["Latón", "Bronce"], ["1/4\" × 20 mm", "3/8\" × 30 mm", "1/2\" × 40 mm", "1/2\" × 60 mm", "3/4\" × 50 mm", "1\" × 80 mm"]),
    "Manguitos": ("Unión", ["Cobre", "Latón", "Galvanizado", "PVC"], ["Ø15", "Ø18", "Ø20", "Ø22", "Ø25", "Ø28", "1/2\"", "3/4\"", "1\""]),
    "Machones": ("Roscado", ["Latón", "Galvanizado", "Inoxidable"], ["1/4\"", "3/8\"", "1/2\"", "3/4\"", "1\"", "1 1/4\"", "1 1/2\"", "2\""]),
    "Codos": ("Cambio de dirección", ["Cobre", "Latón", "Galvanizado", "PVC", "Multicapa"], ["90° Ø15", "90° Ø18", "90° Ø22", "45° Ø22", "90° 1/2\"", "90° 3/4\"", "90° 1\""]),
    "Tes": ("Derivación", ["Cobre", "Latón", "Galvanizado", "PVC", "Multicapa"], ["Ø15×15×15", "Ø18×18×18", "Ø22×22×22", "Ø22×18×22", "1/2\"", "3/4\"", "1\""]),
    "Reducciones": ("Adaptación", ["Latón", "Cobre", "Galvanizado", "PVC"], ["3/4\"-1/2\"", "1\"-3/4\"", "Ø22-18", "Ø28-22", "Ø32-25", "2\"-1 1/2\""]),
    "Entronques": ("Manguera", ["Latón", "Polipropileno"], ["1/2\" × Ø10", "1/2\" × Ø12", "3/4\" × Ø15", "3/4\" × Ø19", "1\" × Ø25", "1 1/4\" × Ø32"]),
    "Válvulas": ("Control", ["Latón", "Acero inoxidable", "PVC"], ["Esfera H-H 1/2\"", "Esfera H-H 3/4\"", "Retención 1/2\"", "Retención 3/4\"", "Compuerta 1\"", "Seguridad 3 bar"]),
    "Bombas": ("Circulación", ["Hierro fundido", "Inoxidable"], ["25-40", "25-60", "32-60", "25-80"]),
    "Calderas": ("Generación térmica", ["Condensación"], ["24 kW", "28 kW", "30 kW", "35 kW"]),
    "Radiadores": ("Emisión térmica", ["Aluminio", "Acero"], ["350 mm", "500 mm", "600 mm", "700 mm"]),
    "Termostatos": ("Regulación", ["Digital", "WiFi", "Modulante"], ["Cableado", "Inalámbrico", "WiFi", "OpenTherm"]),
    "Climatización": ("Aire acondicionado", ["Split", "Multisplit", "Conductos"], ["2,5 kW", "3,5 kW", "5,0 kW", "7,1 kW"]),
    "Herramientas": ("Herramienta profesional", ["Acero", "Aluminio"], ["10\"", "12\"", "14\"", "18\"", "24\""]),
    "Consumibles": ("Instalación", ["PTFE", "Sellador", "Junta", "Abrasivo"], ["Pequeño", "Mediano", "Grande"]),
    "Baño": ("Equipamiento", ["Porcelana", "Latón cromado", "Resina"], ["Estándar", "Compacto", "Suspendido"]),
    "Gas": ("Instalación gas", ["Latón", "Cobre", "Acero"], ["1/2\"", "3/4\"", "Ø15", "Ø18", "Ø22"]),
    "ACS": ("Agua caliente", ["Acero vitrificado", "Inoxidable"], ["50 L", "80 L", "100 L", "150 L", "200 L"]),
}


def chunks(items, size=5000):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def seed():
    rng = random.Random(20260920)
    db = SessionLocal()
    try:
        if (db.scalar(select(func.count()).select_from(Product)) or 0) >= settings.seed_products:
            return

        stores = []
        for code, name, address in STORES:
            store = db.scalar(select(Store).where(Store.code == code))
            if not store:
                store = Store(code=code, name=name, address=address)
                db.add(store)
            stores.append(store)
        db.flush()

        brands = []
        for name in BRANDS:
            brand = db.scalar(select(Brand).where(Brand.name == name)) or Brand(name=name)
            db.add(brand)
            brands.append(brand)
        categories = []
        for name in FAMILIES:
            category = db.scalar(select(Category).where(Category.name == name)) or Category(name=name, slug=name.lower().replace(" ", "-").replace("ó", "o"))
            db.add(category)
            categories.append(category)
        db.flush()
        brand_ids = [b.id for b in brands]
        category_by_name = {c.name: c.id for c in categories}

        product_rows = []
        family_names = list(FAMILIES)
        for i in range(1, settings.seed_products + 1):
            family = family_names[(i - 1) % len(family_names)]
            subfamily, materials, sizes = FAMILIES[family]
            material = materials[(i // len(family_names)) % len(materials)]
            size = sizes[(i * 7) % len(sizes)]
            brand_id = brand_ids[(i * 11) % len(brand_ids)]
            sku = f"B2B{i:06d}"
            name = f"{family[:-1] if family.endswith('s') else family} profesional {material} {size}"
            if family == "Racores Marsella": name = f"Racor Marsella {material} M-H {size}"
            elif family == "Machones": name = f"Machón hexagonal {material} {size}"
            elif family == "Entronques": name = f"Entronque espiga {material} {size}"
            elif family == "Codos": name = f"Codo {material} {size}"
            elif family == "Tes": name = f"Té {material} {size}"
            elif family == "Válvulas": name = f"Válvula {material} {size}"
            base = Decimal(str(0.75 + ((i * 37) % 90000) / 100))
            product_rows.append({
                "erp_id": f"ERP-{i:07d}", "sku": sku, "manufacturer_reference": f"FAB-{(i * 13) % 999999:06d}",
                "ean": f"84{i:011d}"[-13:], "brand_id": brand_id, "category_id": category_by_name[family],
                "family": family, "subfamily": subfamily, "short_description": name,
                "commercial_description": f"{name}. Referencia sintética para pruebas del portal profesional.",
                "technical_description": f"Familia {family}; material {material}; medida {size}; uso profesional.",
                "unit": "UD", "pack_size": Decimal("1"), "list_price": base, "tax_rate": Decimal("21"),
                "attributes": {"material": material, "medida": size, "familia": family},
                "normalized_search": f"{sku} {name} {family} {subfamily} {material} {size}".lower(),
                "active": True, "sync_status": SyncStatus.pending,
            })
        for part in chunks(product_rows):
            db.bulk_insert_mappings(Product, part)
        db.commit()

        product_ids = db.scalars(select(Product.id).order_by(Product.id)).all()
        inventory_rows = []
        for product_id in product_ids:
            for store in stores:
                physical = (product_id * 17 + store.id * 23) % 130
                reserved = min((product_id * 3 + store.id) % 12, physical)
                inventory_rows.append({"product_id": product_id, "store_id": store.id, "physical_qty": physical, "reserved_qty": reserved})
                if len(inventory_rows) >= 5000:
                    db.bulk_insert_mappings(Inventory, inventory_rows)
                    inventory_rows = []
        if inventory_rows:
            db.bulk_insert_mappings(Inventory, inventory_rows)
        db.commit()

        password = hash_password("123456")
        surnames = ["García", "Fernández", "Rodríguez", "López", "Pérez", "Vázquez", "Castro", "Núñez", "Santos", "Iglesias"]
        for i in range(1, settings.seed_customers + 1):
            customer = Customer(
                erp_id=f"CLI{i:05d}", legal_name=f"INSTALACIONES {surnames[i % len(surnames)].upper()} {i:03d}, S.L.",
                trade_name=f"Instalaciones {surnames[i % len(surnames)]} {i}", tax_id=f"B15{i:06d}",
                email=f"compras{i:03d}@cliente.test", phone=f"981{i:06d}",
                billing_address=f"Rúa Profesional {i}, {15000 + i} A Coruña", price_list="PROFESIONAL",
                discount_pct=Decimal(str(5 + (i % 16))), usual_store_id=stores[(i - 1) % len(stores)].id,
                active=True, sync_status=SyncStatus.pending,
            )
            db.add(customer)
            db.flush()
            db.add(User(email=customer.email, password_hash=password, full_name=f"Comprador {surnames[i % len(surnames)]}", role="CLIENTE_ADMIN", customer_id=customer.id, erp_customer_code=customer.erp_id))
            db.add(CustomerAddress(customer_id=customer.id, label="Dirección fiscal", address_type="FISCAL", address=customer.billing_address, city="A Coruña", postal_code=str(15000 + i), is_default=True))
        db.add(User(email="operador@bermudez.test", password_hash=password, full_name="Operador A Coruña", role="OPERADOR_TIENDA", store_id=stores[1].id))
        db.add(User(email="admin@bermudez.test", password_hash=password, full_name="Administrador", role="ADMIN"))
        db.commit()

        customers = db.scalars(select(Customer).order_by(Customer.id)).all()
        users_by_customer = {u.customer_id: u for u in db.scalars(select(User).where(User.customer_id.is_not(None))).all()}
        sample_products = db.scalars(select(Product).order_by(Product.id).limit(500)).all()
        statuses = [OrderStatus.received, OrderStatus.preparing, OrderStatus.ready, OrderStatus.delivered]
        sequence = 1
        for customer in customers:
            user = users_by_customer[customer.id]
            for n in range(2):
                order = Order(order_number=f"WEB-2026-{sequence:06d}", customer_id=customer.id, user_id=user.id,
                              store_id=customer.usual_store_id, status=statuses[(customer.id + n) % len(statuses)],
                              customer_reference=f"OBRA-{customer.id:03d}-{n+1}", job_name=f"Obra cliente {customer.id}",
                              notes="Pedido sintético de demostración", subtotal=0, tax_total=0, total=0,
                              sync_status=SyncStatus.pending)
                db.add(order); db.flush()
                subtotal = Decimal("0")
                for offset in range(4):
                    product = sample_products[(customer.id * 7 + n * 11 + offset) % len(sample_products)]
                    qty = Decimal(str(1 + ((customer.id + offset) % 8)))
                    price = (Decimal(product.list_price) * (Decimal("1") - Decimal(customer.discount_pct) / 100)).quantize(Decimal("0.01"))
                    line = (qty * price).quantize(Decimal("0.01")); subtotal += line
                    db.add(OrderItem(order_id=order.id, product_id=product.id, sku=product.sku,
                                     description=product.short_description, quantity=qty, unit=product.unit,
                                     unit_price=price, discount_pct=customer.discount_pct, tax_rate=product.tax_rate,
                                     line_total=line))
                order.subtotal = subtotal; order.tax_total = (subtotal * Decimal("0.21")).quantize(Decimal("0.01")); order.total = order.subtotal + order.tax_total
                db.add(OrderStatusHistory(order_id=order.id, status=order.status, changed_by_user_id=user.id, note="Estado sintético inicial"))
                if order.status == OrderStatus.delivered:
                    db.add(DeliveryNote(number=f"ALB-2026-{sequence:06d}", customer_id=customer.id, order_id=order.id, store_id=order.store_id, total=order.total))
                    db.add(Invoice(number=f"FAC-2026-{sequence:06d}", customer_id=customer.id, order_id=order.id,
                                   due_date=date.today() + timedelta(days=30), subtotal=order.subtotal,
                                   tax_total=order.tax_total, total=order.total, status="PENDIENTE"))
                sequence += 1
        db.commit()
    finally:
        db.close()
