from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Mapping

import pandas as pd


def _safe_db_path(cfg: Mapping[str, Any]) -> Path | None:
    raw = str(cfg.get("storage", {}).get("db_path", "") or "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.exists() else None


def _read_order_events(db_path: Path) -> pd.DataFrame:
    query = """
        select bot_order_id, side, order_type, state, price_brl, qty_usdt, executed_qty_usdt,
               brl_value, source, note, event_time
        from order_events
        order by event_time asc, id asc
    """
    try:
        with sqlite3.connect(str(db_path)) as conn:
            return pd.read_sql_query(query, conn)
    except Exception:
        return pd.DataFrame()


def _summarize_group(group: pd.DataFrame) -> dict[str, Any]:
    ordered = group.sort_values("event_time").reset_index(drop=True)
    submitted = ordered[ordered["state"].isin(["submitted", "partially_filled", "planned"])].head(1)
    filled = ordered[ordered["state"] == "filled"].tail(1)
    cancelled = ordered[ordered["state"].isin(["cancelled", "canceled", "failed", "rejected", "expired"])].tail(1)
    submitted_ts = pd.to_datetime(submitted["event_time"].iloc[0], errors="coerce", utc=True) if not submitted.empty else pd.NaT
    terminal_ts = pd.to_datetime(filled["event_time"].iloc[0], errors="coerce", utc=True) if not filled.empty else (
        pd.to_datetime(cancelled["event_time"].iloc[0], errors="coerce", utc=True) if not cancelled.empty else pd.NaT
    )
    submitted_price = float(submitted["price_brl"].iloc[0]) if not submitted.empty and pd.notna(submitted["price_brl"].iloc[0]) else None
    filled_price = float(filled["price_brl"].iloc[0]) if not filled.empty and pd.notna(filled["price_brl"].iloc[0]) else None
    side = str(ordered["side"].dropna().iloc[0]).lower() if not ordered["side"].dropna().empty else "unknown"
    if submitted_price and filled_price:
        if side == "buy":
            cost_bps = max(0.0, (filled_price / submitted_price - 1.0) * 10_000.0)
        elif side == "sell":
            cost_bps = max(0.0, (submitted_price / filled_price - 1.0) * 10_000.0)
        else:
            cost_bps = abs(filled_price / submitted_price - 1.0) * 10_000.0
    else:
        cost_bps = None
    latency_s = None
    if pd.notna(submitted_ts) and pd.notna(terminal_ts):
        latency_s = max(0.0, float((terminal_ts - submitted_ts).total_seconds()))
    return {
        "bot_order_id": str(ordered["bot_order_id"].iloc[0]),
        "side": side,
        "order_type": str(ordered["order_type"].dropna().iloc[0]).lower() if not ordered["order_type"].dropna().empty else "unknown",
        "filled": bool(not filled.empty),
        "cost_bps": cost_bps,
        "latency_seconds": latency_s,
        "submitted_price_brl": submitted_price,
        "filled_price_brl": filled_price,
        "submitted_ts": submitted_ts.isoformat() if pd.notna(submitted_ts) else None,
        "terminal_ts": terminal_ts.isoformat() if pd.notna(terminal_ts) else None,
    }


def load_empirical_execution_summary(cfg: Mapping[str, Any]) -> dict[str, Any]:
    db_path = _safe_db_path(cfg)
    if db_path is None:
        return {"available": False, "reason": "state_db_missing", "rows": 0}
    events = _read_order_events(db_path)
    if events.empty or "bot_order_id" not in events.columns:
        return {"available": False, "reason": "no_order_events", "rows": 0}
    records = [_summarize_group(group) for _, group in events.groupby("bot_order_id")]
    frame = pd.DataFrame(records)
    if frame.empty:
        return {"available": False, "reason": "no_grouped_events", "rows": 0}
    frame = frame[frame["order_type"].isin(["limit", "market", "unknown"])]
    available_cost = pd.to_numeric(frame.get("cost_bps"), errors="coerce")
    available_latency = pd.to_numeric(frame.get("latency_seconds"), errors="coerce")
    fill_rate = float(frame["filled"].astype(float).mean()) if "filled" in frame.columns else 0.0
    by_side: dict[str, Any] = {}
    for side, group in frame.groupby("side", dropna=False):
        by_side[str(side)] = {
            "rows": int(len(group)),
            "fill_rate": round(float(group["filled"].astype(float).mean()), 8),
            "median_cost_bps": round(float(pd.to_numeric(group.get("cost_bps"), errors="coerce").dropna().median()) if pd.to_numeric(group.get("cost_bps"), errors="coerce").dropna().size else 0.0, 8),
            "p90_latency_seconds": round(float(pd.to_numeric(group.get("latency_seconds"), errors="coerce").dropna().quantile(0.9)) if pd.to_numeric(group.get("latency_seconds"), errors="coerce").dropna().size else 0.0, 8),
        }
    return {
        "available": True,
        "rows": int(len(frame)),
        "fill_rate": round(fill_rate, 8),
        "median_cost_bps": round(float(available_cost.dropna().median()) if available_cost.dropna().size else 0.0, 8),
        "p90_latency_seconds": round(float(available_latency.dropna().quantile(0.9)) if available_latency.dropna().size else 0.0, 8),
        "by_side": by_side,
    }
