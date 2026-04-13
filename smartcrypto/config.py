from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from smartcrypto.common.constants import DEFAULT_CONFIG_CANDIDATES, DEFAULT_CONFIG_PATH
from smartcrypto.common.env import load_dotenv_map, save_dotenv_map
from smartcrypto.common.utils import project_root_from_config_path

DEFAULT_CONFIG: dict[str, Any] = {
    "exchange": {
        "id": "binance",
        "base_url": "https://api.binance.com",
        "api_key_env": "BINANCE_API_KEY",
        "api_secret_env": "BINANCE_API_SECRET",
        "timeout_seconds": 20,
        "recv_window": 5000,
        "request_retries": 3,
        "request_backoff_seconds": 1.0,
    },
    "storage": {"db_path": "data/usdtbrl_paper.sqlite"},
    "runtime": {
        "loop_seconds": 5,
        "deactivate_after_sell": False,
        "startup_reconcile": True,
        "startup_reconcile_fail_closed": True,
        "reconcile_on_tick": True,
        "inflight_order_lock_seconds": 120,
        "circuit_breaker_max_errors": 5,
        "circuit_breaker_cooldown_seconds": 300,
        "reconcile_pause_on_mismatch": True,
        "reconcile_qty_tolerance_usdt": 0.0001,
        "reconcile_allow_extra_base_asset_balance": False,
    },
    "portfolio": {"initial_cash_brl": 10000.0},
    "market": {
        "symbol": "USDT/BRL",
        "timeframe": "15m",
        "lookback_bars": 240,
        "research_lookback_bars": 800,
    },
    "execution": {
        "mode": "dry_run",
        "entry_order_type": "limit",
        "exit_order_type": "limit",
        "fee_rate": 0.001,
        "limit_orders_enabled": True,
        "buy_price_offset_bps": 3,
        "sell_price_offset_bps": 3,
        "reprice_wait_seconds": 10,
        "reprice_attempts": 6,
        "entry_fallback_market": True,
        "exit_fallback_market": False,
        "force_sell_market": True,
        "limit_time_in_force": "GTC",
    },
    "risk": {"max_open_brl": 2500.0, "max_daily_loss_brl": 400.0},
    "strategy": {
        "enabled": True,
        "first_buy_brl": 25.0,
        "max_cycle_brl": 2500.0,
        "take_profit_pct": 0.65,
        "trailing_enabled": True,
        "trailing_activation_pct": 0.45,
        "trailing_callback_pct": 0.18,
        "return_rebuy_pct": 0.12,
        "stop_loss_enabled": True,
        "stop_loss_pct": 2.4,
        "stop_loss_market": True,
        "min_profit_brl": 0.15,
        "ramps": [
            {"drop_pct": 0.35, "multiplier": 1.0},
            {"drop_pct": 0.7, "multiplier": 1.25},
            {"drop_pct": 1.05, "multiplier": 1.5},
            {"drop_pct": 1.4, "multiplier": 2.0},
            {"drop_pct": 1.8, "multiplier": 2.5},
            {"drop_pct": 2.2, "multiplier": 3.0},
            {"drop_pct": 2.7, "multiplier": 4.0},
            {"drop_pct": 3.3, "multiplier": 5.0},
            {"drop_pct": 4.0, "multiplier": 6.0},
            {"drop_pct": 4.8, "multiplier": 8.0},
            {"drop_pct": 5.7, "multiplier": 10.0},
            {"drop_pct": 6.8, "multiplier": 12.0},
            {"drop_pct": 8.0, "multiplier": 15.0},
            {"drop_pct": 9.4, "multiplier": 18.0},
        ],
    },
    "research": {
        "monte_carlo_runs": 300,
        "block_bootstrap_block_size": 24,
        "walk_forward_folds": 3,
        "walk_forward_train_ratio": 0.65,
    },
    "simulation": {"mock_price_brl": 5.2},
    "notifications": {
        "ntfy": {
            "enabled": True,
            "topic_env": "NTFY_TOPIC",
            "server_env": "NTFY_SERVER",
            "token_env": "NTFY_TOKEN",
            "username_env": "NTFY_USERNAME",
            "password_env": "NTFY_PASSWORD",
            "sales_enabled": True,
            "daily_report_enabled": True,
            "notify_live": True,
            "notify_paper": False,
            "daily_report_hour": 20,
            "daily_report_minute": 0,
            "utc_offset": "-03:00",
            "timeout_seconds": 10,
            "default_tags": ["moneybag", "chart_with_upwards_trend"],
        }
    },
    "dashboard": {"cache_dir": "data/dashboard_cache"},
    "logging": {"dir": "data/logs", "console": True},
    "health": {"stale_runtime_minutes": 20, "stale_market_cache_minutes": 240},
}


