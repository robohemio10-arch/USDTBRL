from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Callable

from smartcrypto.common.constants import DEFAULT_CONFIG_PATH, LEGACY_CONFIG_PATH
from smartcrypto.common.utils import project_root_from_config_path
from smartcrypto.runtime.cache import read_preflight_cache, write_preflight_cache
from smartcrypto.runtime.paper_profile import validate_paper_profile

VALID_MODES = {"paper", "dry_run", "live"}
VALID_TIMEFRAMES = {"1m", "5m", "15m", "1h", "12h", "1d", "4h", "30m"}


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on", "confirm", "confirmed", "i_understand"}


def _check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": str(detail)}


def _normalized_symbol(symbol: str) -> str:
    return str(symbol or "").replace("/", "").replace("-", "").replace("_", "").upper()


def _default_adapter_probe(cfg: dict[str, Any]) -> dict[str, Any]:
    try:
        from smartcrypto.infra.binance_adapter import ExchangeAdapter

        adapter = ExchangeAdapter(cfg)
        normalized = str(
            getattr(adapter, "symbol", "") or _normalized_symbol(cfg.get("market", {}).get("symbol", ""))
        )
        return {
            "accessible": True,
            "normalized_symbol": normalized,
            "has_fetch_ohlcv": bool(hasattr(adapter, "fetch_ohlcv")),
            "has_get_last_price": bool(hasattr(adapter, "get_last_price")),
        }
    except Exception as exc:
        return {
            "accessible": False,
            "normalized_symbol": _normalized_symbol(cfg.get("market", {}).get("symbol", "")),
            "has_fetch_ohlcv": False,
            "has_get_last_price": False,
            "error": str(exc),
            "probe_mode": "fail_closed",
        }


def _expected_db_role(cfg: dict[str, Any]) -> str:
    mode = str(cfg.get("execution", {}).get("mode", "") or "").strip().lower()
    return "live" if mode == "live" else "paper"


def _expected_profile_id(cfg: dict[str, Any], resolved: Path) -> str:
    runtime = dict(cfg.get("runtime", {}) or {})
    return str(runtime.get("experiment_profile") or runtime.get("environment") or resolved.stem or "")


def _read_db_identity(db_path: Path) -> dict[str, str]:
    if not db_path.exists():
        return {}
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        table = conn.execute(
            "select 1 from sqlite_master where type='table' and name='bot_state'"
        ).fetchone()
        if table is None:
            return {}
        rows = conn.execute(
            "select key, value from bot_state where key in ('db_role', 'db_profile_id', 'db_symbol')"
        ).fetchall()
    finally:
        conn.close()
    identity: dict[str, str] = {}
    for row in rows:
        try:
            identity[str(row["key"])] = str(json.loads(row["value"]) or "")
        except Exception:
            identity[str(row["key"])] = str(row["value"] or "")
    return identity


def live_confirmation_enabled(cfg: dict[str, Any]) -> bool:
    runtime = dict(cfg.get("runtime", {}) or {})
    execution = dict(cfg.get("execution", {}) or {})
    safety = dict(cfg.get("safety", {}) or {})
    return any(
        [
            _bool(execution.get("confirm_live")),
            _bool(execution.get("allow_live")),
            _bool(runtime.get("allow_live")),
            _bool(runtime.get("live_confirmed")),
            _bool(runtime.get("live_confirmation")),
            _bool(safety.get("allow_live")),
            _bool(cfg.get("__live_confirmation")),
        ]
    )


