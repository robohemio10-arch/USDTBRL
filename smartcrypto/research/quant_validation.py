from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from smartcrypto.research.ml_store import MLStore


@dataclass(frozen=True)
class PromotionDecision:
    approved: bool
    reasons: list[str]
    metrics: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "approved": bool(self.approved),
            "reasons": list(self.reasons),
            "metrics": dict(self.metrics),
        }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        if isinstance(value, str) and not value.strip():
            return default
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except Exception:
        return default


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _parse_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return {}


def _drawdown_from_equity(equity_curve: pd.Series) -> float:
    if equity_curve.empty:
        return 0.0
    running_peak = equity_curve.cummax()
    dd = equity_curve - running_peak
    return float(dd.min())


def _downside_std(returns: pd.Series) -> float:
    downside = returns[returns < 0]
    if downside.empty:
        return 0.0
    return float(downside.std(ddof=0))


def _profit_factor(pnl: pd.Series) -> float:
    gross_profit = float(pnl[pnl > 0].sum())
    gross_loss = abs(float(pnl[pnl < 0].sum()))
    if gross_loss <= 1e-12:
        return gross_profit if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def summarize_trade_frame(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "trades": 0,
            "pnl_total_brl": 0.0,
            "avg_trade_brl": 0.0,
            "avg_trade_pct": 0.0,
            "fees_total_brl": 0.0,
            "slippage_total_bps": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_brl": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "expectancy_brl": 0.0,
            "avg_duration_minutes": 0.0,
            "avg_drawdown_during_trade_brl": 0.0,
        }
    data = frame.copy()
    pnl = pd.to_numeric(data.get("pnl_brl", 0.0), errors="coerce").fillna(0.0)
    trade_pct = pd.to_numeric(data.get("pnl_pct", 0.0), errors="coerce").fillna(0.0)
    fees = pd.to_numeric(data.get("fees_brl", 0.0), errors="coerce").fillna(0.0)
    slippage_bps = pd.to_numeric(data.get("slippage_bps", 0.0), errors="coerce").fillna(0.0)
    duration = pd.to_numeric(data.get("duration_minutes", 0.0), errors="coerce").fillna(0.0)
    trade_drawdown = pd.to_numeric(data.get("drawdown_during_trade_brl", 0.0), errors="coerce").fillna(0.0)
    equity = pnl.cumsum()
    sharpe_denom = float(pnl.std(ddof=0))
    sortino_denom = _downside_std(pnl)
    return {
        "trades": int(len(data)),
        "pnl_total_brl": round(float(pnl.sum()), 8),
        "avg_trade_brl": round(float(pnl.mean()), 8),
        "avg_trade_pct": round(float(trade_pct.mean()), 8),
        "fees_total_brl": round(float(fees.sum()), 8),
        "slippage_total_bps": round(float(slippage_bps.sum()), 8),
        "win_rate_pct": round(float((pnl > 0).mean() * 100.0), 4),
        "profit_factor": round(float(_profit_factor(pnl)), 8),
        "max_drawdown_brl": round(float(_drawdown_from_equity(equity)), 8),
        "sharpe": round(float(pnl.mean() / sharpe_denom), 8) if sharpe_denom > 1e-12 else 0.0,
        "sortino": round(float(pnl.mean() / sortino_denom), 8) if sortino_denom > 1e-12 else 0.0,
        "expectancy_brl": round(float(pnl.mean()), 8),
        "avg_duration_minutes": round(float(duration.mean()), 4),
        "avg_drawdown_during_trade_brl": round(float(trade_drawdown.mean()), 8),
    }


def segment_metrics(frame: pd.DataFrame, segment_col: str) -> list[dict[str, Any]]:
    if frame.empty or segment_col not in frame.columns:
        return []
    rows: list[dict[str, Any]] = []
    grouped = frame.groupby(segment_col, dropna=False)
    for segment, group in grouped:
        row = summarize_trade_frame(group)
        row[segment_col] = _safe_str(segment, "unknown")
        rows.append(row)
    return rows


