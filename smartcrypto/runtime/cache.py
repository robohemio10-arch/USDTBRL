from __future__ import annotations

import json
import re
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


def normalized_execution_mode(cfg: dict[str, Any]) -> str:
    mode = str(cfg.get("execution", {}).get("mode", "paper") or "paper").strip().lower()
    if mode == "dry_run":
        return "paper"
    return mode if mode in {"paper", "live"} else "paper"


def cache_scope_token(cfg: dict[str, Any]) -> str:
    runtime = dict(cfg.get("runtime", {}) or {})
    config_stem = Path(
        str(cfg.get("__config_path", str(DEFAULT_CONFIG_PATH)) or str(DEFAULT_CONFIG_PATH))
    ).stem.strip().lower()
    if config_stem == "config":
        config_stem = normalized_execution_mode(cfg)
    candidate = (
        runtime.get("experiment_profile")
        or runtime.get("environment")
        or config_stem
        or normalized_execution_mode(cfg)
    )
    token = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(candidate or "").strip().lower()).strip("_")
    return token or normalized_execution_mode(cfg)


def cache_payload_matches_cfg(cfg: dict[str, Any], payload: dict[str, Any]) -> bool:
    if not isinstance(payload, dict) or not payload:
        return False
    expected_mode = normalized_execution_mode(cfg)
    expected_scope = cache_scope_token(cfg)
    payload_mode = str(payload.get("execution_mode", "") or "").strip().lower()
    payload_scope = str(payload.get("cache_scope", "") or "").strip().lower()
    if payload_mode != expected_mode:
        return False
    if payload_scope != expected_scope:
        return False
    return True


def _cache_file_name(prefix: str, cfg: dict[str, Any], *parts: str) -> str:
    tokens = [
        prefix,
        cache_scope_token(cfg),
        cache_symbol_token(cfg.get("market", {}).get("symbol", "USDTBRL")),
        *[str(part) for part in parts if str(part)],
    ]
    return "_".join(tokens) + ".json"


def market_cache_file(cfg: dict[str, Any], interval: str) -> Path:
    return dashboard_cache_dir(cfg) / _cache_file_name("market", cfg, str(interval))


def runtime_status_cache_file(cfg: dict[str, Any]) -> Path:
    return dashboard_cache_dir(cfg) / _cache_file_name("runtime_status", cfg)


def runtime_manifest_cache_file(cfg: dict[str, Any]) -> Path:
    return dashboard_cache_dir(cfg) / _cache_file_name("runtime_manifest", cfg)


def preflight_cache_file(cfg: dict[str, Any]) -> Path:
    return dashboard_cache_dir(cfg) / _cache_file_name("preflight", cfg)


def open_orders_cache_file(cfg: dict[str, Any]) -> Path:
    return dashboard_cache_dir(cfg) / _cache_file_name("open_orders", cfg)


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


def _cache_metadata(cfg: dict[str, Any]) -> dict[str, str]:
    return {
        "symbol": str(cfg.get("market", {}).get("symbol", "")),
        "execution_mode": normalized_execution_mode(cfg),
        "cache_scope": cache_scope_token(cfg),
    }


def write_market_cache(cfg: dict[str, Any], interval: str, df: pd.DataFrame) -> None:
    try:
        out = df.copy()
        if out.empty:
            return

        for col in out.columns:
            try:
                if pd.api.types.is_datetime64_any_dtype(out[col]):
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
            **_cache_metadata(cfg),
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
            **_cache_metadata(cfg),
            "status": status,
        }
        _write_json(runtime_status_cache_file(cfg), payload)
    except Exception:
        pass


def write_runtime_manifest_cache(cfg: dict[str, Any], manifest: dict[str, Any]) -> None:
    try:
        payload = {
            "saved_at": utc_now(),
            **_cache_metadata(cfg),
            "manifest": dict(manifest or {}),
        }
        _write_json(runtime_manifest_cache_file(cfg), payload)
    except Exception:
        pass


def read_runtime_manifest_cache(cfg: dict[str, Any]) -> dict[str, Any]:
    payload = _read_json(runtime_manifest_cache_file(cfg))
    if not cache_payload_matches_cfg(cfg, payload):
        return {}
    manifest = payload.get("manifest", {}) if isinstance(payload, dict) else {}
    return manifest if isinstance(manifest, dict) else {}


def write_preflight_cache(cfg: dict[str, Any], preflight: dict[str, Any]) -> None:
    try:
        payload = {
            "saved_at": utc_now(),
            **_cache_metadata(cfg),
            "preflight": dict(preflight or {}),
        }
        _write_json(preflight_cache_file(cfg), payload)
    except Exception:
        pass


def read_preflight_cache(cfg: dict[str, Any]) -> dict[str, Any]:
    payload = _read_json(preflight_cache_file(cfg))
    if not cache_payload_matches_cfg(cfg, payload):
        return {}
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
            **_cache_metadata(cfg),
            "error": str(error or ""),
            "orders": normalized,
        }
        _write_json(open_orders_cache_file(cfg), payload)
    except Exception:
        pass




def read_runtime_status_payload(cfg: dict[str, Any]) -> dict[str, Any]:
    payload = _read_json(runtime_status_cache_file(cfg))
    if not cache_payload_matches_cfg(cfg, payload):
        return {}
    status = payload.get("status", {})
    return payload if isinstance(status, dict) else {}


def read_runtime_status_cache(cfg: dict[str, Any]) -> dict[str, Any]:
    payload = read_runtime_status_payload(cfg)
    status = payload.get("status", {}) if isinstance(payload, dict) else {}
    return status if isinstance(status, dict) else {}


def read_market_cache_payload(cfg: dict[str, Any], interval: str) -> dict[str, Any]:
    payload = _read_json(market_cache_file(cfg, interval))
    if not cache_payload_matches_cfg(cfg, payload):
        return {}
    if str(payload.get("interval", "") or "") != str(interval):
        return {}
    rows = payload.get("rows", [])
    return payload if isinstance(rows, list) else {}


def read_market_cache_rows(cfg: dict[str, Any], interval: str) -> list[dict[str, Any]]:
    payload = read_market_cache_payload(cfg, interval)
    rows = payload.get("rows", []) if isinstance(payload, dict) else []
    return [dict(row) for row in rows if isinstance(row, dict)]


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
    if normalized_execution_mode(cfg) != "live":
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
