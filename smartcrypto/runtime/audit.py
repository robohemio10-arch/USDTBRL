from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable

import pandas as pd

from smartcrypto.state.store import utc_now

CRITICAL_RUNTIME_EVENTS = (
    "preflight_failed",
    "bot_tick_error",
    "critical_tick_error",
    "circuit_breaker_paused",
    "reconcile_mismatch",
    "unexpected_shutdown",
    "shutdown",
    "duplicate_instance_blocked",
)


def _connect(database_or_path: Any) -> tuple[sqlite3.Connection, Callable[[], None]]:
    if isinstance(database_or_path, sqlite3.Connection):
        database_or_path.row_factory = sqlite3.Row
        return database_or_path, lambda: None

    if hasattr(database_or_path, "connect"):
        connection_or_manager = database_or_path.connect()
        if isinstance(connection_or_manager, sqlite3.Connection):
            connection_or_manager.row_factory = sqlite3.Row
            return connection_or_manager, connection_or_manager.close

        enter = getattr(connection_or_manager, "__enter__", None)
        exit_ = getattr(connection_or_manager, "__exit__", None)
        if callable(enter) and callable(exit_):
            conn = enter()
            if isinstance(conn, sqlite3.Connection):
                conn.row_factory = sqlite3.Row

            def _close() -> None:
                exit_(None, None, None)

            return conn, _close

    conn = sqlite3.connect(str(database_or_path))
    conn.row_factory = sqlite3.Row
    return conn, conn.close


