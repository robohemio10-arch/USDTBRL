from __future__ import annotations

import json
from typing import Any

from smartcrypto.infra.database import SQLiteDatabase


class ReconciliationAuditStore:
    def __init__(self, database: SQLiteDatabase, clock) -> None:
        self.database = database
        self.clock = clock

    def add(
        self,
        *,
        action: str,
        local_status: str,
        local_qty_usdt: float,
        exchange_qty_usdt: float,
        exchange_open_orders: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        with self.database.connect() as conn:
            conn.execute(
                """
                insert into reconciliation_audit(
                    ts, action, local_status, local_qty_usdt, exchange_qty_usdt,
                    exchange_open_orders, details_json
                ) values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.clock(),
                    action,
                    local_status,
                    local_qty_usdt,
                    exchange_qty_usdt,
                    exchange_open_orders,
                    json.dumps(details or {}),
                ),
            )
