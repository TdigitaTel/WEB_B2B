from app.exit_db import fetch_pending_exit_orders, inspect_exit_order_schema


def main():
    schema = inspect_exit_order_schema()
    error = None
    try:
        orders = fetch_pending_exit_orders(10)
    except Exception as exc:
        orders = []
        error = str(exc)
    sample = [{
        "exit_order_id": order.exit_order_id,
        "order_number": order.order_number,
        "customer_code": order.customer_code,
        "store_code": order.store_code,
        "kardex_lines": sum(1 for line in order.lines if line.fulfillment_zone == "KARDEX"),
        "sga_lines": sum(1 for line in order.lines if line.fulfillment_zone == "SGA"),
        "other_lines": sum(1 for line in order.lines if line.fulfillment_zone == "OTROS"),
        "total": float(order.total),
    } for order in orders]
    print({"filter": "IdDelegacion='00' (pedidos recientes, con todas sus líneas)",
           "schema": schema, "error": error, "sample": sample})


if __name__ == "__main__":
    main()