def ensure_runtime_audit_tables(database_or_path: Any) -> None:
    if hasattr(database_or_path, "connect"):
        with database_or_path.connect() as conn:
            _create_tables(conn)
        return
    conn, close_conn = _connect(database_or_path)
    try:
        _create_tables(conn)
        conn.commit()
    finally:
        close_conn()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    columns = {row[1] for row in conn.execute(f"pragma table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"alter table {table} add column {ddl}")


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        create table if not exists runtime_events (
            id integer primary key autoincrement,
            ts text not null,
            run_id text,
            level text not null,
            event text not null,
            mode text,
            symbol text,
            timeframe text,
            build_id text,
            config_hash text,
            preflight_status text,
            details_json text not null default '{}'
        )
        """
    )
    _ensure_column(conn, "runtime_events", "run_id", "run_id text")
    conn.execute(
        """
        create table if not exists cycle_audit (
            id integer primary key autoincrement,
            run_id text,
            cycle_id text not null,
            started_at text not null,
            finished_at text not null,
            status text not null,
            event text not null,
            exit_reason text,
            mode text,
            symbol text,
            timeframe text,
            price_brl real,
            equity_brl real,
            details_json text not null default '{}'
        )
        """
    )
    _ensure_column(conn, "cycle_audit", "run_id", "run_id text")


def record_runtime_event(
    cfg: dict[str, Any],
    database_or_path: Any,
    *,
    event: str,
    level: str = "INFO",
    details: dict[str, Any] | None = None,
    ts: str | None = None,
) -> None:
    ensure_runtime_audit_tables(database_or_path)
    payload = {
        "ts": ts or utc_now(),
        "run_id": str(cfg.get("__operational_manifest", {}).get("run_id", "") or cfg.get("__run_id", "") or ""),
        "level": str(level).upper(),
        "event": str(event),
        "mode": str(cfg.get("execution", {}).get("mode", "") or ""),
        "symbol": str(cfg.get("market", {}).get("symbol", "") or ""),
        "timeframe": str(cfg.get("market", {}).get("timeframe", "") or ""),
        "build_id": str(cfg.get("__operational_manifest", {}).get("build_id", "") or ""),
        "config_hash": str(cfg.get("__operational_manifest", {}).get("config_hash", "") or ""),
        "preflight_status": str(cfg.get("__preflight", {}).get("status", "") or ""),
        "details_json": json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
    }
    if hasattr(database_or_path, "connect"):
        with database_or_path.connect() as conn:
            _create_tables(conn)
            conn.execute(
                """
                insert into runtime_events(
                    ts, run_id, level, event, mode, symbol, timeframe, build_id, config_hash, preflight_status, details_json
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["ts"],
                    payload["run_id"],
                    payload["level"],
                    payload["event"],
                    payload["mode"],
                    payload["symbol"],
                    payload["timeframe"],
                    payload["build_id"],
                    payload["config_hash"],
                    payload["preflight_status"],
                    payload["details_json"],
                ),
            )
        return
    conn, close_conn = _connect(database_or_path)
    try:
        _create_tables(conn)
        conn.execute(
            """
            insert into runtime_events(
                ts, run_id, level, event, mode, symbol, timeframe, build_id, config_hash, preflight_status, details_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["ts"],
                payload["run_id"],
                payload["level"],
                payload["event"],
                payload["mode"],
                payload["symbol"],
                payload["timeframe"],
                payload["build_id"],
                payload["config_hash"],
                payload["preflight_status"],
                payload["details_json"],
            ),
        )
        conn.commit()
    finally:
        close_conn()


def record_cycle_audit(
    cfg: dict[str, Any],
    database_or_path: Any,
    *,
    cycle_id: str,
    started_at: str,
    finished_at: str,
    status: str,
    event: str,
    exit_reason: str = "",
    price_brl: float | None = None,
    equity_brl: float | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    ensure_runtime_audit_tables(database_or_path)
    row = (
        str(cfg.get("__operational_manifest", {}).get("run_id", "") or cfg.get("__run_id", "") or ""),
        str(cycle_id),
        str(started_at),
        str(finished_at),
        str(status),
        str(event),
        str(exit_reason or ""),
        str(cfg.get("execution", {}).get("mode", "") or ""),
        str(cfg.get("market", {}).get("symbol", "") or ""),
        str(cfg.get("market", {}).get("timeframe", "") or ""),
        None if price_brl is None else float(price_brl),
        None if equity_brl is None else float(equity_brl),
        json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
    )
    if hasattr(database_or_path, "connect"):
        with database_or_path.connect() as conn:
            _create_tables(conn)
            conn.execute(
                """
                insert into cycle_audit(
                    run_id, cycle_id, started_at, finished_at, status, event, exit_reason, mode,
                    symbol, timeframe, price_brl, equity_brl, details_json
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
        return
    conn, close_conn = _connect(database_or_path)
    try:
        _create_tables(conn)
        conn.execute(
            """
            insert into cycle_audit(
                run_id, cycle_id, started_at, finished_at, status, event, exit_reason, mode,
                symbol, timeframe, price_brl, equity_brl, details_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
        conn.commit()
    finally:
        close_conn()


def read_recent_runtime_events(database_or_path: Any, limit: int = 20) -> pd.DataFrame:
    ensure_runtime_audit_tables(database_or_path)
    if hasattr(database_or_path, "read_sql"):
        return database_or_path.read_sql(
            "select * from runtime_events order by id desc limit ?",
            (int(limit),),
        )
    conn, close_conn = _connect(database_or_path)
    try:
        return pd.read_sql_query(
            "select * from runtime_events order by id desc limit ?",
            conn,
            params=(int(limit),),
        )
    finally:
        close_conn()


def read_recent_cycle_audit(database_or_path: Any, limit: int = 20) -> pd.DataFrame:
    ensure_runtime_audit_tables(database_or_path)
    if hasattr(database_or_path, "read_sql"):
        return database_or_path.read_sql(
            "select * from cycle_audit order by id desc limit ?",
            (int(limit),),
        )
    conn, close_conn = _connect(database_or_path)
    try:
        return pd.read_sql_query(
            "select * from cycle_audit order by id desc limit ?",
            conn,
            params=(int(limit),),
        )
    finally:
        close_conn()


def recent_critical_events(
    database_or_path: Any,
    *,
    run_id: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    events = read_recent_runtime_events(database_or_path, limit=max(limit * 10, 50))
    if events.empty:
        return []
    df = events[
        events["event"].astype(str).isin(CRITICAL_RUNTIME_EVENTS)
        | events["level"].astype(str).str.upper().isin(["ERROR", "WARNING"])
    ].copy()
    if run_id:
        df = df[df["run_id"].astype(str) == str(run_id)]
    rows: list[dict[str, Any]] = []
    for _, row in df.head(limit).iterrows():
        details: dict[str, Any] = {}
        raw = row.get("details_json", "{}")
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    details = parsed
            except Exception:
                details = {"raw": raw}
        rows.append(
            {
                "ts": str(row.get("ts", "") or ""),
                "run_id": str(row.get("run_id", "") or ""),
                "level": str(row.get("level", "") or ""),
                "event": str(row.get("event", "") or ""),
                "details": details,
                "details_json": raw if isinstance(raw, str) else json.dumps(details, ensure_ascii=False, sort_keys=True),
            }
        )
    return rows


def summarize_runtime_session(
    database_or_path: Any,
    *,
    run_id: str = "",
    boot_timestamp: str = "",
) -> dict[str, Any]:
    cycles = read_recent_cycle_audit(database_or_path, limit=5000)
    if run_id and not cycles.empty:
        cycles = cycles[cycles["run_id"].astype(str) == str(run_id)]
    error_cycles = int(cycles["status"].astype(str).str.lower().eq("error").sum()) if not cycles.empty else 0
    last_cycle_id = str(cycles.iloc[0].get("cycle_id", "") or "") if not cycles.empty else ""
    critical = recent_critical_events(database_or_path, run_id=run_id, limit=20)
    return {
        "run_id": str(run_id or ""),
        "boot_timestamp": str(boot_timestamp or ""),
        "cycle_count": int(len(cycles)),
        "error_cycle_count": int(error_cycles),
        "critical_event_count": int(len(critical)),
        "critical_error_count": int(sum(1 for row in critical if str(row.get("level", "")).upper() == "ERROR")),
        "last_cycle_id": last_cycle_id,
        "critical_events": critical,
        "alert_event_names": list(CRITICAL_RUNTIME_EVENTS),
    }
