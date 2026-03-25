from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from smartcrypto.common.constants import DEFAULT_CONFIG_PATH
from smartcrypto.common.utils import project_root_from_config_path
from smartcrypto.state.store import utc_now


def project_root_from_cfg(cfg: dict[str, Any]) -> Path:
    cfg_path = str(cfg.get("__config_path", str(DEFAULT_CONFIG_PATH)) or str(DEFAULT_CONFIG_PATH))
    return project_root_from_config_path(cfg_path)


def dashboard_cache_dir(cfg: dict[str, Any]) -> Path:
    raw = str(
        cfg.get("dashboard", {}).get("cache_dir", "data/dashboard_cache") or "data/dashboard_cache"
    )
    path = Path(raw)
    if not path.is_absolute():
        path = project_root_from_cfg(cfg) / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_symbol_token(symbol: str) -> str:
    token = "".join(ch for ch in str(symbol or "") if ch.isalnum()).upper()
    return token or "SYMBOL"


def market_cache_file(cfg: dict[str, Any], interval: str) -> Path:
    return (
        dashboard_cache_dir(cfg)
        / f"market_{cache_symbol_token(cfg.get('market', {}).get('symbol', 'USDTBRL'))}_{str(interval)}.json"
    )


def runtime_status_cache_file(cfg: dict[str, Any]) -> Path:
    return (
        dashboard_cache_dir(cfg)
        / f"runtime_status_{cache_symbol_token(cfg.get('market', {}).get('symbol', 'USDTBRL'))}.json"
    )


def open_orders_cache_file(cfg: dict[str, Any]) -> Path:
    return (
        dashboard_cache_dir(cfg)
        / f"open_orders_{cache_symbol_token(cfg.get('market', {}).get('symbol', 'USDTBRL'))}.json"
    )


def write_market_cache(cfg: dict[str, Any], interval: str, df: pd.DataFrame) -> None:
    try:
        out = df.copy()
        if out.empty:
            return
        if "ts" in out.columns:
            out["ts"] = pd.to_datetime(out["ts"], errors="coerce", utc=True).dt.strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        payload = {
            "saved_at": utc_now(),
            "symbol": str(cfg.get("market", {}).get("symbol", "")),
            "interval": str(interval),
            "rows": out.to_dict(orient="records"),
        }
        market_cache_file(cfg, interval).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


def write_runtime_status_cache(cfg: dict[str, Any], status: dict[str, Any]) -> None:
    try:
        payload = {
            "saved_at": utc_now(),
            "symbol": str(cfg.get("market", {}).get("symbol", "")),
            "execution_mode": str(cfg.get("execution", {}).get("mode", "dry_run")),
            "status": status,
        }
        runtime_status_cache_file(cfg).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


def write_open_orders_cache(
    cfg: dict[str, Any], orders: list[dict[str, Any]], error: str = ""
) -> None:
    try:
        normalized: list[dict[str, Any]] = []
        for row in orders or []:
            item = dict(row)
            updated_at = item.get("updated_at")
            if updated_at is not None:
                try:
                    item["updated_at"] = pd.to_datetime(
                        updated_at, errors="coerce", utc=True
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")
                except Exception:
                    item["updated_at"] = str(updated_at)
            normalized.append(item)
        payload = {
            "saved_at": utc_now(),
            "symbol": str(cfg.get("market", {}).get("symbol", "")),
            "execution_mode": str(cfg.get("execution", {}).get("mode", "dry_run")),
            "error": str(error or ""),
            "orders": normalized,
        }
        open_orders_cache_file(cfg).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


def persist_dashboard_runtime_state(
    cfg: dict[str, Any], exchange: Any, status: dict[str, Any]
) -> None:
    write_runtime_status_cache(cfg, status)
    if str(cfg.get("execution", {}).get("mode", "dry_run")).lower() != "live":
        write_open_orders_cache(cfg, [])
        return
    if not hasattr(exchange, "get_open_orders"):
        write_open_orders_cache(cfg, [], error="ExchangeAdapter não expõe get_open_orders().")
        return
    try:
        orders = exchange.get_open_orders()
        write_open_orders_cache(cfg, orders)
    except Exception as exc:
        write_open_orders_cache(cfg, [], error=str(exc))
