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


def runtime_manifest_cache_file(cfg: dict[str, Any]) -> Path:
    return (
        dashboard_cache_dir(cfg)
        / f"runtime_manifest_{cache_symbol_token(cfg.get('market', {}).get('symbol', 'USDTBRL'))}.json"
    )


def preflight_cache_file(cfg: dict[str, Any]) -> Path:
    return (
        dashboard_cache_dir(cfg)
        / f"preflight_{cache_symbol_token(cfg.get('market', {}).get('symbol', 'USDTBRL'))}.json"
    )


def open_orders_cache_file(cfg: dict[str, Any]) -> Path:
    return (
        dashboard_cache_dir(cfg)
        / f"open_orders_{cache_symbol_token(cfg.get('market', {}).get('symbol', 'USDTBRL'))}.json"
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def write_market_cache(cfg: dict[str, Any], interval: str, df: pd.DataFrame) -> None:
    try:
        out = df.copy()
        if out.empty:
            return

        for col in out.columns:
            try:
                if pd.api.types.is_datetime64_any_dtype(out[col]) or pd.api.types.is_datetime64tz_dtype(out[col]):
                    out[col] = pd.to_datetime(out[col], errors="coerce", utc=True).dt.strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    )
            except Exception:
                pass

        for col in ("ts", "open_time", "close_time"):
            if col in out.columns:
                out[col] = pd.to_datetime(out[col], errors="coerce", utc=True).dt.strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )

        out = out.where(pd.notnull(out), None)

        payload = {
            "saved_at": utc_now(),
            "symbol": str(cfg.get("market", {}).get("symbol", "")),
            "interval": str(interval),
            "rows": out.to_dict(orient="records"),
        }
        _write_json(market_cache_file(cfg, interval), payload)
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
        _write_json(runtime_status_cache_file(cfg), payload)
    except Exception:
        pass


def write_runtime_manifest_cache(cfg: dict[str, Any], manifest: dict[str, Any]) -> None:
    try:
        payload = {
            "saved_at": utc_now(),
            "symbol": str(cfg.get("market", {}).get("symbol", "")),
            "manifest": dict(manifest or {}),
        }
        _write_json(runtime_manifest_cache_file(cfg), payload)
    except Exception:
        pass


def read_runtime_manifest_cache(cfg: dict[str, Any]) -> dict[str, Any]:
    payload = _read_json(runtime_manifest_cache_file(cfg))
    manifest = payload.get("manifest", {}) if isinstance(payload, dict) else {}
    return manifest if isinstance(manifest, dict) else {}


def write_preflight_cache(cfg: dict[str, Any], preflight: dict[str, Any]) -> None:
    try:
        payload = {
            "saved_at": utc_now(),
            "symbol": str(cfg.get("market", {}).get("symbol", "")),
            "preflight": dict(preflight or {}),
        }
        _write_json(preflight_cache_file(cfg), payload)
    except Exception:
        pass


def read_preflight_cache(cfg: dict[str, Any]) -> dict[str, Any]:
    payload = _read_json(preflight_cache_file(cfg))
    preflight = payload.get("preflight", {}) if isinstance(payload, dict) else {}
    return preflight if isinstance(preflight, dict) else {}


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
        _write_json(open_orders_cache_file(cfg), payload)
    except Exception:
        pass


def persist_dashboard_runtime_state(
    cfg: dict[str, Any], exchange: Any, status: dict[str, Any]
) -> None:
    write_runtime_status_cache(cfg, status)
    manifest = cfg.get("__operational_manifest", {})
    if isinstance(manifest, dict) and manifest:
        write_runtime_manifest_cache(cfg, manifest)
    preflight = cfg.get("__preflight", {})
    if isinstance(preflight, dict) and preflight:
        write_preflight_cache(cfg, preflight)
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