def resolve_config_path(path: str | Path | None = None) -> Path:
    candidate = Path(path or DEFAULT_CONFIG_PATH)
    if candidate.exists():
        return candidate
    for fallback in DEFAULT_CONFIG_CANDIDATES:
        fallback_path = Path(fallback)
        if fallback_path.exists():
            return fallback_path
    return candidate

def project_root_from_cfg_path(cfg_path: str | Path) -> Path:
    return project_root_from_config_path(cfg_path)


def project_root_from_cfg(cfg: dict[str, Any]) -> Path:
    return project_root_from_cfg_path(str(cfg.get("__config_path", str(DEFAULT_CONFIG_PATH)) or str(DEFAULT_CONFIG_PATH)))


def _deep_merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def build_legacy_ramps(cfg: dict[str, Any]) -> list[dict[str, float]]:
    strategy = cfg.get("strategy", {}) or {}
    count = int(strategy.get("safety_orders", 0) or 0)
    step = float(strategy.get("safety_step_pct", 0.7) or 0.7)
    scale = float(strategy.get("safety_volume_scale", 1.45) or 1.45)
    ramps: list[dict[str, float]] = []
    current_drop = step / 2 if count > 0 else 0.0
    multiplier = 1.0
    for _ in range(count):
        ramps.append({"drop_pct": round(current_drop, 4), "multiplier": round(multiplier, 6)})
        current_drop += step
        multiplier *= scale
    return ramps


def strip_runtime_only_keys(cfg: dict[str, Any]) -> dict[str, Any]:
    cleaned = deepcopy(cfg)
    cleaned.pop("__config_path", None)
    return cleaned


def normalize_config(
    cfg: dict[str, Any] | None, *, config_path: str | Path = DEFAULT_CONFIG_PATH
) -> dict[str, Any]:
    incoming = deepcopy(cfg or {})
    merged = _deep_merge(DEFAULT_CONFIG, incoming)

    strategy = merged.setdefault("strategy", {})
    ramps = strategy.get("ramps") or []
    if not ramps:
        ramps = build_legacy_ramps(merged)
    normalized_ramps: list[dict[str, float]] = []
    for ramp in ramps:
        if not isinstance(ramp, dict):
            continue
        drop_pct = float(ramp.get("drop_pct", 0) or 0)
        multiplier = float(ramp.get("multiplier", 0) or 0)
        if drop_pct > 0 and multiplier > 0:
            normalized_ramps.append({"drop_pct": drop_pct, "multiplier": multiplier})
    strategy["ramps"] = normalized_ramps or deepcopy(DEFAULT_CONFIG["strategy"]["ramps"])
    strategy.pop("safety_orders", None)
    strategy.pop("safety_step_pct", None)
    strategy.pop("safety_volume_scale", None)

    execution = merged.setdefault("execution", {})
    if "fallback_market" in execution:
        generic_fallback = bool(execution.pop("fallback_market"))
        execution.setdefault("entry_fallback_market", generic_fallback)
        execution.setdefault("exit_fallback_market", False)

    market = merged.setdefault("market", {})
    market["symbol"] = str(market.get("symbol", "USDT/BRL") or "USDT/BRL")
    market["timeframe"] = str(market.get("timeframe", "15m") or "15m")

    merged.setdefault("__config_path", str(config_path))
    return merged


