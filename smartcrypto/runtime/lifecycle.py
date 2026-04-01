from __future__ import annotations

import argparse
import time as time_module
from dataclasses import dataclass, field
from typing import Any, Callable

from smartcrypto.common.health import health_report
from smartcrypto.infra.binance_adapter import ExchangeAdapter
from smartcrypto.runtime.instance_lock import InstanceLockError, runtime_instance_lock
from smartcrypto.runtime.single_instance import DuplicateInstanceBlockedError, runtime_single_instance
from smartcrypto.runtime.status import display_paper_panel_table
from smartcrypto.state.store import StateStore, utc_now


@dataclass
class CycleResult:
    cycle_id: str
    event: str
    status: str
    started_at: str
    finished_at: str
    price_brl: float | None = None
    equity_brl: float | None = None
    exit_reason: str = ""
    ai_decision: dict[str, Any] | None = None
    baseline_decision: dict[str, Any] | None = None
    ai_context: dict[str, Any] | None = None
    details: dict[str, Any] = field(default_factory=dict)


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
    cfg: dict[str, Any],
    *,
    is_live: bool,
    args: argparse.Namespace,
) -> bool:
    if not is_live:
        return False
    if has_research_command(args):
        return False
    return bool(cfg.get("runtime", {}).get("startup_reconcile", True))


def loop_interval_seconds(cfg: dict[str, Any]) -> int:
    value = cfg.get("runtime", {}).get("loop_seconds", 20)
    try:
        seconds = int(value or 20)
    except Exception:
        seconds = 20
    return seconds if seconds > 0 else 20


def resolve_status_price(
    cfg: dict[str, Any],
    exchange: ExchangeAdapter,
    store: StateStore,
    logger: Any,
    *,
    fallback_price_fn: Callable[[dict[str, Any]], float],
) -> float:
    try:
        return float(exchange.get_last_price())
    except Exception as exc:
        price = fallback_price_fn(cfg)
        if hasattr(store, "add_event"):
            store.add_event("WARNING", "status_price_fallback", {"error": str(exc), "price_brl": price})
        if logger is not None and hasattr(logger, "warning"):
            logger.warning("status_price_fallback", error=str(exc), price_brl=price)
        return price


def build_healthcheck_payload(cfg: dict[str, Any], store: StateStore) -> dict[str, Any]:
    return health_report(cfg, store, interval=str(cfg.get("market", {}).get("timeframe", "15m")))


def _safe_store_flag(store: Any, key: str, value: Any) -> None:
    if hasattr(store, "set_flag"):
        store.set_flag(key, value)


def _safe_database(store: Any) -> Any | None:
    if hasattr(store, "database"):
        return store.database
    return None


def _baseline_decision(store: Any) -> dict[str, Any]:
    if hasattr(store, "get_flag"):
        decision = store.get_flag("ai_runtime_baseline_decision", {})
        if isinstance(decision, dict):
            return dict(decision)
    return {}


def _cycle_id(cfg: dict[str, Any], prefix: str) -> str:
    run_id = str(cfg.get("__run_id", "") or cfg.get("__operational_manifest", {}).get("run_id", "") or "run")
    return f"{prefix}-{run_id}-{int(time_module.time() * 1000)}"


def _record_bot_event(store: Any, level: str, event: str, details: dict[str, Any] | None = None) -> None:
    if store is None:
        return
    if hasattr(store, "add_event"):
        store.add_event(level, event, details or {})
        return
    if hasattr(store, "bot_events") and hasattr(store.bot_events, "add"):
        store.bot_events.add(level, event, details or {})


def _post_tick_observability(
    cfg: dict[str, Any],
    store: Any,
    result: dict[str, Any],
    *,
    cycle_id: str,
    started_at: str,
    finished_at: str,
) -> None:
    database = _safe_database(store)
    if database is None:
        return
    from smartcrypto.runtime.ai_observability import record_ai_observation
    from smartcrypto.runtime.audit import record_cycle_audit

    ai_decision = store.get_flag("ai_runtime_decision", {}) if hasattr(store, "get_flag") else {}
    baseline_decision = _baseline_decision(store)
    record_ai_observation(
        cfg,
        database,
        cycle_id=cycle_id,
        ai_decision=ai_decision if isinstance(ai_decision, dict) else {},
        baseline_decision=baseline_decision if baseline_decision else None,
        context={
            "price_brl": result.get("price_brl"),
            "equity_brl": result.get("equity_brl"),
            "paused": result.get("paused"),
        },
        ts=finished_at,
    )
    record_cycle_audit(
        cfg,
        database,
        cycle_id=cycle_id,
        started_at=started_at,
        finished_at=finished_at,
        status="ok",
        event="tick_completed",
        exit_reason=str(result.get("exit_reason", "") or ""),
        price_brl=result.get("price_brl"),
        equity_brl=result.get("equity_brl"),
        details={"paused": result.get("paused"), "time": result.get("time")},
    )


