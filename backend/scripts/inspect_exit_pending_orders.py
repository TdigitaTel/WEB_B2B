from app.exit_db import fetch_pending_exit_orders, inspect_exit_order_schema


def main():
    schema = inspect_exit_order_schema()
    orders = fetch_pending_exit_orders(10)
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
    print({"filter": "IdDelegacion='00' AND StatusPedido='S' AND PorcentajePendiente<>100", "resolved_columns": schema, "sample": sample})


if __name__ == "__main__":
    main()
