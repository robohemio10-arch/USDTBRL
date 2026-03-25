from __future__ import annotations

import json
from typing import Any

import pandas as pd

from smartcrypto.infra.database import SQLiteDatabase


class DispatchLockStore:
    def __init__(
        self,
        database: SQLiteDatabase,
        clock,
        active_statuses: tuple[str, ...],
    ) -> None:
        self.database = database
        self.clock = clock
        self.active_statuses = active_statuses

    def upsert(
        self,
        *,
        bot_order_id: str,
        side: str,
        reason: str,
        order_type: str,
        client_order_id: str | None = None,
        status: str = "pending_submit",
        requested_price_brl: float | None = None,
        requested_qty_usdt: float | None = None,
        requested_brl_value: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        now = self.clock()
        payload = json.dumps(details or {})
        with self.database.connect() as conn:
            conn.execute(
                """
                insert into order_dispatch_locks(
                    bot_order_id, side, reason, order_type, client_order_id, status,
                    requested_price_brl, requested_qty_usdt, requested_brl_value,
                    created_at, updated_at, details_json
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(bot_order_id) do update set
                    side=excluded.side,
                    reason=excluded.reason,
                    order_type=excluded.order_type,
                    client_order_id=excluded.client_order_id,
                    status=excluded.status,
                    requested_price_brl=excluded.requested_price_brl,
                    requested_qty_usdt=excluded.requested_qty_usdt,
                    requested_brl_value=excluded.requested_brl_value,
                    updated_at=excluded.updated_at,
                    details_json=excluded.details_json
                """,
                (
                    bot_order_id,
                    side,
                    reason,
                    order_type,
                    client_order_id,
                    status,
                    requested_price_brl,
                    requested_qty_usdt,
                    requested_brl_value,
                    now,
                    now,
                    payload,
                ),
            )

    def get(self, bot_order_id: str) -> dict[str, Any] | None:
        with self.database.connect() as conn:
            row = conn.execute(
                "select * from order_dispatch_locks where bot_order_id = ?",
                (bot_order_id,),
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        try:
            data["details"] = json.loads(data.get("details_json") or "{}")
        except Exception:
            data["details"] = {}
        return data

    def update(
        self,
        bot_order_id: str,
        *,
        client_order_id: str | None = None,
        status: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        current = self.get(bot_order_id)
        if not current:
            return
        merged_details = dict(current.get("details") or {})
        if details:
            merged_details.update(details)
        with self.database.connect() as conn:
            conn.execute(
                """
                update order_dispatch_locks
                set client_order_id = ?, status = ?, updated_at = ?, details_json = ?
                where bot_order_id = ?
                """,
                (
                    client_order_id if client_order_id is not None else current.get("client_order_id"),
                    status if status is not None else current.get("status"),
                    self.clock(),
                    json.dumps(merged_details),
                    bot_order_id,
                ),
            )

    def list_active(self, limit: int | None = None) -> list[dict[str, Any]]:
        placeholders = ", ".join("?" for _ in self.active_statuses)
        params: list[Any] = list(self.active_statuses)
        sql = f"""
            select *
            from order_dispatch_locks
            where status in ({placeholders})
            order by created_at desc
        """
        if limit is not None:
            sql += "\n limit ?"
            params.append(int(limit))
        with self.database.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        payload = []
        for row in rows:
            data = dict(row)
            try:
                data["details"] = json.loads(data.get("details_json") or "{}")
            except Exception:
                data["details"] = {}
            payload.append(data)
        return payload

    def clear(self, bot_order_id: str, *, terminal_status: str = "terminal") -> None:
        with self.database.connect() as conn:
            conn.execute(
                "update order_dispatch_locks set status = ?, updated_at = ? where bot_order_id = ?",
                (terminal_status, self.clock(), bot_order_id),
            )

    def clear_stale(self, max_age_seconds: int) -> int:
        placeholders = ", ".join("?" for _ in self.active_statuses)
        with self.database.connect() as conn:
            rows = conn.execute(
                f"""
                select bot_order_id, updated_at
                from order_dispatch_locks
                where status in ({placeholders})
                """,
                self.active_statuses,
            ).fetchall()
        now = pd.Timestamp.utcnow()
        cleared = 0
        for row in rows:
            ts = pd.to_datetime(row["updated_at"], errors="coerce", utc=True)
            if pd.isna(ts):
                continue
            age = (now - ts).total_seconds()
            if age >= max_age_seconds:
                self.clear(str(row["bot_order_id"]), terminal_status="stale")
                cleared += 1
        return cleared