def _post_tick_observability_cycle_result(
    cfg: dict[str, Any],
    *,
    database: Any,
    store: Any | None,
    result: CycleResult,
) -> None:
    from smartcrypto.runtime.ai_observability import record_ai_observation
    from smartcrypto.runtime.audit import record_cycle_audit

    record_cycle_audit(
        cfg,
        database,
        cycle_id=result.cycle_id,
        started_at=result.started_at,
        finished_at=result.finished_at,
        status=result.status,
        event=result.event,
        exit_reason=result.exit_reason,
        price_brl=result.price_brl,
        equity_brl=result.equity_brl,
        details=result.details,
    )

    if result.ai_decision is not None or result.baseline_decision is not None:
        record_ai_observation(
            cfg,
            database,
            cycle_id=result.cycle_id,
            ai_decision=result.ai_decision,
            baseline_decision=result.baseline_decision,
            context=result.ai_context,
            ts=result.finished_at,
        )

    if store is not None:
        current_count = int(getattr(store, "get_flag", lambda *_a, **_k: 0)("runtime_cycle_count", 0) or 0)
        _safe_store_flag(store, "runtime_cycle_count", current_count + 1)
        _safe_store_flag(store, "runtime_last_cycle_id", result.cycle_id)
        _safe_store_flag(store, "runtime_last_cycle_finished_at", result.finished_at)
        if str(result.status).lower() == "error":
            current_errors = int(getattr(store, "get_flag", lambda *_a, **_k: 0)("runtime_error_cycle_count", 0) or 0)
            _safe_store_flag(store, "runtime_error_cycle_count", current_errors + 1)


def run_once_cycle(
    cfg: dict[str, Any],
    store: StateStore,
    exchange: ExchangeAdapter,
    logger: Any,
    *,
    tick_fn: Callable[[dict[str, Any], StateStore, ExchangeAdapter], dict[str, Any]],
    persist_runtime_state_fn: Callable[[dict[str, Any], ExchangeAdapter, dict[str, Any]], None],
) -> dict[str, Any]:
    from smartcrypto.runtime.audit import record_runtime_event

    with runtime_instance_lock(cfg):
        database = _safe_database(store)
        if database is not None:
            record_runtime_event(cfg, database, event="instance_lock_acquired", level="INFO", details={"mode": "once"})
        cycle_id = _cycle_id(cfg, "once")
        started_at = utc_now()
        try:
            result = tick_fn(cfg, store, exchange)
            _safe_store_flag(store, "consecutive_error_count", 0)
            persist_runtime_state_fn(cfg, exchange, result)
            finished_at = utc_now()
            _post_tick_observability(cfg, store, result, cycle_id=cycle_id, started_at=started_at, finished_at=finished_at)
            panel = result.get("paper_panel", {}) if isinstance(result, dict) else {}
            if panel:
                display_paper_panel_table(panel)
            elif logger is not None and hasattr(logger, "info"):
                logger.info("tick_once_ok", price_brl=result.get("price_brl"), equity_brl=result.get("equity_brl"))
            return result
        finally:
            if database is not None:
                record_runtime_event(cfg, database, event="instance_lock_released", level="INFO", details={"mode": "once"})


