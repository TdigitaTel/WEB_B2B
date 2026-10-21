"""Filtra documentos e importes antes de enviar respuestas al navegador."""
FINANCIAL = {
    "price", "list_price", "customer_price", "price_with_tax", "price_without_tax", "unit_price",
    "line_total", "subtotal", "tax_total", "net_amount", "gross_amount", "tax_amount", "amount",
    "with_tax", "without_tax", "discount_pct", "discount", "tax_rate", "price_list",
}


def protect_payload(value, permissions, hide_prices=False):
    if isinstance(value, list):
        return [protect_payload(item, permissions, hide_prices) for item in value]
    if not isinstance(value, dict):
        return value
    # El total de una página de catálogo cuenta artículos, no es un importe.
    count_total = "page" in value or ("items" in value and not {"subtotal", "store", "number"}.intersection(value))
    result = {}
    for key, item in value.items():
        if key == "documents" and isinstance(item, list):
            allowed = {"ALBARAN": permissions.get("can_view_delivery_notes", False),
                       "FACTURA": permissions.get("can_view_invoices", False)}
            item = [doc for doc in item if allowed.get(doc.get("type"), False)]
        if key == "invoice_number" and not permissions.get("can_view_invoices", False):
            item = None
        if hide_prices and (key in FINANCIAL or (key == "total" and not count_total)):
            item = None
        result[key] = protect_payload(item, permissions, hide_prices)
    if hide_prices and "available" in result and result.get("type") in {"ALBARAN", "FACTURA"}:
        result["available"] = False
    return result