def compare_methods(frame: pd.DataFrame, baseline_method: str = "heuristic", candidate_method: str = "ai") -> dict[str, Any]:
    data = frame.copy()
    if data.empty or "method" not in data.columns:
        return {
            "baseline": summarize_trade_frame(pd.DataFrame()),
            "candidate": summarize_trade_frame(pd.DataFrame()),
            "delta": {},
        }
    baseline = summarize_trade_frame(data[data["method"] == baseline_method])
    candidate = summarize_trade_frame(data[data["method"] == candidate_method])
    delta: dict[str, Any] = {}
    keys = set(baseline) & set(candidate)
    for key in keys:
        if isinstance(baseline[key], (int, float)) and isinstance(candidate[key], (int, float)):
            delta[key] = round(float(candidate[key]) - float(baseline[key]), 8)
    return {
        "baseline_method": baseline_method,
        "candidate_method": candidate_method,
        "baseline": baseline,
        "candidate": candidate,
        "delta": delta,
    }


def promotion_decision(
    metrics_ai: Mapping[str, Any],
    metrics_baseline: Mapping[str, Any],
    *,
    min_trades: int = 30,
    min_pnl_lift_pct: float = 10.0,
    allow_equal_drawdown: bool = True,
) -> PromotionDecision:
    reasons: list[str] = []
    ai_trades = int(metrics_ai.get("trades", 0) or 0)
    base_pnl = _safe_float(metrics_baseline.get("pnl_total_brl", 0.0))
    ai_pnl = _safe_float(metrics_ai.get("pnl_total_brl", 0.0))
    base_dd = abs(_safe_float(metrics_baseline.get("max_drawdown_brl", 0.0)))
    ai_dd = abs(_safe_float(metrics_ai.get("max_drawdown_brl", 0.0)))
    base_pf = _safe_float(metrics_baseline.get("profit_factor", 0.0))
    ai_pf = _safe_float(metrics_ai.get("profit_factor", 0.0))
    base_sharpe = _safe_float(metrics_baseline.get("sharpe", 0.0))
    ai_sharpe = _safe_float(metrics_ai.get("sharpe", 0.0))

    if ai_trades < int(min_trades):
        reasons.append("trades_insufficient")

    pnl_threshold = base_pnl * (1.0 + float(min_pnl_lift_pct) / 100.0)
    if ai_pnl <= pnl_threshold:
        reasons.append("pnl_lift_insufficient")

    if allow_equal_drawdown:
        if ai_dd > base_dd + 1e-9:
            reasons.append("drawdown_worse_than_baseline")
    elif ai_dd >= base_dd - 1e-9:
        reasons.append("drawdown_not_better")

    if ai_pf + 1e-9 < base_pf:
        reasons.append("profit_factor_below_baseline")
    if ai_sharpe + 1e-9 < base_sharpe:
        reasons.append("sharpe_below_baseline")

    return PromotionDecision(
        approved=not reasons,
        reasons=reasons or ["approved"],
        metrics={
            "min_trades": int(min_trades),
            "min_pnl_lift_pct": float(min_pnl_lift_pct),
            "candidate_trades": ai_trades,
            "candidate_pnl_total_brl": ai_pnl,
            "baseline_pnl_total_brl": base_pnl,
            "candidate_max_drawdown_brl": ai_dd,
            "baseline_max_drawdown_brl": base_dd,
            "candidate_profit_factor": ai_pf,
            "baseline_profit_factor": base_pf,
            "candidate_sharpe": ai_sharpe,
            "baseline_sharpe": base_sharpe,
        },
    )


def build_quant_validation_report(
    evaluation_trades: pd.DataFrame,
    *,
    baseline_method: str = "heuristic",
    candidate_method: str = "ai",
    min_trades: int = 30,
    min_pnl_lift_pct: float = 10.0,
) -> dict[str, Any]:
    compare = compare_methods(evaluation_trades, baseline_method=baseline_method, candidate_method=candidate_method)
    by_regime = {
        baseline_method: segment_metrics(evaluation_trades[evaluation_trades.get("method") == baseline_method], "regime"),
        candidate_method: segment_metrics(evaluation_trades[evaluation_trades.get("method") == candidate_method], "regime"),
    }
    by_hour = {
        baseline_method: segment_metrics(evaluation_trades[evaluation_trades.get("method") == baseline_method], "hour_bucket"),
        candidate_method: segment_metrics(evaluation_trades[evaluation_trades.get("method") == candidate_method], "hour_bucket"),
    }
    promotion = promotion_decision(
        compare["candidate"],
        compare["baseline"],
        min_trades=min_trades,
        min_pnl_lift_pct=min_pnl_lift_pct,
    )
    report = {
        "methods": compare,
        "segments": {"by_regime": by_regime, "by_hour": by_hour},
        "promotion": promotion.as_dict(),
    }
    return report