def _run_loop_legacy(
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
    from smartcrypto.runtime.audit import record_cycle_audit, record_runtime_event

    loop_seconds = loop_interval_seconds(cfg)
    database = _safe_database(store)
    try:
        with runtime_instance_lock(cfg):
            if database is not None:
                record_runtime_event(
                    cfg,
                    database,
                    event="instance_lock_acquired",
                    level="INFO",
                    details={"mode": "loop"},
                )
                record_runtime_event(cfg, database, event="loop_started", level="INFO", details={"loop_seconds": loop_seconds})
            while True:
                cycle_id = _cycle_id(cfg, "loop")
                started_at = utc_now()
                try:
                    result = tick_fn(cfg, store, exchange)
                    _safe_store_flag(store, "consecutive_error_count", 0)
                    persist_runtime_state_fn(cfg, exchange, result)
                    finished_at = utc_now()
                    _post_tick_observability(cfg, store, result, cycle_id=cycle_id, started_at=started_at, finished_at=finished_at)
                    panel = result.get("paper_panel", {}) if isinstance(result, dict) else {}
                    if panel:
                        display_paper_panel_table(panel)
                    elif logger is not None and hasattr(logger, "info"):
                        logger.info(
                            "tick_ok",
                            price_brl=result.get("price_brl"),
                            equity_brl=result.get("equity_brl"),
                            paused=result.get("paused"),
                        )
                except KeyboardInterrupt:
                    if database is not None:
                        record_runtime_event(cfg, database, event="unexpected_shutdown", level="ERROR", details={"reason": "keyboard_interrupt"})
                    _record_bot_event(store, "WARN", "bot_interrupted", {})
                    if logger is not None and hasattr(logger, "warning"):
                        logger.warning("bot_interrupted")
                    raise
                except Exception as exc:
                    current_errors = int(getattr(store, "get_flag", lambda *_a, **_k: 0)("consecutive_error_count", 0) or 0) + 1
                    _safe_store_flag(store, "consecutive_error_count", current_errors)
                    _record_bot_event(
                        store,
                        "ERROR",
                        "bot_tick_error",
                        {"error": str(exc), "consecutive_errors": current_errors},
                    )
                    if logger is not None and hasattr(logger, "error"):
                        logger.error("bot_tick_error", error=str(exc), consecutive_errors=current_errors)
                    if database is not None:
                        finished_at = utc_now()
                        record_runtime_event(
                            cfg,
                            database,
                            event="bot_tick_error",
                            level="ERROR",
                            details={"error": str(exc), "consecutive_errors": current_errors},
                            ts=finished_at,
                        )
                        record_cycle_audit(
                            cfg,
                            database,
                            cycle_id=cycle_id,
                            started_at=started_at,
                            finished_at=finished_at,
                            status="error",
                            event="tick_failed",
                            exit_reason=str(exc),
                            details={"consecutive_errors": current_errors},
                        )
                    if current_errors >= int(circuit_breaker_max_errors_fn(cfg)):
                        cooldown = int(circuit_breaker_cooldown_seconds_fn(cfg))
                        _safe_store_flag(store, "paused", True)
                        set_reentry_block_fn(store, cooldown, "circuit_breaker")
                        _record_bot_event(store, "ERROR", "circuit_breaker_paused", {"cooldown_seconds": cooldown})
                        if logger is not None and hasattr(logger, "error"):
                            logger.error("circuit_breaker_paused", cooldown_seconds=cooldown)
                        if database is not None:
                            record_runtime_event(
                                cfg,
                                database,
                                event="circuit_breaker_paused",
                                level="ERROR",
                                details={"cooldown_seconds": cooldown},
                            )
                        sleep_fn(max(cooldown, 1))
                    else:
                        sleep_fn(max(loop_seconds, 1))
                    continue
                sleep_fn(max(loop_seconds, 1))
    except InstanceLockError as exc:
        if database is not None:
            record_runtime_event(cfg, database, event="instance_lock_failed", level="ERROR", details={"error": str(exc)})
        _record_bot_event(store, "ERROR", "instance_lock_failed", {"error": str(exc)})
        if logger is not None and hasattr(logger, "error"):
            logger.error("instance_lock_failed", error=str(exc))
        raise


def _run_loop_simple(
    cfg: dict[str, Any],
    *,
    database: Any,
    store: Any | None,
    tick_once: Callable[[], CycleResult],
    logger: Any | None = None,
    sleep_fn: Callable[[float], None] = time_module.sleep,
) -> int:
    from smartcrypto.runtime.audit import record_runtime_event
    from smartcrypto.runtime.single_instance import acquire_single_instance, release_single_instance

    runtime = dict(cfg.get("runtime", {}) or {})
    try:
        max_iterations = max(0, int(runtime.get("max_iterations", cfg.get("__max_iterations", 0)) or 0))
    except Exception:
        max_iterations = 0
    try:
        sleep_seconds = max(0.0, float(runtime.get("sleep_seconds", cfg.get("__sleep_seconds", 0.0)) or 0.0))
    except Exception:
        sleep_seconds = 0.0

    completed = 0
    acquired = False
    release_event = True
    try:
        acquire_single_instance(cfg, database=database)
        acquired = True
        while True:
            if max_iterations and completed >= max_iterations:
                break
            try:
                result = tick_once()
            except KeyboardInterrupt:
                release_event = False
                record_runtime_event(
                    cfg,
                    database,
                    event="unexpected_shutdown",
                    level="ERROR",
                    details={"reason": "keyboard_interrupt", "run_id": cfg.get("__run_id", "")},
                )
                _record_bot_event(store, "ERROR", "unexpected_shutdown", {"reason": "keyboard_interrupt"})
                raise
            except BaseException as exc:
                release_event = False
                record_runtime_event(
                    cfg,
                    database,
                    event="unexpected_shutdown",
                    level="ERROR",
                    details={"error": str(exc), "run_id": cfg.get("__run_id", "")},
                )
                _record_bot_event(store, "ERROR", "unexpected_shutdown", {"error": str(exc)})
                raise

            _post_tick_observability_cycle_result(
                cfg,
                database=database,
                store=store,
                result=result,
            )
            completed += 1

            if logger is not None and hasattr(logger, "info"):
                logger.info("Tick concluído", extra={"cycle_id": result.cycle_id, "status": result.status})
            if sleep_seconds > 0:
                sleep_fn(sleep_seconds)
    except DuplicateInstanceBlockedError:
        _record_bot_event(store, "ERROR", "duplicate_instance_blocked", {"run_id": cfg.get("__run_id", "")})
        raise
    finally:
        if acquired:
            try:
                release_single_instance(cfg, database=database, record_event=release_event)
            except Exception:
                pass

    return completed


def run_loop(*args: Any, **kwargs: Any) -> Any:
    if "tick_once" in kwargs or (kwargs.get("database") is not None and kwargs.get("tick_fn") is None):
        return _run_loop_simple(*args, **kwargs)
    return _run_loop_legacy(*args, **kwargs)