def validate_config(cfg: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    portfolio = cfg.get("portfolio", {}) or {}
    execution = cfg.get("execution", {}) or {}
    strategy = cfg.get("strategy", {}) or {}
    risk = cfg.get("risk", {}) or {}
    market = cfg.get("market", {}) or {}

    if float(portfolio.get("initial_cash_brl", 0) or 0) <= 0:
        errors.append("portfolio.initial_cash_brl precisa ser maior que zero.")
    if float(strategy.get("first_buy_brl", 0) or 0) <= 0:
        errors.append("strategy.first_buy_brl precisa ser maior que zero.")
    if float(risk.get("max_open_brl", 0) or 0) <= 0:
        errors.append("risk.max_open_brl precisa ser maior que zero.")
    if float(strategy.get("max_cycle_brl", 0) or 0) <= 0:
        errors.append("strategy.max_cycle_brl precisa ser maior que zero.")
    if float(strategy.get("max_cycle_brl", 0) or 0) > float(
        portfolio.get("initial_cash_brl", 0) or 0
    ):
        errors.append("strategy.max_cycle_brl não pode ser maior que portfolio.initial_cash_brl.")
    if float(risk.get("max_open_brl", 0) or 0) > float(portfolio.get("initial_cash_brl", 0) or 0):
        errors.append("risk.max_open_brl não pode ser maior que portfolio.initial_cash_brl.")
    if float(strategy.get("trailing_callback_pct", 0) or 0) >= float(
        strategy.get("trailing_activation_pct", 0) or 0
    ):
        errors.append(
            "strategy.trailing_callback_pct precisa ser menor que strategy.trailing_activation_pct."
        )
    if float(strategy.get("stop_loss_pct", 0) or 0) > 8:
        errors.append("strategy.stop_loss_pct acima de 8% foi bloqueado por guard-rail.")
    if int(execution.get("reprice_attempts", 0) or 0) < 1:
        errors.append("execution.reprice_attempts precisa ser pelo menos 1.")
    if int(execution.get("reprice_wait_seconds", 0) or 0) < 1:
        errors.append("execution.reprice_wait_seconds precisa ser pelo menos 1.")
    if int(cfg.get("runtime", {}).get("inflight_order_lock_seconds", 0) or 0) < 10:
        errors.append("runtime.inflight_order_lock_seconds precisa ser pelo menos 10.")
    if int(cfg.get("runtime", {}).get("circuit_breaker_max_errors", 0) or 0) < 1:
        errors.append("runtime.circuit_breaker_max_errors precisa ser pelo menos 1.")
    if int(cfg.get("runtime", {}).get("circuit_breaker_cooldown_seconds", 0) or 0) < 30:
        errors.append("runtime.circuit_breaker_cooldown_seconds precisa ser pelo menos 30.")
    if float(cfg.get("runtime", {}).get("reconcile_qty_tolerance_usdt", 0.0) or 0.0) < 0:
        errors.append("runtime.reconcile_qty_tolerance_usdt não pode ser negativo.")
    if int(cfg.get("exchange", {}).get("request_retries", 0) or 0) < 1:
        errors.append("exchange.request_retries precisa ser pelo menos 1.")
    if float(cfg.get("exchange", {}).get("request_backoff_seconds", 0.0) or 0.0) < 0:
        errors.append("exchange.request_backoff_seconds não pode ser negativo.")
    if str(market.get("symbol", "")).strip() == "":
        errors.append("market.symbol é obrigatório.")
    if not strategy.get("ramps"):
        errors.append("strategy.ramps precisa ter ao menos uma rampa válida.")
    if int(cfg.get("health", {}).get("stale_runtime_minutes", 0) or 0) < 1:
        errors.append("health.stale_runtime_minutes precisa ser pelo menos 1.")
    if int(cfg.get("health", {}).get("stale_market_cache_minutes", 0) or 0) < 1:
        errors.append("health.stale_market_cache_minutes precisa ser pelo menos 1.")

    return errors


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    cfg_path = resolve_config_path(path)
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    cfg = normalize_config(raw, config_path=cfg_path)
    errors = validate_config(cfg)
    if errors:
        joined = "\n".join(f"- {message}" for message in errors)
        raise ValueError(f"Configuração inválida:\n{joined}")
    return cfg


def save_config(path: str | Path, payload: dict[str, Any]) -> None:
    cfg_path = resolve_config_path(path)
    normalized = normalize_config(payload, config_path=cfg_path)
    errors = validate_config(normalized)
    if errors:
        joined = "\n".join(f"- {message}" for message in errors)
        raise ValueError(f"Configuração inválida:\n{joined}")
    cfg_path.write_text(
        yaml.safe_dump(strip_runtime_only_keys(normalized), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def sync_env_template(project_root: str | Path) -> Path:
    root = Path(project_root)
    env_path = root / ".env"
    current = load_dotenv_map(env_path) if env_path.exists() else {}
    defaults = {
        "BINANCE_API_KEY": current.get("BINANCE_API_KEY", ""),
        "BINANCE_API_SECRET": current.get("BINANCE_API_SECRET", ""),
        "NTFY_SERVER": current.get("NTFY_SERVER", "https://ntfy.sh"),
        "NTFY_TOPIC": current.get("NTFY_TOPIC", ""),
        "NTFY_TOKEN": current.get("NTFY_TOKEN", ""),
        "NTFY_USERNAME": current.get("NTFY_USERNAME", ""),
        "NTFY_PASSWORD": current.get("NTFY_PASSWORD", ""),
    }
    save_dotenv_map(env_path, defaults)
    return env_path
