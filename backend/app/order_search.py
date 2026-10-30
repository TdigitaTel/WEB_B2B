"""Exact customer order lookup and numeric display ordering (not identity matching)."""
import re


def matches_order_search(row: dict, query: str) -> bool:
    query = query.strip().upper()
    if query.startswith("WEB-"):
        return any(str(row.get(field) or "").strip().upper() == query
                   for field in ("web_number", "order_number", "number"))
    return any(str(row.get(field) or "").strip().replace("~", "/").split("/")[-1] == query
               for field in ("exit_order_number", "exit_number", "nro_pedido_exit"))


def order_number_sort_key(row: dict) -> tuple:
    value = str(row.get("exit_order_number") or row.get("exit_number") or
                row.get("nro_pedido_exit") or row.get("web_number") or row.get("number") or "")
    digits = re.search(r"(\d+)$", value)
    return (int(digits.group(1)) if digits else -1, str(row.get("created_at") or ""), value)
