from __future__ import annotations

import os
import sys
import time
from typing import Any

from smartcrypto.common.health import health_report
from smartcrypto.runtime.ai_observability import summarize_ai_observability
from smartcrypto.runtime.audit import recent_critical_events, summarize_runtime_session
from smartcrypto.runtime.cache import read_preflight_cache, read_runtime_manifest_cache
from smartcrypto.state.portfolio import Portfolio
from smartcrypto.state.position_manager import PositionManager
from smartcrypto.state.store import PositionState, StateStore, utc_now


def reentry_remaining_seconds(store: StateStore) -> int:
    value = store.get_flag("reentry_block_until", 0)
    try:
        until_epoch = float(value or 0.0)
    except Exception:
        until_epoch = 0.0
    if until_epoch <= 0:
        return 0
    return max(0, int(until_epoch - time.time()))


def reentry_price_threshold(store: StateStore) -> float:
    value = store.get_flag("reentry_price_below", 0)
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except Exception:
        return int(default)



def paper_panel(store: StateStore, price: float, cfg: dict[str, Any]) -> dict[str, Any]:
    position = store.get_position()
    cycles = store.read_df("cycles", 10000)
    closed_cycles = 0
    total_spent_all_cycles_brl = 0.0
    entry_price_brl = _safe_float(position.avg_price_brl)
    if not cycles.empty:
        if "status" in cycles.columns:
            closed_cycles = int(cycles["status"].astype(str).str.lower().eq("closed").sum())
            open_cycles = cycles[cycles["status"].astype(str).str.lower().eq("open")].copy()
        else:
            closed_cycles = int(cycles["closed_at"].notna().sum()) if "closed_at" in cycles.columns else 0
            open_cycles = cycles[cycles["closed_at"].isna()].copy() if "closed_at" in cycles.columns else cycles.copy()
        if "brl_spent" in cycles.columns:
            total_spent_all_cycles_brl = _safe_float(cycles["brl_spent"].fillna(0.0).sum())
        if not open_cycles.empty and "entry_price_brl" in open_cycles.columns:
            entry_price_brl = _safe_float(open_cycles.iloc[-1].get("entry_price_brl"))
    invested_this_cycle_brl = _safe_float(position.brl_spent)
    avg_price_brl = _safe_float(position.avg_price_brl)
    pnl_pct = 0.0
    if invested_this_cycle_brl > 0:
        pnl_pct = (_safe_float(position.unrealized_pnl_brl) / invested_this_cycle_brl) * 100.0
    realized_profit_brl = _safe_float(position.realized_pnl_brl)
    ramp_number = _safe_int(position.safety_count)
    return {
        "symbol": str(cfg.get("market", {}).get("symbol", "USDT/BRL") or "USDT/BRL"),
        "mode": str(cfg.get("execution", {}).get("mode", "paper") or "paper"),
        "run_active": True,
        "entry_price_brl": entry_price_brl,
        "ramp_number": ramp_number,
        "ramps_done": ramp_number,
        "avg_price_brl": avg_price_brl,
        "current_price_brl": _safe_float(price),
        "pnl_pct": pnl_pct,
        "closed_cycles": closed_cycles,
        "invested_this_cycle_brl": invested_this_cycle_brl,
        "realized_profit_total_brl": realized_profit_brl,
        "realized_profit_brl": realized_profit_brl,
        "total_spent_all_cycles_brl": total_spent_all_cycles_brl,
    }


def _ansi_enabled() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    if os.name != "nt":
        return bool(getattr(sys.stdout, "isatty", lambda: False)())
    return bool(
        os.getenv("WT_SESSION")
        or os.getenv("TERM")
        or os.getenv("ANSICON")
        or os.getenv("ConEmuANSI") == "ON"
        or os.getenv("TERM_PROGRAM")
        or getattr(sys.stdout, "isatty", lambda: False)()
    )


def _ansi_pnl_text(value: float) -> str:
    text = f"{value:,.2f}%"
    if not _ansi_enabled():
        return text
    if value > 0:
        return f"\x1b[32m{text}\x1b[0m"
    if value < 0:
        return f"\x1b[31m{text}\x1b[0m"
    return text


