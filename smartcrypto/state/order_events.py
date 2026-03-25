from __future__ import annotations

import json
from typing import Any

import pandas as pd

from smartcrypto.infra.database import SQLiteDatabase


class OrderEventStore:
    def __init__(self, database: SQLiteDatabase, clock) -> None:
        self.database = database
        self.clock = clock

    def add(
        self,
        *,
        bot_order_id: str,
        state: str,
        side: str | None = None,
        order_type: str | None = None,
        reason: str | None = None,
        price_brl: float | None = None,
        qty_usdt: float | None = None,
        executed_qty_usdt: float | None = None,
        brl_value: float | None = None,
        source: str = "bot",
        exchange_order_id: str | None = None,
        client_order_id: str | None = None,
        parent_bot_order_id: str | None = None,
        note: str | None = None,
        payload: dict[str, Any] | None = None,
        event_time: str | None = None,
    ) -> None:
        with self.database.connect() as conn:
            conn.execute(
                """
                insert into order_events(
                    bot_order_id, parent_bot_order_id, exchange_order_id, client_order_id,
                    side, order_type, state, reason, price_brl, qty_usdt, executed_qty_usdt,
                    brl_value, source, note, payload, event_time
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bot_order_id,
                    parent_bot_order_id,
                    str(exchange_order_id or "") or None,
                    str(client_order_id or "") or None,
                    side,
                    order_type,
                    state,
                    reason,
                    price_brl,
                    qty_usdt,
                    executed_qty_usdt,
                    brl_value,
                    source,
                    note,
                    json.dumps(payload or {}, ensure_ascii=False),
                    event_time or self.clock(),
                ),
            )

    def latest_states_df(self, limit: int = 200) -> pd.DataFrame:
        query = """
            with ranked as (
                select
                    *,
                    row_number() over (
                        partition by bot_order_id
                        order by datetime(event_time) desc, id desc
                    ) as rn
                from order_events
            )
            select
                bot_order_id,
                parent_bot_order_id,
                exchange_order_id,
                client_order_id,
                side,
                order_type,
                state,
                reason,
                price_brl,
                qty_usdt,
                executed_qty_usdt,
                brl_value,
                source,
                note,
                event_time
            from ranked
            where rn = 1
            order by datetime(event_time) desc, bot_order_id desc
            limit ?
        """
        return self.database.read_sql(query, params=(int(limit),))
