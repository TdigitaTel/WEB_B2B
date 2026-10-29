"""Price prominence is a presentation preference shared by each EXIT customer."""
from .models import CustomerCatalogSetting


def highlight_price_without_tax(db, customer_code):
    row = db.get(CustomerCatalogSetting, customer_code) if customer_code else None
    return bool(row and row.highlight_price_without_tax)
