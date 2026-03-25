"""
Camada legada de compatibilidade para persistência central.

Caminhos canônicos novos:
- state.position_manager
- state.portfolio
- state.order_events
- state.order_projections
- state.snapshots
- state.bot_events
- state.dispatch_locks
- state.reconciliation_audit

Este módulo permanece para compatibilidade operacional e integração legada.
Novas funcionalidades não devem ser adicionadas aqui.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from smartcrypto.infra.database import SQLiteDatabase
from smartcrypto.state.bot_events import BotEventStore
from smartcrypto.state.dispatch_locks import DispatchLockStore
from smartcrypto.state.migrations import apply_migrations
from smartcrypto.state.order_events import OrderEventStore
from smartcrypto.state.order_projections import OrderProjectionStore
from smartcrypto.state.reconciliation_audit import ReconciliationAuditStore
from smartcrypto.state.snapshots import SnapshotStore


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PositionState:
    status: str = "flat"
    qty_usdt: float = 0.0
    brl_spent: float = 0.0
    avg_price_brl: float = 0.0
    realized_pnl_brl: float = 0.0
    unrealized_pnl_brl: float = 0.0
    tp_price_brl: float = 0.0
    stop_price_brl: float = 0.0
    safety_count: int = 0
    regime: str = "sideways"
    trailing_active: int = 0
    trailing_anchor_brl: float = 0.0
    updated_at: str = ""


class StateStore:
    ACTIVE_DISPATCH_LOCK_STATUSES = (
        "pending_submit",
        "submit_unknown",
        "submitted",
        "recovered_open",
    )

    def __init__(self, db_path: str, database: SQLiteDatabase | None = None) -> None:
        self.db_path = db_path
        self.database = database or SQLiteDatabase(db_path)
        self.order_projections = OrderProjectionStore(self.database, utc_now)
        self.order_events = OrderEventStore(self.database, utc_now)
        self.snapshots = SnapshotStore(self.database, utc_now)
        self.bot_events = BotEventStore(self.database, utc_now)
        self.dispatch_locks = DispatchLockStore(
            self.database,
            utc_now,
            self.ACTIVE_DISPATCH_LOCK_STATUSES,
        )
        self.reconciliation_audit = ReconciliationAuditStore(self.database, utc_now)
        self._init_db()

    def conn(self):
        return self.database.connect()

    def _init_db(self) -> None:
        with self.conn() as c:
            apply_migrations(c)
        self._migrate_planned_orders_compatibility()
        with self.conn() as c:
            row = c.execute("select count(*) as n from positions").fetchone()
            if int(row["n"]) == 0:
                self._insert_position(c, PositionState(updated_at=utc_now()))


    def _migrate_planned_orders_compatibility(self) -> None:
        with self.conn() as c:
            table_names = {
                row["name"]
                for row in c.execute(
                    "select name from sqlite_master where type = 'table'"
                ).fetchall()
            }
            if "planned_orders" not in table_names:
                return
            pending_count = (
                c.execute("select count(*) as n from pending_orders").fetchone()["n"]
                if "pending_orders" in table_names
                else 0
            )
            planned_count = c.execute("select count(*) as n from planned_orders").fetchone()["n"]
            if planned_count == 0 and pending_count > 0:
                c.execute("""
                    insert into planned_orders(side, order_type, price_brl, qty_usdt, brl_value, reason, status, updated_at)
                    select side, order_type, price_brl, qty_usdt, brl_value, reason, status, updated_at
                    from pending_orders
                    """)



    def _replace_order_projection_table(
        self, table_name: str, orders: list[dict[str, Any]]
    ) -> None:
        self.order_projections.replace_table(table_name, orders)

    def replace_planned_orders(self, orders: list[dict[str, Any]]) -> None:
        self.order_projections.replace_planned_orders(orders)

    def add_order_event(
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
        self.order_events.add(
            bot_order_id=bot_order_id,
            state=state,
            side=side,
            order_type=order_type,
            reason=reason,
            price_brl=price_brl,
            qty_usdt=qty_usdt,
            executed_qty_usdt=executed_qty_usdt,
            brl_value=brl_value,
            source=source,
            exchange_order_id=exchange_order_id,
            client_order_id=client_order_id,
            parent_bot_order_id=parent_bot_order_id,
            note=note,
            payload=payload,
            event_time=event_time,
        )

    def latest_order_states_df(self, limit: int = 200) -> pd.DataFrame:
        return self.order_events.latest_states_df(limit=limit)

    def replace_pending_orders(self, orders: list[dict[str, Any]]) -> None:
        self.order_projections.replace_pending_orders(orders)

    def add_snapshot(
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
        self.snapshots.add(
            last_price_brl=last_price_brl,
            equity_brl=equity_brl,
            cash_brl=cash_brl,
            pos_value_brl=pos_value_brl,
            realized_pnl_brl=realized_pnl_brl,
            unrealized_pnl_brl=unrealized_pnl_brl,
            drawdown_pct=drawdown_pct,
            regime=regime,
            meta=meta,
        )

    def add_event(self, level: str, event: str, details: dict[str, Any] | None = None) -> None:
        self.bot_events.add(level, event, details)

    def upsert_dispatch_lock(
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
        self.dispatch_locks.upsert(
            bot_order_id=bot_order_id,
            side=side,
            reason=reason,
            order_type=order_type,
            client_order_id=client_order_id,
            status=status,
            requested_price_brl=requested_price_brl,
            requested_qty_usdt=requested_qty_usdt,
            requested_brl_value=requested_brl_value,
            details=details,
        )

    def update_dispatch_lock(
        self,
        bot_order_id: str,
        *,
        client_order_id: str | None = None,
        status: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.dispatch_locks.update(
            bot_order_id,
            client_order_id=client_order_id,
            status=status,
            details=details,
        )

    def get_dispatch_lock(self, bot_order_id: str) -> dict[str, Any] | None:
        return self.dispatch_locks.get(bot_order_id)

    def list_active_dispatch_locks(self, limit: int | None = None) -> list[dict[str, Any]]:
        return self.dispatch_locks.list_active(limit=limit)

    def clear_dispatch_lock(self, bot_order_id: str, *, terminal_status: str = "terminal") -> None:
        self.dispatch_locks.clear(bot_order_id, terminal_status=terminal_status)

    def clear_stale_dispatch_locks(self, max_age_seconds: int) -> int:
        return self.dispatch_locks.clear_stale(max_age_seconds=max_age_seconds)

    def add_reconciliation_audit(
        self,
        *,
        action: str,
        local_status: str,
        local_qty_usdt: float,
        exchange_qty_usdt: float,
        exchange_open_orders: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.reconciliation_audit.add(
            action=action,
            local_status=local_status,
            local_qty_usdt=local_qty_usdt,
            exchange_qty_usdt=exchange_qty_usdt,
            exchange_open_orders=exchange_open_orders,
            details=details,
        )

    def _insert_position(self, c: sqlite3.Connection, position: PositionState) -> None:
        c.execute(
            """
            insert into positions(
                status, qty_usdt, brl_spent, avg_price_brl, realized_pnl_brl,
                unrealized_pnl_brl, tp_price_brl, stop_price_brl, safety_count,
                regime, trailing_active, trailing_anchor_brl, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                position.status,
                position.qty_usdt,
                position.brl_spent,
                position.avg_price_brl,
                position.realized_pnl_brl,
                position.unrealized_pnl_brl,
                position.tp_price_brl,
                position.stop_price_brl,
                position.safety_count,
                position.regime,
                position.trailing_active,
                position.trailing_anchor_brl,
                position.updated_at or utc_now(),
            ),
        )


    def set_flag(self, key: str, value: Any) -> None:
        with self.conn() as c:
            c.execute(
                """
                insert into bot_state(key, value)
                values(?, ?)
                on conflict(key) do update set value=excluded.value
                """,
                (key, json.dumps(value)),
            )


    def get_flag(self, key: str, default: Any = None) -> Any:
        with self.conn() as c:
            row = c.execute("select value from bot_state where key = ?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except Exception:
            return default


    def get_position(self) -> PositionState:
        with self.conn() as c:
            row = c.execute("select * from positions order by id desc limit 1").fetchone()
        if row is None:
            return PositionState(updated_at=utc_now())
        data = dict(row)
        return PositionState(
            status=data.get("status", "flat"),
            qty_usdt=float(data.get("qty_usdt", 0.0) or 0.0),
            brl_spent=float(data.get("brl_spent", 0.0) or 0.0),
            avg_price_brl=float(data.get("avg_price_brl", 0.0) or 0.0),
            realized_pnl_brl=float(data.get("realized_pnl_brl", 0.0) or 0.0),
            unrealized_pnl_brl=float(data.get("unrealized_pnl_brl", 0.0) or 0.0),
            tp_price_brl=float(data.get("tp_price_brl", 0.0) or 0.0),
            stop_price_brl=float(data.get("stop_price_brl", 0.0) or 0.0),
            safety_count=int(data.get("safety_count", 0) or 0),
            regime=data.get("regime", "sideways"),
            trailing_active=int(data.get("trailing_active", 0) or 0),
            trailing_anchor_brl=float(data.get("trailing_anchor_brl", 0.0) or 0.0),
            updated_at=data.get("updated_at", ""),
        )


    def update_position(self, **updates: Any) -> PositionState:
        current = self.get_position()
        payload = PositionState(
            status=str(updates.get("status", current.status)),
            qty_usdt=float(updates.get("qty_usdt", current.qty_usdt)),
            brl_spent=float(updates.get("brl_spent", current.brl_spent)),
            avg_price_brl=float(updates.get("avg_price_brl", current.avg_price_brl)),
            realized_pnl_brl=float(updates.get("realized_pnl_brl", current.realized_pnl_brl)),
            unrealized_pnl_brl=float(updates.get("unrealized_pnl_brl", current.unrealized_pnl_brl)),
            tp_price_brl=float(updates.get("tp_price_brl", current.tp_price_brl)),
            stop_price_brl=float(updates.get("stop_price_brl", current.stop_price_brl)),
            safety_count=int(updates.get("safety_count", current.safety_count)),
            regime=str(updates.get("regime", current.regime)),
            trailing_active=int(updates.get("trailing_active", current.trailing_active)),
            trailing_anchor_brl=float(
                updates.get("trailing_anchor_brl", current.trailing_anchor_brl)
            ),
            updated_at=utc_now(),
        )
        with self.conn() as c:
            c.execute("delete from positions")
            self._insert_position(c, payload)
        return payload


    def reset_position(self, realized_pnl_brl: float | None = None) -> PositionState:
        current = self.get_position()
        return self.update_position(
            status="flat",
            qty_usdt=0.0,
            brl_spent=0.0,
            avg_price_brl=0.0,
            unrealized_pnl_brl=0.0,
            tp_price_brl=0.0,
            stop_price_brl=0.0,
            safety_count=0,
            regime=current.regime,
            trailing_active=0,
            trailing_anchor_brl=0.0,
            realized_pnl_brl=(
                current.realized_pnl_brl if realized_pnl_brl is None else realized_pnl_brl
            ),
        )


    def replace_safety_ladder(self, ladder_rows: list[dict[str, Any]]) -> None:
        with self.conn() as c:
            c.execute("delete from safety_ladder")
            for row in ladder_rows:
                c.execute(
                    """
                    insert into safety_ladder(step_index, trigger_price_brl, order_brl, expected_qty_usdt, status)
                    values (?, ?, ?, ?, ?)
                    """,
                    (
                        row.get("step_index"),
                        row.get("trigger_price_brl"),
                        row.get("order_brl"),
                        row.get("expected_qty_usdt"),
                        row.get("status", "ready"),
                    ),
                )


    def add_trade(
        self,
        *,
        side: str,
        price_brl: float,
        qty_usdt: float,
        brl_value: float,
        fee_brl: float,
        reason: str,
        mode: str,
        regime: str,
    ) -> None:
        with self.conn() as c:
            c.execute(
                """
                insert into trades(created_at, side, price_brl, qty_usdt, brl_value, fee_brl, reason, mode, regime)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (utc_now(), side, price_brl, qty_usdt, brl_value, fee_brl, reason, mode, regime),
            )


    def open_cycle(
        self, *, regime: str, entry_price_brl: float, qty_usdt: float, brl_spent: float
    ) -> None:
        with self.conn() as c:
            c.execute(
                """
                insert into cycles(
                    opened_at, closed_at, regime, entry_price_brl, exit_price_brl, qty_usdt,
                    brl_spent, brl_received, pnl_brl, pnl_pct, safety_count, exit_reason, status
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    utc_now(),
                    None,
                    regime,
                    entry_price_brl,
                    None,
                    qty_usdt,
                    brl_spent,
                    None,
                    None,
                    None,
                    0,
                    None,
                    "open",
                ),
            )


    def sync_open_cycle(self, *, qty_usdt: float, brl_spent: float, safety_count: int) -> None:
        with self.conn() as c:
            row = c.execute(
                "select id from cycles where status='open' order by id desc limit 1"
            ).fetchone()
            if row is None:
                return
            c.execute(
                "update cycles set qty_usdt=?, brl_spent=?, safety_count=? where id=?",
                (qty_usdt, brl_spent, safety_count, row["id"]),
            )


    def close_latest_cycle(
        self,
        *,
        exit_price_brl: float,
        brl_received: float,
        pnl_brl: float,
        pnl_pct: float,
        safety_count: int,
        exit_reason: str,
    ) -> None:
        with self.conn() as c:
            row = c.execute(
                "select id from cycles where status='open' order by id desc limit 1"
            ).fetchone()
            if row is None:
                return
            c.execute(
                """
                update cycles
                set closed_at=?, exit_price_brl=?, brl_received=?, pnl_brl=?, pnl_pct=?,
                    safety_count=?, exit_reason=?, status='closed'
                where id=?
                """,
                (
                    utc_now(),
                    exit_price_brl,
                    brl_received,
                    pnl_brl,
                    pnl_pct,
                    safety_count,
                    exit_reason,
                    row["id"],
                ),
            )


    def add_regime_observation(
        self, regime: str, score: float, features: dict[str, Any] | None = None
    ) -> None:
        with self.conn() as c:
            c.execute(
                "insert into regime_observations(ts, regime, score, features_json) values (?, ?, ?, ?)",
                (utc_now(), regime, score, json.dumps(features or {})),
            )


    def add_research_run(
        self, run_type: str, name: str, params: dict[str, Any], results: dict[str, Any]
    ) -> None:
        with self.conn() as c:
            c.execute(
                "insert into research_runs(ts, run_type, name, params_json, results_json) values (?, ?, ?, ?, ?)",
                (utc_now(), run_type, name, json.dumps(params), json.dumps(results)),
            )


    def read_df(self, table: str, limit: int | None = None) -> pd.DataFrame:
        allowed = {
            "positions",
            "planned_orders",
            "pending_orders",
            "order_events",
            "safety_ladder",
            "trades",
            "cycles",
            "snapshots",
            "bot_events",
            "regime_observations",
            "research_runs",
            "bot_state",
            "reconciliation_audit",
            "order_dispatch_locks",
        }
        if table not in allowed:
            raise ValueError(f"Tabela não permitida: {table}")
        query = f"select * from {table}"
        if table == "order_dispatch_locks":
            query += " order by datetime(updated_at) desc, bot_order_id desc"
        elif table != "bot_state":
            query += " order by id desc"
        if limit is not None:
            query += f" limit {int(limit)}"
        with self.conn() as c:
            return pd.read_sql_query(query, c)


    def last_equity(self) -> float | None:
        df = self.read_df("snapshots", 1)
        if df.empty:
            return None
        return float(df.iloc[0]["equity_brl"])


    def compute_drawdown_pct(self) -> float:
        df = self.read_df("snapshots", 10000)
        if df.empty:
            return 0.0
        equity = df.iloc[::-1]["equity_brl"].astype(float)
        peak = equity.cummax()
        dd = ((equity / peak) - 1.0) * 100.0
        return float(dd.min())
