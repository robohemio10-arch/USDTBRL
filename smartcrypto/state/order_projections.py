from __future__ import annotations

from typing import Any

from smartcrypto.infra.database import SQLiteDatabase


class OrderProjectionStore:
    def __init__(self, database: SQLiteDatabase, clock) -> None:
        self.database = database
        self.clock = clock

    def replace_table(self, table_name: str, orders: list[dict[str, Any]]) -> None:
        with self.database.connect() as conn:
            conn.execute(f"delete from {table_name}")
            for order in orders:
                conn.execute(
                    f"""
                    insert into {table_name}(
                        side, order_type, price_brl, qty_usdt, brl_value, reason, status, updated_at
                    ) values (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order.get("side"),
                        order.get("order_type"),
                        order.get("price_brl"),
                        order.get("qty_usdt"),
                        order.get("brl_value"),
                        order.get("reason"),
                        order.get("status", "planned"),
                        self.clock(),
                    ),
                )

    def replace_planned_orders(self, orders: list[dict[str, Any]]) -> None:
        self.replace_table("planned_orders", orders)
        self.replace_table("pending_orders", orders)

    def replace_pending_orders(self, orders: list[dict[str, Any]]) -> None:
        self.replace_planned_orders(orders)
