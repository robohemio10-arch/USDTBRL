from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

from smartcrypto.research.ml_store import MLStore
from smartcrypto.research.quant_validation import (
    build_evaluation_trades_frame,
    build_quant_validation_report,
    promotion_decision,
    run_quant_validation,
    summarize_trade_frame,
)


def test_summarize_trade_frame_reports_core_metrics() -> None:
    frame = pd.DataFrame(
        [
            {"pnl_brl": 10.0, "pnl_pct": 1.0, "fees_brl": 0.3, "slippage_bps": 4.0, "duration_minutes": 10, "drawdown_during_trade_brl": 0.0},
            {"pnl_brl": -5.0, "pnl_pct": -0.5, "fees_brl": 0.2, "slippage_bps": 6.0, "duration_minutes": 20, "drawdown_during_trade_brl": 5.0},
        ]
    )
    metrics = summarize_trade_frame(frame)
    assert metrics["trades"] == 2
    assert metrics["pnl_total_brl"] == 5.0
    assert metrics["fees_total_brl"] == 0.5
    assert metrics["win_rate_pct"] == 50.0
    assert metrics["profit_factor"] == 2.0


def test_promotion_decision_requires_lift_and_drawdown() -> None:
    approved = promotion_decision(
        {"trades": 40, "pnl_total_brl": 120.0, "max_drawdown_brl": -20.0, "profit_factor": 1.5, "sharpe": 1.2},
        {"trades": 40, "pnl_total_brl": 100.0, "max_drawdown_brl": -25.0, "profit_factor": 1.2, "sharpe": 1.0},
        min_trades=30,
        min_pnl_lift_pct=10.0,
    )
    rejected = promotion_decision(
        {"trades": 10, "pnl_total_brl": 80.0, "max_drawdown_brl": -30.0, "profit_factor": 0.9, "sharpe": 0.8},
        {"trades": 40, "pnl_total_brl": 100.0, "max_drawdown_brl": -20.0, "profit_factor": 1.2, "sharpe": 1.0},
        min_trades=30,
        min_pnl_lift_pct=10.0,
    )
    assert approved.approved is True
    assert rejected.approved is False
    assert "trades_insufficient" in rejected.reasons


def _prepare_state_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            create table cycles (
                opened_at text,
                closed_at text,
                regime text,
                entry_price_brl real,
                exit_price_brl real,
                qty_usdt real,
                brl_spent real,
                brl_received real,
                pnl_brl real,
                pnl_pct real,
                safety_count integer,
                exit_reason text,
                status text
            )
            """
        )
        conn.execute(
            """
            create table trades (
                created_at text,
                side text,
                price_brl real,
                qty_usdt real,
                brl_value real,
                fee_brl real,
                reason text,
                mode text,
                regime text
            )
            """
        )
        conn.executemany(
            "insert into cycles values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("2026-01-01T10:00:00+00:00", "2026-01-01T10:15:00+00:00", "sideways", 5.0, 5.1, 10.0, 50.0, 51.0, 1.0, 2.0, 0, "take_profit", "closed"),
                ("2026-01-01T11:00:00+00:00", "2026-01-01T11:20:00+00:00", "trend_up", 5.2, 5.3, 10.0, 52.0, 53.0, 1.0, 1.9, 1, "ai_take_profit", "closed"),
            ],
        )
        conn.executemany(
            "insert into trades values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("2026-01-01T10:00:00+00:00", "buy", 5.0, 10.0, 50.0, 0.05, "entry", "paper", "sideways"),
                ("2026-01-01T10:15:00+00:00", "sell", 5.1, 10.0, 51.0, 0.05, "take_profit", "paper", "sideways"),
                ("2026-01-01T11:00:00+00:00", "buy", 5.2, 10.0, 52.0, 0.05, "entry", "paper", "trend_up"),
                ("2026-01-01T11:20:00+00:00", "sell", 5.3, 10.0, 53.0, 0.05, "ai_take_profit", "paper", "trend_up"),
            ],
        )
        conn.commit()


def test_build_evaluation_trades_frame_classifies_ai_and_heuristic(tmp_path: Path) -> None:
    state_db = tmp_path / "state.sqlite"
    ml_db = tmp_path / "ml_store.sqlite"
    _prepare_state_db(state_db)
    store = MLStore(str(ml_db))
    store.add_rollout_event(
        "USDT/BRL",
        "1m",
        "paper_decision",
        {
            "stage": "paper_decision",
            "enabled": True,
            "effective_entry_gate": True,
        },
    )
    cfg = {"storage": {"db_path": str(state_db), "ml_store_path": str(ml_db)}, "market": {"symbol": "USDT/BRL", "timeframe": "1m"}}
    frame = build_evaluation_trades_frame(cfg, ml_store=store)
    assert len(frame) == 2
    assert set(frame["method"]) == {"heuristic", "ai"}


def test_run_quant_validation_persists_report_and_trade_rows(tmp_path: Path) -> None:
    state_db = tmp_path / "state.sqlite"
    ml_db = tmp_path / "ml_store.sqlite"
    _prepare_state_db(state_db)
    store = MLStore(str(ml_db))
    store.add_rollout_event(
        "USDT/BRL",
        "1m",
        "paper_decision",
        {
            "stage": "paper_decision",
            "enabled": True,
            "effective_entry_gate": True,
        },
    )
    cfg = {
        "storage": {"db_path": str(state_db), "ml_store_path": str(ml_db)},
        "market": {"symbol": "USDT/BRL", "timeframe": "1m"},
        "research": {"quant_validation_min_trades": 1, "quant_validation_min_pnl_lift_pct": 0.0},
    }
    report = run_quant_validation(cfg, persist=True)
    assert report["rows"] == 2
    trades = store.read_df("evaluation_trades")
    reports = store.read_df("evaluation_reports")
    assert len(trades) == 2
    assert len(reports) == 1
    payload = json.loads(reports.iloc[0]["payload_json"])
    assert payload["rows"] == 2


def test_build_quant_validation_report_contains_segments() -> None:
    frame = pd.DataFrame(
        [
            {"method": "heuristic", "pnl_brl": 1.0, "pnl_pct": 1.0, "fees_brl": 0.1, "slippage_bps": 2.0, "duration_minutes": 5.0, "drawdown_during_trade_brl": 0.0, "regime": "sideways", "hour_bucket": 10},
            {"method": "ai", "pnl_brl": 2.0, "pnl_pct": 2.0, "fees_brl": 0.1, "slippage_bps": 1.0, "duration_minutes": 4.0, "drawdown_during_trade_brl": 0.0, "regime": "trend_up", "hour_bucket": 11},
        ]
    )
    report = build_quant_validation_report(frame, min_trades=1, min_pnl_lift_pct=0.0)
    assert "methods" in report
    assert "segments" in report
    assert report["promotion"]["approved"] is True
