from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from smartcrypto.infra.notifications import NtfyClient
from smartcrypto.state.store import PositionState, StateStore


def parse_utc_offset(value: str) -> timezone:
    raw = str(value or "-03:00").strip()
    sign = -1 if raw.startswith("-") else 1
    raw = raw[1:] if raw[:1] in "+-" else raw
    hours_str, minutes_str = (raw.split(":", 1) + ["00"])[:2]
    hours = int(hours_str or 0)
    minutes = int(minutes_str or 0)
    return timezone(sign * timedelta(hours=hours, minutes=minutes))


def ntfy_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    return dict(cfg.get("notifications", {}).get("ntfy", {}) or {})


def ntfy_client(cfg: dict[str, Any]) -> NtfyClient:
    return NtfyClient(ntfy_cfg(cfg))


def ntfy_mode_allowed(cfg: dict[str, Any]) -> bool:
    settings = ntfy_cfg(cfg)
    mode = str(cfg.get("execution", {}).get("mode", "dry_run") or "dry_run").lower()
    if mode == "live":
        return bool(settings.get("notify_live", True))
    return bool(settings.get("notify_paper", False))


def publish_ntfy(
    cfg: dict[str, Any], *, title: str, message: str, priority: str = "default", tags: str = ""
) -> None:
    client = ntfy_client(cfg)
    if not client.is_ready() or not ntfy_mode_allowed(cfg):
        return
    client.publish(title=title, message=message, priority=priority, tags=tags)


def send_sell_notification(
    *,
    store: StateStore,
    cfg: dict[str, Any],
    reason: str,
    exec_price: float,
    exec_qty: float,
    pnl_brl: float,
    pnl_pct: float,
    order_type: str,
) -> None:
    settings = ntfy_cfg(cfg)
    if not bool(settings.get("enabled", False)) or not bool(settings.get("sales_enabled", True)):
        return
    message = (
        f"Par: {cfg['market']['symbol']}\n"
        f"Motivo: {reason}\n"
        f"Preço: R$ {exec_price:.4f}\n"
        f"Quantidade: {exec_qty:.6f} USDT\n"
        f"PnL: R$ {pnl_brl:.2f} ({pnl_pct:.2f}%)\n"
        f"Tipo: {order_type}\n"
        f"Modo: {cfg['execution']['mode']}"
    )
    try:
        publish_ntfy(
            cfg,
            title=f"Venda {cfg['market']['symbol']}",
            message=message,
            priority="high",
            tags="moneybag,rotating_light",
        )
    except Exception as exc:
        store.add_event("ERROR", "ntfy_sell_failed", {"error": str(exc), "reason": reason})


def _cash_available(initial_cash: float, position: PositionState) -> float:
    return initial_cash + position.realized_pnl_brl - position.brl_spent


def send_daily_report_if_due(
    *, store: StateStore, cfg: dict[str, Any], position: PositionState, last_price: float
) -> None:
    settings = ntfy_cfg(cfg)
    if not bool(settings.get("enabled", False)) or not bool(
        settings.get("daily_report_enabled", True)
    ):
        return
    local_tz = parse_utc_offset(str(settings.get("utc_offset", "-03:00")))
    now_local = datetime.now(local_tz)
    scheduled_hour = int(settings.get("daily_report_hour", 20) or 20)
    scheduled_minute = int(settings.get("daily_report_minute", 0) or 0)
    if (now_local.hour, now_local.minute) < (scheduled_hour, scheduled_minute):
        return
    today_key = now_local.strftime("%Y-%m-%d")
    if str(store.get_flag("ntfy_daily_report_sent_date", "")) == today_key:
        return

    cycles = store.read_df("cycles", 4000)
    trades = store.read_df("trades", 4000)
    snapshots = store.read_df("snapshots", 3000)

    if not cycles.empty and "closed_at" in cycles.columns:
        cycles = cycles.copy()
        cycles["closed_at"] = pd.to_datetime(cycles["closed_at"], errors="coerce", utc=True)
        start_local = pd.Timestamp(now_local.date(), tz=local_tz)
        start_utc = start_local.tz_convert("UTC")
        day_cycles = cycles[cycles["closed_at"] >= start_utc]
    else:
        day_cycles = pd.DataFrame()

    if not trades.empty and "created_at" in trades.columns:
        trades = trades.copy()
        trades["created_at"] = pd.to_datetime(trades["created_at"], errors="coerce", utc=True)
        start_local = pd.Timestamp(now_local.date(), tz=local_tz)
        start_utc = start_local.tz_convert("UTC")
        day_trades = trades[trades["created_at"] >= start_utc]
    else:
        day_trades = pd.DataFrame()

    equity_brl = 0.0
    if not snapshots.empty and "equity_brl" in snapshots.columns:
        equity_brl = float(
            pd.to_numeric(snapshots["equity_brl"], errors="coerce").fillna(0.0).iloc[0]
        )
    if equity_brl <= 0:
        equity_brl = _cash_available(float(cfg["portfolio"]["initial_cash_brl"]), position) + float(
            position.qty_usdt
        ) * float(last_price)

    realized_today = (
        float(day_cycles["pnl_brl"].fillna(0.0).sum())
        if (not day_cycles.empty and "pnl_brl" in day_cycles.columns)
        else 0.0
    )
    sells_today = (
        int((day_trades["side"].astype(str).str.lower() == "sell").sum())
        if (not day_trades.empty and "side" in day_trades.columns)
        else 0
    )
    closed_cycles = (
        int((day_cycles["status"].astype(str).str.lower() == "closed").sum())
        if (not day_cycles.empty and "status" in day_cycles.columns)
        else len(day_cycles)
    )
    unrealized = float(position.qty_usdt) * float(last_price) - float(position.brl_spent)

    message = (
        f"Relatório diário {cfg['market']['symbol']}\n"
        f"Data local: {today_key}\n"
        f"Equity: R$ {equity_brl:.2f}\n"
        f"Realizado no dia: R$ {realized_today:.2f}\n"
        f"Não realizado atual: R$ {unrealized:.2f}\n"
        f"Vendas no dia: {sells_today}\n"
        f"Ciclos fechados no dia: {closed_cycles}\n"
        f"Posição aberta: {position.status}\n"
        f"Último preço: R$ {last_price:.4f}"
    )
    try:
        publish_ntfy(
            cfg,
            title=f"Relatório diário {cfg['market']['symbol']}",
            message=message,
            priority="default",
            tags="spiral_calendar_pad,bar_chart",
        )
        store.set_flag("ntfy_daily_report_sent_date", today_key)
    except Exception as exc:
        store.add_event("ERROR", "ntfy_daily_report_failed", {"error": str(exc)})