def _load_table(db_path: str | Path, query: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    with sqlite3.connect(str(db_path)) as conn:
        return pd.read_sql_query(query, conn, params=params)


def _classify_method(opened_at: pd.Timestamp, exit_reason: str, rollout_events: pd.DataFrame) -> tuple[str, str]:
    if str(exit_reason).startswith("ai_"):
        return "ai", "ai_exit_reason"
    if rollout_events.empty:
        return "heuristic", "no_rollout_history"
    eligible = rollout_events[rollout_events["ts"] <= opened_at]
    if eligible.empty:
        return "heuristic", "no_prior_rollout"
    latest = eligible.iloc[-1]
    payload = _parse_payload(latest.get("payload_json", "{}"))
    stage = _safe_str(payload.get("stage", latest.get("stage", "")), "")
    enabled = bool(payload.get("enabled", True))
    effective_gate = bool(payload.get("effective_entry_gate", payload.get("final_gate", True)))
    if enabled and stage in {"paper_decision", "live_partial"} and effective_gate:
        return "ai", stage
    return "heuristic", stage or "rollout_not_effective"


def build_evaluation_trades_frame(cfg: Mapping[str, Any], ml_store: MLStore | None = None) -> pd.DataFrame:
    storage = cfg.get("storage", {}) if isinstance(cfg, Mapping) else {}
    state_db_path = str(storage.get("db_path", "data/usdtbrl_live.sqlite"))
    symbol = _safe_str(cfg.get("market", {}).get("symbol", "UNKNOWN"), "UNKNOWN")
    timeframe = _safe_str(cfg.get("market", {}).get("timeframe", "unknown"), "unknown")

    cycles = _load_table(
        state_db_path,
        "select opened_at, closed_at, regime, entry_price_brl, exit_price_brl, qty_usdt, brl_spent, brl_received, pnl_brl, pnl_pct, safety_count, exit_reason, status from cycles where status='closed' order by opened_at asc",
    )
    if cycles.empty:
        return pd.DataFrame(
            columns=[
                "opened_at",
                "closed_at",
                "symbol",
                "timeframe",
                "method",
                "stage",
                "entry_price_brl",
                "exit_price_brl",
                "qty_usdt",
                "pnl_brl",
                "pnl_pct",
                "fees_brl",
                "slippage_bps",
                "drawdown_during_trade_brl",
                "duration_minutes",
                "regime",
                "hour_bucket",
                "details_json",
            ]
        )
    trades = _load_table(
        state_db_path,
        "select created_at, side, price_brl, qty_usdt, brl_value, fee_brl, reason, mode, regime from trades order by created_at asc",
    )
    rollout_events = pd.DataFrame()
    if ml_store is not None:
        rollout_events = ml_store.read_df("rollout_events", limit=None)
    elif "ml_store_path" in storage:
        rollout_events = MLStore(str(storage["ml_store_path"])).read_df("rollout_events", limit=None)
    if not rollout_events.empty:
        rollout_events = rollout_events.copy()
        rollout_events["ts"] = pd.to_datetime(rollout_events["ts"], errors="coerce", utc=True)
        rollout_events = rollout_events.sort_values("ts")

    cycles = cycles.copy()
    cycles["opened_at"] = pd.to_datetime(cycles["opened_at"], errors="coerce", utc=True)
    cycles["closed_at"] = pd.to_datetime(cycles["closed_at"], errors="coerce", utc=True)
    if not trades.empty:
        trades = trades.copy()
        trades["created_at"] = pd.to_datetime(trades["created_at"], errors="coerce", utc=True)

    rows: list[dict[str, Any]] = []
    for _, cycle in cycles.iterrows():
        opened_at = cycle["opened_at"]
        closed_at = cycle["closed_at"]
        if pd.isna(opened_at) or pd.isna(closed_at):
            continue
        cycle_trades = trades[(trades["created_at"] >= opened_at) & (trades["created_at"] <= closed_at)] if not trades.empty else pd.DataFrame()
        fees_brl = float(pd.to_numeric(cycle_trades.get("fee_brl", 0.0), errors="coerce").fillna(0.0).sum()) if not cycle_trades.empty else 0.0
        buy_avg = 0.0
        sell_avg = 0.0
        if not cycle_trades.empty and "side" in cycle_trades.columns:
            buys = cycle_trades[cycle_trades["side"].astype(str).str.lower() == "buy"]
            sells = cycle_trades[cycle_trades["side"].astype(str).str.lower() == "sell"]
            if not buys.empty:
                buy_avg = float(pd.to_numeric(buys["price_brl"], errors="coerce" ).fillna(0.0).mean())
            if not sells.empty:
                sell_avg = float(pd.to_numeric(sells["price_brl"], errors="coerce").fillna(0.0).mean())
        slippage_bps = 0.0
        entry_price = _safe_float(cycle.get("entry_price_brl"), buy_avg)
        exit_price = _safe_float(cycle.get("exit_price_brl"), sell_avg)
        if entry_price > 0 and buy_avg > 0:
            slippage_bps += abs((buy_avg / entry_price) - 1.0) * 10_000.0
        if exit_price > 0 and sell_avg > 0:
            slippage_bps += abs((sell_avg / exit_price) - 1.0) * 10_000.0
        method, stage = _classify_method(opened_at, _safe_str(cycle.get("exit_reason", "")), rollout_events)
        rows.append(
            {
                "opened_at": opened_at.isoformat(),
                "closed_at": closed_at.isoformat(),
                "symbol": symbol,
                "timeframe": timeframe,
                "method": method,
                "stage": stage,
                "entry_price_brl": entry_price,
                "exit_price_brl": exit_price,
                "qty_usdt": _safe_float(cycle.get("qty_usdt", 0.0)),
                "pnl_brl": _safe_float(cycle.get("pnl_brl", 0.0)),
                "pnl_pct": _safe_float(cycle.get("pnl_pct", 0.0)),
                "fees_brl": round(fees_brl, 8),
                "slippage_bps": round(slippage_bps, 8),
                "drawdown_during_trade_brl": max(0.0, -_safe_float(cycle.get("pnl_brl", 0.0)) if _safe_float(cycle.get("pnl_brl", 0.0)) < 0 else 0.0),
                "duration_minutes": round((closed_at - opened_at).total_seconds() / 60.0, 4),
                "regime": _safe_str(cycle.get("regime", "unknown"), "unknown"),
                "hour_bucket": int(opened_at.hour),
                "details_json": json.dumps(
                    {
                        "exit_reason": _safe_str(cycle.get("exit_reason", "")),
                        "safety_count": int(_safe_float(cycle.get("safety_count", 0), 0.0)),
                        "trade_count": int(len(cycle_trades)),
                    },
                    ensure_ascii=False,
                ),
            }
        )
    return pd.DataFrame(rows)


def persist_evaluation_trades(store: MLStore, frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    inserted = 0
    for row in frame.to_dict(orient="records"):
        store.add_evaluation_trade(row)
        inserted += 1
    return inserted


def run_quant_validation(cfg: Mapping[str, Any], *, persist: bool = True) -> dict[str, Any]:
    storage = cfg.get("storage", {}) if isinstance(cfg, Mapping) else {}
    ml_store = MLStore(str(storage.get("ml_store_path", "data/ml_store.sqlite")))
    evaluation_frame = build_evaluation_trades_frame(cfg, ml_store=ml_store)
    if persist:
        ml_store.clear_table("evaluation_trades")
        if not evaluation_frame.empty:
            persist_evaluation_trades(ml_store, evaluation_frame)
    report = build_quant_validation_report(
        evaluation_frame,
        baseline_method=str(cfg.get("research", {}).get("quant_validation_baseline_method", "heuristic")),
        candidate_method=str(cfg.get("research", {}).get("quant_validation_candidate_method", "ai")),
        min_trades=int(cfg.get("research", {}).get("quant_validation_min_trades", 30) or 30),
        min_pnl_lift_pct=float(cfg.get("research", {}).get("quant_validation_min_pnl_lift_pct", 10.0) or 10.0),
    )
    report["rows"] = int(len(evaluation_frame))
    report["symbol"] = _safe_str(cfg.get("market", {}).get("symbol", "UNKNOWN"), "UNKNOWN")
    report["timeframe"] = _safe_str(cfg.get("market", {}).get("timeframe", "unknown"), "unknown")
    if persist:
        ml_store.add_evaluation_report(report)
    return report
