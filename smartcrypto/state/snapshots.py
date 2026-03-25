from __future__ import annotations

import json
from typing import Any

from smartcrypto.infra.database import SQLiteDatabase


class SnapshotStore:
    def __init__(self, database: SQLiteDatabase, clock) -> None:
        self.database = database
        self.clock = clock

    def add(
        self,
        *,
        last_price_brl: float,
        equity_brl: float,
        cash_brl: float,
        pos_value_brl: float,
        realized_pnl_brl: float,
        unrealized_pnl_brl: float,
        drawdown_pct: float,
        regime: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        with self.database.connect() as conn:
            conn.execute(
                """
                insert into snapshots(
                    ts, last_price_brl, equity_brl, cash_brl, pos_value_brl, realized_pnl_brl,
                    unrealized_pnl_brl, drawdown_pct, regime, meta_json
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.clock(),
                    last_price_brl,
                    equity_brl,
                    cash_brl,
                    pos_value_brl,
                    realized_pnl_brl,
                    unrealized_pnl_brl,
                    drawdown_pct,
                    regime,
                    json.dumps(meta or {}),
                ),
            )