def perform_preflight(
    cfg: dict[str, Any],
    *,
    resolved_config_path: str | Path,
    config_is_canonical: bool,
    ambiguity_detected: bool = False,
    adapter_probe: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved = Path(resolved_config_path).resolve()
    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    checks.append(_check("config_resolved", resolved.exists(), str(resolved)))
    if not resolved.exists():
        errors.append(f"Arquivo de configuração não encontrado: {resolved}")

    checks.append(_check("config_canonical", config_is_canonical, str(DEFAULT_CONFIG_PATH)))
    if not config_is_canonical:
        errors.append("Configuração operacional não está usando o caminho canônico.")

    checks.append(_check("no_ambiguity", not ambiguity_detected, "config/config.yml vs config.yml"))
    if ambiguity_detected:
        errors.append("Ambiguidade operacional detectada entre config canônica e config raiz.")

    run_id = str(cfg.get("__run_id", "") or cfg.get("runtime", {}).get("run_id", "") or "").strip()
    boot_timestamp = str(
        cfg.get("__boot_timestamp", "") or cfg.get("runtime", {}).get("boot_timestamp", "") or ""
    ).strip()
    environment = str(
        cfg.get("runtime", {}).get("environment", "") or cfg.get("execution", {}).get("environment", "") or ""
    ).strip()

    checks.append(_check("run_id_present", bool(run_id), run_id or "ausente"))
    if not run_id:
        warnings.append("run_id de sessão ausente.")

    checks.append(_check("boot_timestamp_present", bool(boot_timestamp), boot_timestamp or "ausente"))
    if not boot_timestamp:
        warnings.append("boot timestamp da sessão ausente.")

    mode = str(cfg.get("execution", {}).get("mode", "") or "").strip().lower()
    checks.append(_check("mode_present", bool(mode), mode or "ausente"))
    if not mode:
        errors.append("execution.mode ausente.")
    checks.append(_check("mode_valid", mode in VALID_MODES, mode or "ausente"))
    if mode and mode not in VALID_MODES:
        errors.append(f"execution.mode inválido: {mode}")

    db_path_raw = str(cfg.get("storage", {}).get("db_path", "") or "")
    checks.append(_check("db_path_present", bool(db_path_raw), db_path_raw or "ausente"))
    if not db_path_raw:
        errors.append("storage.db_path ausente.")
        db_path = Path()
    else:
        db_path = Path(db_path_raw)
        if not db_path.is_absolute():
            db_path = project_root_from_config_path(resolved) / db_path
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(db_path))
            conn.execute("pragma journal_mode=WAL")
            conn.execute("select 1")
            conn.close()
            checks.append(_check("db_path_accessible", True, str(db_path)))
        except Exception as exc:
            checks.append(_check("db_path_accessible", False, str(db_path)))
            errors.append(f"storage.db_path inacessível: {exc}")

    symbol = str(cfg.get("market", {}).get("symbol", "") or "").strip()
    timeframe = str(cfg.get("market", {}).get("timeframe", "") or "").strip()
    normalized_symbol = _normalized_symbol(symbol)
    checks.append(_check("symbol_present", bool(symbol), symbol or "ausente"))
    checks.append(_check("timeframe_present", bool(timeframe), timeframe or "ausente"))
    if not symbol:
        errors.append("market.symbol ausente.")
    if not timeframe:
        errors.append("market.timeframe ausente.")
    checks.append(_check("symbol_valid", bool(normalized_symbol) and normalized_symbol.isalnum(), normalized_symbol or "ausente"))
    if symbol and (not normalized_symbol or not normalized_symbol.isalnum()):
        errors.append(f"market.symbol inválido: {symbol}")
    checks.append(_check("timeframe_valid", timeframe in VALID_TIMEFRAMES, timeframe or "ausente"))
    if timeframe and timeframe not in VALID_TIMEFRAMES:
        errors.append(f"market.timeframe inválido: {timeframe}")

    checks.append(_check("environment_present", bool(environment), environment or "ausente"))
    if not environment:
        warnings.append("runtime.environment ausente.")

    if mode == "live":
        live_ok = live_confirmation_enabled(cfg)
        checks.append(_check("live_confirmation", live_ok, "required for live"))
        if not live_ok:
            errors.append("Modo live bloqueado sem confirmação explícita.")
    else:
        checks.append(_check("live_confirmation", True, "not required"))

    runtime = dict(cfg.get("runtime", {}) or {})
    single_instance_enabled = bool(runtime.get("single_instance_enabled", False))
    lock_path = str(runtime.get("instance_lock_path", "") or "").strip()
    checks.append(_check("single_instance_lock_configured", (not single_instance_enabled) or bool(lock_path), lock_path or "ausente"))
    if single_instance_enabled and not lock_path:
        errors.append("runtime.instance_lock_path ausente com single_instance_enabled=true.")

    probe = adapter_probe or _default_adapter_probe
    adapter_details = dict(probe(cfg) or {})
    adapter_accessible = bool(adapter_details.get("accessible", True))
    checks.append(_check("exchange_adapter_accessible", adapter_accessible, str(adapter_details)))
    if not adapter_accessible:
        errors.append("Adapter/exchange inacessível durante preflight.")
    else:
        adapter_symbol = str(adapter_details.get("normalized_symbol", normalized_symbol) or "")
        checks.append(_check("symbol_matches_adapter", not adapter_symbol or adapter_symbol == normalized_symbol, adapter_symbol or "ausente"))
        if adapter_symbol and adapter_symbol != normalized_symbol:
            warnings.append("market.symbol não coincide com o símbolo normalizado pelo adapter.")
        if not bool(adapter_details.get("has_fetch_ohlcv", False)):
            warnings.append("Adapter sem suporte mínimo a fetch_ohlcv().")
        if not bool(adapter_details.get("has_get_last_price", False)):
            warnings.append("Adapter sem suporte explícito a get_last_price().")

    if db_path_raw:
        expected_db_role = _expected_db_role(cfg)
        expected_profile_id = _expected_profile_id(cfg, resolved)
        db_identity = _read_db_identity(db_path)
        role_ok = not db_identity.get("db_role") or db_identity.get("db_role") == expected_db_role
        profile_ok = not db_identity.get("db_profile_id") or db_identity.get("db_profile_id") == expected_profile_id
        symbol_ok = not db_identity.get("db_symbol") or db_identity.get("db_symbol") == normalized_symbol
        checks.append(_check("db_role_matches", role_ok, db_identity.get("db_role", "uninitialized")))
        checks.append(_check("db_profile_matches", profile_ok, db_identity.get("db_profile_id", "uninitialized")))
        checks.append(_check("db_symbol_matches", symbol_ok, db_identity.get("db_symbol", "uninitialized")))
        if not role_ok:
            errors.append(
                f"Banco com papel divergente: db_role={db_identity.get('db_role')} esperado={expected_db_role}."
            )
        if not profile_ok:
            errors.append(
                f"Banco com perfil divergente: db_profile_id={db_identity.get('db_profile_id')} esperado={expected_profile_id}."
            )
        if not symbol_ok:
            errors.append(
                f"Banco com símbolo divergente: db_symbol={db_identity.get('db_symbol')} esperado={normalized_symbol}."
            )
    else:
        db_identity = {}

    profile_validation = validate_paper_profile(
        cfg,
        config_path=resolved,
        feature_flags=dict(cfg.get("__feature_flags", {}) or {}),
    )
    if profile_validation.get("recognized"):
        checks.append(_check("official_profile_valid", not profile_validation.get("errors"), str(profile_validation.get("profile_id", ""))))
        errors.extend(str(item) for item in profile_validation.get("errors", []))
        warnings.extend(str(item) for item in profile_validation.get("warnings", []))

    preflight = {
        "status": "ok" if not errors else "failed",
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "resolved_config_path": str(resolved),
        "mode": mode,
        "symbol": symbol,
        "normalized_symbol": normalized_symbol,
        "timeframe": timeframe,
        "db_path": str(db_path) if db_path_raw else "",
        "db_identity": db_identity,
        "run_id": run_id,
        "boot_timestamp": boot_timestamp,
        "environment": environment,
        "feature_flags_present": bool(cfg.get("__feature_flags", {})),
        "adapter_accessible": adapter_accessible,
        "adapter_details": adapter_details,
        "profile": profile_validation,
    }
    cfg["__preflight"] = dict(preflight)
    write_preflight_cache(cfg, preflight)
    return preflight


def assert_preflight_ok(preflight: dict[str, Any]) -> None:
    if str(preflight.get("status", "failed")) == "ok":
        return
    errors = preflight.get("errors", []) if isinstance(preflight, dict) else []
    joined = "; ".join(str(item) for item in errors) or "preflight_failed"
    raise ValueError(f"Preflight operacional falhou: {joined}")


def load_preflight(cfg: dict[str, Any]) -> dict[str, Any]:
    cached = cfg.get("__preflight", {})
    if isinstance(cached, dict) and cached:
        return dict(cached)
    return read_preflight_cache(cfg)