def _ansi_money_text(value: float) -> str:
    text = f"{value:,.2f}"
    if not _ansi_enabled():
        return text
    if value > 0:
        return f"\x1b[32m{text}\x1b[0m"
    if value < 0:
        return f"\x1b[31m{text}\x1b[0m"
    return text


def _box_line(left: str, join: str, right: str, widths: list[int]) -> str:
    return left + join.join("─" * (width + 2) for width in widths) + right


def render_paper_panel_table(panel: dict[str, Any]) -> str:
    realized_profit = _safe_float(panel.get("realized_profit_brl", panel.get("realized_profit_total_brl")))
    columns = [
        ("Moeda/USDT/BRL", str(panel.get("symbol", "USDT/BRL") or "USDT/BRL")),
        ("Modo Paper/Live", str(panel.get("mode", "paper") or "paper").upper()),
        ("Run sim/não", "SIM" if bool(panel.get("run_active", False)) else "NÃO"),
        ("Valor de entrada", f"{_safe_float(panel.get('entry_price_brl')):,.4f}"),
        ("Número da rampa", str(_safe_int(panel.get("ramps_done", panel.get("ramp_number"))))),
        ("Valor médio", f"{_safe_float(panel.get('avg_price_brl')):,.4f}"),
        ("Valor atual", f"{_safe_float(panel.get('current_price_brl')):,.4f}"),
        ("PNL em %", _ansi_pnl_text(_safe_float(panel.get("pnl_pct")))),
        ("Ciclos realizados", str(_safe_int(panel.get("closed_cycles")))),
        ("Empenhado neste ciclo", f"{_safe_float(panel.get('invested_this_cycle_brl')):,.2f}"),
        ("Lucro total ciclos", _ansi_money_text(realized_profit)),
        ("Montante total ciclos", f"{_safe_float(panel.get('total_spent_all_cycles_brl')):,.2f}"),
    ]
    plain_values = [
        str(panel.get("symbol", "USDT/BRL") or "USDT/BRL"),
        str(panel.get("mode", "paper") or "paper").upper(),
        "SIM" if bool(panel.get("run_active", False)) else "NÃO",
        f"{_safe_float(panel.get('entry_price_brl')):,.4f}",
        str(_safe_int(panel.get("ramps_done", panel.get("ramp_number")))),
        f"{_safe_float(panel.get('avg_price_brl')):,.4f}",
        f"{_safe_float(panel.get('current_price_brl')):,.4f}",
        f"{_safe_float(panel.get('pnl_pct')):,.2f}%",
        str(_safe_int(panel.get("closed_cycles"))),
        f"{_safe_float(panel.get('invested_this_cycle_brl')):,.2f}",
        f"{realized_profit:,.2f}",
        f"{_safe_float(panel.get('total_spent_all_cycles_brl')):,.2f}",
    ]
    widths = [max(len(label), len(value)) for (label, _), value in zip(columns, plain_values)]
    top = _box_line("┌", "┬", "┐", widths)
    mid = _box_line("├", "┼", "┤", widths)
    bottom = _box_line("└", "┴", "┘", widths)
    header = "│" + "│".join(f" {label.ljust(width)} " for (label, _), width in zip(columns, widths)) + "│"
    values = "│" + "│".join(
        f" {str(value).rjust(width)} " for value, width in zip([v for _, v in columns], widths)
    ) + "│"
    return "\n".join([top, header, mid, values, bottom])

def display_paper_panel_table(panel: dict[str, Any]) -> None:
    clear_cmd = "cls" if os.name == "nt" else "clear"
    os.system(clear_cmd)
    print(render_paper_panel_table(panel), flush=True)


def log_snapshot(
    store: StateStore,
    *,
    price: float,
    position: PositionState | None = None,
    cfg: dict[str, Any],
    regime: str,
    meta: dict[str, Any] | None = None,
) -> None:
    portfolio = Portfolio(store, position_manager=PositionManager(store))
    view = portfolio.runtime_view(
        mark_price_brl=price,
        initial_cash_brl=float(cfg["portfolio"]["initial_cash_brl"]),
    )
    store.add_snapshot(
        last_price_brl=price,
        equity_brl=view.equity_brl,
        cash_brl=view.cash_brl,
        pos_value_brl=view.position_notional_brl,
        realized_pnl_brl=view.realized_pnl_brl,
        unrealized_pnl_brl=view.unrealized_pnl_brl,
        drawdown_pct=view.drawdown_pct,
        regime=regime,
        meta=meta or {},
    )


