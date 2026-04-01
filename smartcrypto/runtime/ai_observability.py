from __future__ import annotations

import json
import sqlite3
from typing import Any

import pandas as pd

from smartcrypto.state.store import utc_now


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    columns = {row[1] for row in conn.execute(f"pragma table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"alter table {table} add column {ddl}")


def ensure_ai_observability_table(database_or_path: Any) -> None:
    def _create(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            create table if not exists ai_decisions_log (
                id integer primary key autoincrement,
                ts text not null,
                run_id text,
                cycle_id text,
                mode text,
                stage text,
                symbol text,
                timeframe text,
                divergence integer not null default 0,
                veto integer not null default 0,
                override integer not null default 0,
                baseline_is_real integer not null default 0,
                baseline_entry_gate integer not null default 0,
                ai_effective_entry_gate integer not null default 0,
                baseline_position_action text,
                ai_position_action text,
                baseline_decision_json text not null default '{}',
                ai_decision_json text not null default '{}',
                context_json text not null default '{}'
            )
            """
        )
        _ensure_column(conn, "ai_decisions_log", "run_id", "run_id text")
        _ensure_column(conn, "ai_decisions_log", "baseline_is_real", "baseline_is_real integer not null default 0")
        _ensure_column(conn, "ai_decisions_log", "baseline_entry_gate", "baseline_entry_gate integer not null default 0")
        _ensure_column(conn, "ai_decisions_log", "ai_effective_entry_gate", "ai_effective_entry_gate integer not null default 0")
        _ensure_column(conn, "ai_decisions_log", "baseline_position_action", "baseline_position_action text")
        _ensure_column(conn, "ai_decisions_log", "ai_position_action", "ai_position_action text")

    if hasattr(database_or_path, "connect"):
        with database_or_path.connect() as conn:
            _create(conn)
        return
    conn = sqlite3.connect(str(database_or_path))
    try:
        _create(conn)
        conn.commit()
    finally:
        conn.close()


def baseline_decision_from_ai(ai_decision: dict[str, Any] | None = None) -> dict[str, Any]:
    ai = dict(ai_decision or {})
    baseline = dict(ai.get("baseline_decision", {}) or {})
    if baseline:
        baseline["is_real"] = bool(baseline.get("is_real", True))
        return baseline
    return {
        "source": "heuristic_runtime_fallback",
        "entry_gate": True,
        "effective_entry_gate": True,
        "position_action": "wait",
        "reason": "baseline_default",
        "enabled": True,
        "stage": str(ai.get("stage", "disabled") or "disabled"),
        "is_real": False,
    }


def _normalized_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _normalized_action(payload: dict[str, Any], default: str) -> str:
    for key in ("position_action", "target_action", "action"):
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def record_ai_observation(
    cfg: dict[str, Any],
    database_or_path: Any,
    *,
    cycle_id: str,
    ai_decision: dict[str, Any] | None = None,
    baseline_decision: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    ts: str | None = None,
) -> None:
    ensure_ai_observability_table(database_or_path)
    ai_payload = dict(ai_decision or {})
    baseline_payload = dict(baseline_decision or baseline_decision_from_ai(ai_payload))
    baseline_is_real = bool(baseline_payload.get("is_real", False))
    stage = str(ai_payload.get("stage", "disabled") or "disabled")
    baseline_entry_gate = _normalized_bool(
        baseline_payload.get("entry_gate", baseline_payload.get("effective_entry_gate", True)),
        True,
    )
    ai_effective_entry_gate = _normalized_bool(
        ai_payload.get("effective_entry_gate", ai_payload.get("entry_gate", True)),
        True,
    )
    baseline_position_action = _normalized_action(baseline_payload, "wait")
    ai_position_action = _normalized_action(ai_payload, "wait")
    divergence = baseline_entry_gate != ai_effective_entry_gate or baseline_position_action != ai_position_action
    veto = baseline_entry_gate and not ai_effective_entry_gate
    override = (not baseline_entry_gate) and ai_effective_entry_gate
    row = (
        str(ts or utc_now()),
        str(cfg.get("__operational_manifest", {}).get("run_id", "") or cfg.get("__run_id", "") or ""),
        str(cycle_id),
        str(cfg.get("execution", {}).get("mode", "") or ""),
        stage,
        str(cfg.get("market", {}).get("symbol", "") or ""),
        str(cfg.get("market", {}).get("timeframe", "") or ""),
        1 if divergence else 0,
        1 if veto else 0,
        1 if override else 0,
        1 if baseline_is_real else 0,
        1 if baseline_entry_gate else 0,
        1 if ai_effective_entry_gate else 0,
        baseline_position_action,
        ai_position_action,
        json.dumps(baseline_payload, ensure_ascii=False, sort_keys=True),
        json.dumps(ai_payload, ensure_ascii=False, sort_keys=True),
        json.dumps(context or {}, ensure_ascii=False, sort_keys=True),
    )
    if hasattr(database_or_path, "connect"):
        with database_or_path.connect() as conn:
            conn.execute(
                """
                insert into ai_decisions_log(
                    ts, run_id, cycle_id, mode, stage, symbol, timeframe, divergence, veto, override,
                    baseline_is_real, baseline_entry_gate, ai_effective_entry_gate,
                    baseline_position_action, ai_position_action,
                    baseline_decision_json, ai_decision_json, context_json
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row,
            )
        return
    conn = sqlite3.connect(str(database_or_path))
    try:
        conn.execute(
            """
            insert into ai_decisions_log(
                ts, run_id, cycle_id, mode, stage, symbol, timeframe, divergence, veto, override,
                baseline_is_real, baseline_entry_gate, ai_effective_entry_gate,
                baseline_position_action, ai_position_action,
                baseline_decision_json, ai_decision_json, context_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
        conn.commit()
    finally:
        conn.close()


def summarize_ai_observability(database_or_path: Any, limit: int = 500) -> dict[str, Any]:
    ensure_ai_observability_table(database_or_path)
    if hasattr(database_or_path, "read_sql"):
        df = database_or_path.read_sql(
            "select * from ai_decisions_log order by id desc limit ?",
            (int(limit),),
        )
    else:
        conn = sqlite3.connect(str(database_or_path))
        try:
            df = pd.read_sql_query(
                "select * from ai_decisions_log order by id desc limit ?",
                conn,
                params=(int(limit),),
            )
        finally:
            conn.close()
    if df.empty:
        return {
            "total": 0,
            "divergence_count": 0,
            "veto_count": 0,
            "override_count": 0,
            "real_baseline_count": 0,
            "stages": {},
            "latest_stage": "disabled",
        }
    stages = df["stage"].fillna("disabled").astype(str).value_counts().to_dict()
    return {
        "total": int(len(df)),
        "divergence_count": int(df["divergence"].fillna(0).astype(int).sum()),
        "veto_count": int(df["veto"].fillna(0).astype(int).sum()),
        "override_count": int(df["override"].fillna(0).astype(int).sum()),
        "real_baseline_count": int(df["baseline_is_real"].fillna(0).astype(int).sum()),
        "stages": {str(k): int(v) for k, v in stages.items()},
        "latest_stage": str(df.iloc[0].get("stage", "disabled") or "disabled"),
    }


def recent_ai_observations(database_or_path: Any, limit: int = 20) -> pd.DataFrame:
    ensure_ai_observability_table(database_or_path)
    if hasattr(database_or_path, "read_sql"):
        return database_or_path.read_sql(
            "select * from ai_decisions_log order by id desc limit ?",
            (int(limit),),
        )
    conn = sqlite3.connect(str(database_or_path))
    try:
        return pd.read_sql_query(
            "select * from ai_decisions_log order by id desc limit ?",
            conn,
            params=(int(limit),),
        )
    finally:
        conn.close()
