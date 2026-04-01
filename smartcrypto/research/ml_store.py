from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def _parse_maybe_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return {}


class MLStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self.conn() as c:
            c.execute(
                """
                create table if not exists feature_snapshots (
                    id integer primary key autoincrement,
                    ts text not null,
                    symbol text not null,
                    timeframe text not null,
                    dataset_name text not null,
                    payload_json text not null
                )
                """
            )
            c.execute(
                """
                create table if not exists shadow_predictions (
                    id integer primary key autoincrement,
                    ts text not null,
                    symbol text not null,
                    timeframe text not null,
                    methodology text not null,
                    payload_json text not null
                )
                """
            )
            c.execute(
                """
                create table if not exists model_registry (
                    id integer primary key autoincrement,
                    ts text not null,
                    model_name text not null,
                    version text not null,
                    metrics_json text not null,
                    params_json text not null,
                    artifact_json text not null
                )
                """
            )
            c.execute(
                """
                create table if not exists rollout_events (
                    id integer primary key autoincrement,
                    ts text not null,
                    symbol text not null,
                    timeframe text not null,
                    stage text not null,
                    payload_json text not null
                )
                """
            )
            c.execute(
                """
                create table if not exists evaluation_trades (
                    id integer primary key autoincrement,
                    opened_at text not null,
                    closed_at text not null,
                    symbol text not null,
                    timeframe text not null,
                    method text not null,
                    stage text not null,
                    entry_price_brl real not null,
                    exit_price_brl real not null,
                    qty_usdt real not null,
                    pnl_brl real not null,
                    pnl_pct real not null,
                    fees_brl real not null,
                    slippage_bps real not null,
                    drawdown_during_trade_brl real not null,
                    duration_minutes real not null,
                    regime text not null,
                    hour_bucket integer not null,
                    details_json text not null
                )
                """
            )
            c.execute(
                """
                create table if not exists evaluation_reports (
                    id integer primary key autoincrement,
                    ts text not null,
                    symbol text not null,
                    timeframe text not null,
                    payload_json text not null
                )
                """
            )

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def add_feature_snapshot(self, symbol: str, timeframe: str, dataset_name: str, payload: dict[str, Any]) -> None:
        with self.conn() as c:
            c.execute(
                "insert into feature_snapshots(ts, symbol, timeframe, dataset_name, payload_json) values (?, ?, ?, ?, ?)",
                (self._utc_now(), symbol, timeframe, dataset_name, json.dumps(payload)),
            )

    def add_shadow_prediction(self, symbol: str, timeframe: str, methodology: str, payload: dict[str, Any]) -> None:
        with self.conn() as c:
            c.execute(
                "insert into shadow_predictions(ts, symbol, timeframe, methodology, payload_json) values (?, ?, ?, ?, ?)",
                (self._utc_now(), symbol, timeframe, methodology, json.dumps(payload)),
            )

    def add_rollout_event(self, symbol: str, timeframe: str, stage: str, payload: dict[str, Any]) -> None:
        with self.conn() as c:
            c.execute(
                "insert into rollout_events(ts, symbol, timeframe, stage, payload_json) values (?, ?, ?, ?, ?)",
                (self._utc_now(), symbol, timeframe, stage, json.dumps(payload)),
            )

    def register_model(
        self,
        model_name: str,
        version: str,
        *,
        metrics: dict[str, Any],
        params: dict[str, Any],
        artifact: dict[str, Any],
    ) -> None:
        with self.conn() as c:
            c.execute(
                "insert into model_registry(ts, model_name, version, metrics_json, params_json, artifact_json) values (?, ?, ?, ?, ?, ?)",
                (self._utc_now(), model_name, version, json.dumps(metrics), json.dumps(params), json.dumps(artifact)),
            )

    def add_evaluation_trade(self, payload: dict[str, Any]) -> None:
        with self.conn() as c:
            c.execute(
                """
                insert into evaluation_trades(
                    opened_at, closed_at, symbol, timeframe, method, stage, entry_price_brl, exit_price_brl, qty_usdt,
                    pnl_brl, pnl_pct, fees_brl, slippage_bps, drawdown_during_trade_brl, duration_minutes, regime,
                    hour_bucket, details_json
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(payload.get("opened_at", "")),
                    str(payload.get("closed_at", "")),
                    str(payload.get("symbol", "UNKNOWN")),
                    str(payload.get("timeframe", "unknown")),
                    str(payload.get("method", "heuristic")),
                    str(payload.get("stage", "unknown")),
                    float(payload.get("entry_price_brl", 0.0) or 0.0),
                    float(payload.get("exit_price_brl", 0.0) or 0.0),
                    float(payload.get("qty_usdt", 0.0) or 0.0),
                    float(payload.get("pnl_brl", 0.0) or 0.0),
                    float(payload.get("pnl_pct", 0.0) or 0.0),
                    float(payload.get("fees_brl", 0.0) or 0.0),
                    float(payload.get("slippage_bps", 0.0) or 0.0),
                    float(payload.get("drawdown_during_trade_brl", 0.0) or 0.0),
                    float(payload.get("duration_minutes", 0.0) or 0.0),
                    str(payload.get("regime", "unknown")),
                    int(payload.get("hour_bucket", -1) or -1),
                    json.dumps(payload.get("details") or _parse_maybe_json(payload.get("details_json", "{}"))),
                ),
            )

    def add_evaluation_report(self, payload: dict[str, Any]) -> None:
        with self.conn() as c:
            c.execute(
                "insert into evaluation_reports(ts, symbol, timeframe, payload_json) values (?, ?, ?, ?)",
                (
                    self._utc_now(),
                    str(payload.get("symbol", "UNKNOWN")),
                    str(payload.get("timeframe", "unknown")),
                    json.dumps(payload),
                ),
            )

    def clear_table(self, table: str) -> None:
        allowed = {"evaluation_trades", "evaluation_reports"}
        if table not in allowed:
            raise ValueError(f"Tabela não permitida para limpeza: {table}")
        with self.conn() as c:
            c.execute(f"delete from {table}")

    def read_df(self, table: str, limit: int | None = None) -> pd.DataFrame:
        allowed = {"feature_snapshots", "shadow_predictions", "model_registry", "rollout_events", "evaluation_trades", "evaluation_reports"}
        if table not in allowed:
            raise ValueError(f"Tabela não permitida: {table}")
        query = f"select * from {table} order by id desc"
        if table == "evaluation_trades":
            query = "select * from evaluation_trades order by opened_at desc"
        if limit is not None:
            query += f" limit {int(limit)}"
        with self.conn() as c:
            return pd.read_sql_query(query, c)