def status_payload(store: StateStore, price: float, cfg: dict[str, Any]) -> dict[str, Any]:
    manager = PositionManager(store)
    portfolio = Portfolio(store, position_manager=manager)
    view = portfolio.runtime_view(
        mark_price_brl=price,
        initial_cash_brl=float(cfg["portfolio"]["initial_cash_brl"]),
    )
    active_locks = store.list_active_dispatch_locks(limit=5)
    panel = paper_panel(store, price, cfg)
    payload = {
        "time": utc_now(),
        "price_brl": round(price, 6),
        "paused": bool(store.get_flag("paused", False)),
        "position": view.position,
        "portfolio": {
            "cash_brl": view.cash_brl,
            "equity_brl": view.equity_brl,
            "position_notional_brl": view.position_notional_brl,
            "invested_brl": view.invested_brl,
            "unrealized_pnl_brl": view.unrealized_pnl_brl,
            "realized_pnl_brl": view.realized_pnl_brl,
            "drawdown_pct": view.drawdown_pct,
        },
        "cash_brl": view.cash_brl,
        "equity_brl": view.equity_brl,
        "paper_panel": panel,
        "flags": {
            "force_sell_requested": store.get_flag("force_sell_requested", False),
            "reset_cycle_requested": store.get_flag("reset_cycle_requested", False),
            "reentry_block_until": store.get_flag("reentry_block_until", 0),
            "reentry_remaining_seconds": reentry_remaining_seconds(store),
            "reentry_price_below": reentry_price_threshold(store),
            "live_reconcile_required": store.get_flag("live_reconcile_required", False),
            "consecutive_error_count": int(store.get_flag("consecutive_error_count", 0) or 0),
            "pause_after_sell_requested": store.get_flag("pause_after_sell_requested", False),
        },
        "live_hardening": {
            "active_dispatch_locks": [
                {
                    "bot_order_id": str(row.get("bot_order_id") or ""),
                    "side": str(row.get("side") or ""),
                    "reason": str(row.get("reason") or ""),
                    "status": str(row.get("status") or ""),
                    "updated_at": str(row.get("updated_at") or ""),
                    "client_order_id": str(row.get("client_order_id") or ""),
                }
                for row in active_locks
            ],
            "active_dispatch_lock_count": len(active_locks),
        },
    }
    payload["health"] = health_report(
        cfg, store, interval=str(cfg.get("market", {}).get("timeframe", "15m"))
    )
    return payload


def runtime_status_summary(
    cfg: dict[str, Any],
    store: StateStore,
    *,
    price: float | None = None,
) -> dict[str, Any]:
    effective_price = float(price if price is not None else 0.0)
    base = status_payload(store, effective_price, cfg)
    manifest = cfg.get("__operational_manifest", {})
    if not isinstance(manifest, dict) or not manifest:
        manifest = read_runtime_manifest_cache(cfg)
    preflight = cfg.get("__preflight", {})
    if not isinstance(preflight, dict) or not preflight:
        preflight = read_preflight_cache(cfg)
    ai_summary = summarize_ai_observability(store.database, limit=500)
    run_id = str(manifest.get("run_id", "") or cfg.get("__run_id", "") or "")
    session = summarize_runtime_session(
        store.database,
        run_id=run_id,
        boot_timestamp=str(manifest.get("boot_timestamp", "") or ""),
    )
    critical_rows = recent_critical_events(store.database, run_id=run_id, limit=10)
    return {
        "manifest": manifest,
        "runtime": base,
        "preflight": preflight,
        "flags": dict(cfg.get("__feature_flags", {}) or {}),
        "mode": str(cfg.get("execution", {}).get("mode", "") or ""),
        "run_id": run_id,
        "ai_summary": ai_summary,
        "critical_events": critical_rows,
        "session": session,
        "protocol_version": str(manifest.get("protocol_version", "") or ""),
        "experiment_profile": str(manifest.get("experiment_profile", "") or ""),
        "retention_days": manifest.get("retention_days"),
    }