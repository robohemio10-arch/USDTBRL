from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

import pandas as pd

from smartcrypto.app.config_io import root_dir
from smartcrypto.runtime.cache import dashboard_cache_dir, open_orders_cache_file as _unused  # noqa: F401
from smartcrypto.state.portfolio import Portfolio
from smartcrypto.state.position_manager import PositionManager
from smartcrypto.state.store import StateStore


READONLY_TIMEOUT_SECONDS = 1.5
READONLY_BUSY_TIMEOUT_MS = 1500


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except Exception:
        return default


def parse_datetime_series(values: Any) -> pd.Series:
    series = pd.Series(values)
    try:
        parsed = pd.to_datetime(series, format="ISO8601", errors="coerce", utc=True)
    except Exception:
        parsed = pd.to_datetime(series, errors="coerce", utc=True)
    if parsed.isna().any():
        try:
            fallback = pd.to_datetime(series[parsed.isna()], format="mixed", errors="coerce", utc=True)
            parsed.loc[parsed.isna()] = fallback
        except Exception:
            fallback = pd.to_datetime(series[parsed.isna()], errors="coerce", utc=True)
            parsed.loc[parsed.isna()] = fallback
    return parsed


def read_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}
        return cast(dict[str, Any], payload)
    except Exception:
        return {}


def db_path_from_cfg(cfg: dict[str, Any]) -> Path:
    raw = str(
        cfg.get("storage", {}).get("db_path", "data/usdtbrl_live.sqlite")
        or "data/usdtbrl_live.sqlite"
    )
    path = Path(raw)
    if not path.is_absolute():
        path = root_dir() / path
    return path


def state_store(cfg: dict[str, Any]) -> StateStore:
    return StateStore(str(db_path_from_cfg(cfg)))


def position_manager(cfg: dict[str, Any]) -> PositionManager:
    return PositionManager(state_store(cfg))


def portfolio(cfg: dict[str, Any]) -> Portfolio:
    return Portfolio(state_store(cfg), position_manager=position_manager(cfg))


def _readonly_uri(path: Path) -> str:
    return f"file:{quote(str(path.resolve()))}?mode=ro"


def _open_readonly_connection(path: Path) -> sqlite3.Connection:
    try:
        conn = sqlite3.connect(
            _readonly_uri(path),
            uri=True,
            timeout=READONLY_TIMEOUT_SECONDS,
            isolation_level=None,
        )
    except sqlite3.OperationalError:
        conn = sqlite3.connect(
            str(path),
            timeout=READONLY_TIMEOUT_SECONDS,
            isolation_level=None,
        )
    conn.execute(f"PRAGMA busy_timeout = {READONLY_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA query_only = ON")
    return conn


