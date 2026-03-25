from __future__ import annotations

import argparse
from typing import Any, Callable
import time as time_module

from smartcrypto.common.health import health_report
from smartcrypto.infra.binance_adapter import ExchangeAdapter
from smartcrypto.state.store import StateStore


def build_cli_parser(default_config_path: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="USDT/BRL live-hardened bot")
    parser.add_argument("--config", default=default_config_path)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--backtest", action="store_true")
    parser.add_argument("--monte-carlo", action="store_true")
    parser.add_argument("--optimize", action="store_true")
    parser.add_argument("--walk-forward", action="store_true")
    parser.add_argument("--healthcheck", action="store_true")
    return parser


def lifecycle_state(running: bool) -> str:
    return "running" if running else "stopped"


def runtime_mode_name(is_live: bool) -> str:
    return "live" if is_live else "paper"


def should_run_once(*, paused: bool, force: bool = False) -> bool:
    return force or not paused


def has_research_command(args: argparse.Namespace) -> bool:
    return any(
        [
            bool(getattr(args, "backtest", False)),
            bool(getattr(args, "monte_carlo", False)),
            bool(getattr(args, "optimize", False)),
            bool(getattr(args, "walk_forward", False)),
        ]
    )


def should_perform_startup_reconcile(
    cfg: dict[str, Any], *, is_live: bool, args: argparse.Namespace
) -> bool:
    return (
        is_live
        and bool(cfg.get("runtime", {}).get("startup_reconcile", True))
        and not has_research_command(args)
    )


def loop_interval_seconds(cfg: dict[str, Any]) -> int:
    return max(1, int(cfg.get("runtime", {}).get("loop_seconds", 20) or 20))


def resolve_status_price(
    cfg: dict[str, Any],
    exchange: ExchangeAdapter,
    store: StateStore,
    logger: Any,
    *,
    fallback_price_fn: Callable[[dict[str, Any]], float],
) -> float:
    try:
        return exchange.get_last_price()
    except Exception as exc:
        price = fallback_price_fn(cfg)
        store.add_event("WARNING", "status_price_fallback", {"error": str(exc), "price_brl": price})
        logger.warning("status_price_fallback", error=str(exc), price_brl=price)
        return price


def build_healthcheck_payload(cfg: dict[str, Any], store: StateStore) -> dict[str, Any]:
    return health_report(cfg, store, interval=str(cfg.get("market", {}).get("timeframe", "15m")))


def run_once_cycle(
    cfg: dict[str, Any],
    store: StateStore,
    exchange: ExchangeAdapter,
    logger: Any,
    *,
    tick_fn: Callable[[dict[str, Any], StateStore, ExchangeAdapter], dict[str, Any]],
    persist_runtime_state_fn: Callable[[dict[str, Any], ExchangeAdapter, dict[str, Any]], None],
) -> dict[str, Any]:
    result = tick_fn(cfg, store, exchange)
    store.set_flag("consecutive_error_count", 0)
    persist_runtime_state_fn(cfg, exchange, result)
    logger.info("tick_once_ok", price_brl=result.get("price_brl"), equity_brl=result.get("equity_brl"))
    return result


def run_loop(
    cfg: dict[str, Any],
    store: StateStore,
    exchange: ExchangeAdapter,
    logger: Any,
    *,
    tick_fn: Callable[[dict[str, Any], StateStore, ExchangeAdapter], dict[str, Any]],
    persist_runtime_state_fn: Callable[[dict[str, Any], ExchangeAdapter, dict[str, Any]], None],
    circuit_breaker_max_errors_fn: Callable[[dict[str, Any]], int],
    circuit_breaker_cooldown_seconds_fn: Callable[[dict[str, Any]], int],
    set_reentry_block_fn: Callable[[StateStore, int, str], None],
    sleep_fn: Callable[[float], None] = time_module.sleep,
) -> None:
    loop_seconds = loop_interval_seconds(cfg)
    while True:
        try:
            result = tick_fn(cfg, store, exchange)
            store.set_flag("consecutive_error_count", 0)
            persist_runtime_state_fn(cfg, exchange, result)
            logger.info(
                "tick_ok",
                price_brl=result.get("price_brl"),
                equity_brl=result.get("equity_brl"),
                paused=result.get("paused"),
            )
        except KeyboardInterrupt:
            store.add_event("WARN", "bot_interrupted", {})
            logger.warning("bot_interrupted")
            raise
        except Exception as exc:
            current_errors = int(store.get_flag("consecutive_error_count", 0) or 0) + 1
            store.set_flag("consecutive_error_count", current_errors)
            store.add_event(
                "ERROR",
                "bot_tick_error",
                {"error": str(exc), "consecutive_error_count": current_errors},
            )
            logger.error("bot_tick_error", error=str(exc), consecutive_error_count=current_errors)
            if current_errors >= circuit_breaker_max_errors_fn(cfg):
                store.set_flag("paused", True)
                cooldown = circuit_breaker_cooldown_seconds_fn(cfg)
                if cooldown > 0:
                    set_reentry_block_fn(store, cooldown, "circuit_breaker")
                store.add_event(
                    "ERROR",
                    "circuit_breaker_paused_bot",
                    {"consecutive_error_count": current_errors, "cooldown_seconds": cooldown},
                )
                logger.error(
                    "circuit_breaker_paused_bot",
                    consecutive_error_count=current_errors,
                    cooldown_seconds=cooldown,
                )
        sleep_fn(loop_seconds)