def query_df(cfg: dict[str, Any], sql: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    path = db_path_from_cfg(cfg)
    if not path.exists():
        return pd.DataFrame()
    try:
        with _open_readonly_connection(path) as conn:
            return pd.read_sql_query(sql, conn, params=params)
    except Exception:
        return pd.DataFrame()


def list_tables(cfg: dict[str, Any]) -> list[str]:
    path = db_path_from_cfg(cfg)
    if not path.exists():
        return []
    try:
        with _open_readonly_connection(path) as conn:
            rows = conn.execute(
                "select name from sqlite_master where type='table' order by name"
            ).fetchall()
    except Exception:
        return []
    return [row[0] for row in rows]


def table_exists(cfg: dict[str, Any], table: str) -> bool:
    return table in list_tables(cfg)


def read_table(cfg: dict[str, Any], table: str, limit: int = 200) -> pd.DataFrame:
    if not table_exists(cfg, table):
        return pd.DataFrame()
    sql = f"select * from {table} order by rowid desc limit ?"
    return query_df(cfg, sql, (int(limit),))


def load_runtime_status(cfg: dict[str, Any], runtime_status_cache_file: Any) -> dict[str, Any]:
    payload = read_json_file(runtime_status_cache_file(cfg))
    status_obj = payload.get("status", {}) if isinstance(payload, dict) else {}
    if isinstance(status_obj, dict) and status_obj:
        return cast(dict[str, Any], status_obj)
    store = state_store(cfg)
    runtime_portfolio = portfolio(cfg).runtime_view(
        mark_price_brl=0.0,
        initial_cash_brl=safe_float(cfg.get("portfolio", {}).get("initial_cash_brl", 0.0)),
    )
    return {
        "time": "",
        "price_brl": 0.0,
        "paused": bool(store.get_flag("paused", False)),
        "position": runtime_portfolio.position,
        "portfolio": {
            "cash_brl": runtime_portfolio.cash_brl,
            "equity_brl": runtime_portfolio.equity_brl,
            "position_notional_brl": runtime_portfolio.position_notional_brl,
            "invested_brl": runtime_portfolio.invested_brl,
            "unrealized_pnl_brl": runtime_portfolio.unrealized_pnl_brl,
            "realized_pnl_brl": runtime_portfolio.realized_pnl_brl,
            "drawdown_pct": runtime_portfolio.drawdown_pct,
        },
        "cash_brl": runtime_portfolio.cash_brl,
        "equity_brl": runtime_portfolio.equity_brl,
        "flags": {
            "force_sell_requested": bool(store.get_flag("force_sell_requested", False)),
            "reset_cycle_requested": bool(store.get_flag("reset_cycle_requested", False)),
            "reentry_block_until": store.get_flag("reentry_block_until", 0),
            "reentry_remaining_seconds": 0,
            "reentry_price_below": store.get_flag("reentry_price_below", 0.0),
            "live_reconcile_required": bool(store.get_flag("live_reconcile_required", False)),
            "consecutive_error_count": safe_int(store.get_flag("consecutive_error_count", 0)),
        },
        "live_hardening": {
            "active_dispatch_locks": [],
        },
    }


def open_orders_cache_file(cfg: dict[str, Any]) -> Path:
    symbol = str(cfg.get("market", {}).get("symbol", "USDTBRL")).replace("/", "")
    return dashboard_cache_dir(cfg) / f"open_orders_{symbol}.json"


def load_open_orders_cache(cfg: dict[str, Any]) -> pd.DataFrame:
    payload = read_json_file(open_orders_cache_file(cfg))
    rows = payload.get("orders", []) if isinstance(payload, dict) else []
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    if "updated_at" in df.columns:
        df["updated_at"] = pd.to_datetime(df["updated_at"], errors="coerce", utc=True)
    return df


def trades_df(cfg: dict[str, Any], limit: int = 500) -> pd.DataFrame:
    df = query_df(cfg, "select * from trades order by id desc limit ?", (int(limit),))
    if df.empty:
        return df
    for col in ["price_brl", "qty_usdt", "brl_value", "fee_brl"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    if "created_at" in df.columns:
        df["created_at"] = parse_datetime_series(df["created_at"])
    return df


def cycles_df(cfg: dict[str, Any], limit: int = 500) -> pd.DataFrame:
    df = query_df(cfg, "select * from cycles order by id desc limit ?", (int(limit),))
    if df.empty:
        return df
    for col in [
        "entry_price_brl",
        "exit_price_brl",
        "qty_usdt",
        "brl_spent",
        "brl_received",
        "pnl_brl",
        "pnl_pct",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    if "opened_at" in df.columns:
        df["opened_at"] = parse_datetime_series(df["opened_at"])
    if "closed_at" in df.columns:
        df["closed_at"] = parse_datetime_series(df["closed_at"])
    return df


def snapshots_df(cfg: dict[str, Any], limit: int = 1000) -> pd.DataFrame:
    df = query_df(cfg, "select * from snapshots order by id desc limit ?", (int(limit),))
    if df.empty:
        return df
    if "ts" in df.columns:
        df["ts"] = parse_datetime_series(df["ts"])
    for col in ["price_brl", "cash_brl", "equity_brl"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df.sort_values("ts")


def planned_orders_df(cfg: dict[str, Any], limit: int = 50) -> pd.DataFrame:
    if table_exists(cfg, "planned_orders"):
        df = query_df(cfg, "select * from planned_orders order by id desc limit ?", (int(limit),))
    elif table_exists(cfg, "pending_orders"):
        df = query_df(cfg, "select * from pending_orders order by id desc limit ?", (int(limit),))
    else:
        df = pd.DataFrame()
    if df.empty:
        return df
    for col in ["price_brl", "qty_usdt", "brl_value"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df


def order_states_df(cfg: dict[str, Any], limit: int = 100) -> pd.DataFrame:
    if not table_exists(cfg, "order_events"):
        return pd.DataFrame()
    sql = """
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
    df = query_df(cfg, sql, (int(limit),))
    if df.empty:
        return df
    for col in ["price_brl", "qty_usdt", "executed_qty_usdt", "brl_value"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    if "event_time" in df.columns:
        df["event_time"] = parse_datetime_series(df["event_time"])
    return df


def bot_events_df(cfg: dict[str, Any], limit: int = 200) -> pd.DataFrame:
    df = query_df(cfg, "select * from bot_events order by id desc limit ?", (int(limit),))
    if df.empty:
        return df
    if "ts" in df.columns:
        df["ts"] = parse_datetime_series(df["ts"])
    return df


def dispatch_locks_df(cfg: dict[str, Any], limit: int = 50) -> pd.DataFrame:
    if not table_exists(cfg, "order_dispatch_locks"):
        return pd.DataFrame()
    return query_df(cfg, "select * from order_dispatch_locks order by id desc limit ?", (int(limit),))


def reconciliation_df(cfg: dict[str, Any], limit: int = 50) -> pd.DataFrame:
    if not table_exists(cfg, "reconciliation_audit"):
        return pd.DataFrame()
    return query_df(cfg, "select * from reconciliation_audit order by id desc limit ?", (int(limit),))
