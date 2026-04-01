from __future__ import annotations
import argparse
import hashlib
import json
import math
import random
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from smartcrypto.common.health import health_report
from smartcrypto.common.logging_utils import BotLogger
from smartcrypto.common.constants import DEFAULT_CONFIG_PATH
from smartcrypto.common.utils import project_root_from_config_path
from smartcrypto.config import load_config
from smartcrypto.domain.regime import compute_regime as domain_compute_regime
from smartcrypto.domain.risk import (
    effective_cycle_cap as domain_effective_cycle_cap,
    estimate_exit_pnl_brl as domain_estimate_exit_pnl_brl,
    min_profit_brl as domain_min_profit_brl,
    min_profit_exit_price as domain_min_profit_exit_price,
)
from smartcrypto.domain.strategy import (
    can_execute_sell_reason as domain_can_execute_sell_reason,
    compute_exit_targets as domain_compute_exit_targets,
    fit_ramps_to_cycle as domain_fit_ramps_to_cycle,
    normalize_ramps as domain_normalize_ramps,
    sanitize_exit_profile as domain_sanitize_exit_profile,
    sell_reason_uses_profit_floor as domain_sell_reason_uses_profit_floor,
    strategy_params as domain_strategy_params,
    strategy_runtime_diagnostics as domain_strategy_runtime_diagnostics,
)
from smartcrypto.execution.controls import (
    build_safety_ladder as execution_build_safety_ladder,
    choose_exit_order_type as execution_choose_exit_order_type,
    clear_reentry_price_block as execution_clear_reentry_price_block,
    entry_fallback_market_enabled as execution_entry_fallback_market_enabled,
    exit_fallback_market_enabled as execution_exit_fallback_market_enabled,
    fallback_market_enabled as execution_fallback_market_enabled,
    is_live_mode as execution_is_live_mode,
    offset_price as execution_offset_price,
    order_type_for as execution_order_type_for,
    post_sell_controls as execution_post_sell_controls,
    reentry_price_threshold as execution_reentry_price_threshold,
    reentry_remaining_seconds as execution_reentry_remaining_seconds,
    reconcile_flat_state as execution_reconcile_flat_state,
    replace_dashboard_orders as execution_replace_dashboard_orders,
    set_reentry_block as execution_set_reentry_block,
    set_reentry_price_block as execution_set_reentry_price_block,
)

from smartcrypto.execution.trading import (
    execute_buy as execution_execute_buy,
    execute_sell as execution_execute_sell,
    record_execution_report as execution_record_execution_report,
    record_simulated_execution as execution_record_simulated_execution,
)
from smartcrypto.runtime.tick_cycle import tick as runtime_tick
from smartcrypto.runtime.reconcile_ops import (
    active_dispatch_lock_present as runtime_active_dispatch_lock_present,
    bot_managed_open_order_refs as runtime_bot_managed_open_order_refs,
    inflight_order_lock_seconds as runtime_inflight_order_lock_seconds,
    is_bot_managed_exchange_order as runtime_is_bot_managed_exchange_order,
    live_reconcile_allow_extra_base_asset_balance as runtime_live_reconcile_allow_extra_base_asset_balance,
    live_reconcile_pause_on_mismatch as runtime_live_reconcile_pause_on_mismatch,
    live_reconcile_qty_tolerance as runtime_live_reconcile_qty_tolerance,
    map_exchange_order_state as runtime_map_exchange_order_state,
    mark_dispatch_unknown as runtime_mark_dispatch_unknown,
    reconcile_live_exchange_state as runtime_reconcile_live_exchange_state,
    recover_dispatch_locks as runtime_recover_dispatch_locks,
)
from smartcrypto.infra.binance_adapter import ExchangeAdapter
from smartcrypto.runtime.cache import (
    cache_symbol_token as runtime_cache_symbol_token,
    dashboard_cache_dir as runtime_dashboard_cache_dir,
    market_cache_file as runtime_market_cache_file,
    open_orders_cache_file as runtime_open_orders_cache_file,
    persist_dashboard_runtime_state as runtime_persist_dashboard_runtime_state,
    write_market_cache as runtime_write_market_cache,
    write_open_orders_cache as runtime_write_open_orders_cache,
    write_runtime_status_cache as runtime_write_runtime_status_cache,
    runtime_status_cache_file as runtime_runtime_status_cache_file,
)
from smartcrypto.runtime.notifications import (
    ntfy_cfg as runtime_ntfy_cfg,
    ntfy_client as runtime_ntfy_client,
    ntfy_mode_allowed as runtime_ntfy_mode_allowed,
    parse_utc_offset as runtime_parse_utc_offset,
    publish_ntfy as runtime_publish_ntfy,
    send_daily_report_if_due as runtime_send_daily_report_if_due,
    send_sell_notification as runtime_send_sell_notification,
)
from smartcrypto.runtime.status import (
    log_snapshot as runtime_log_snapshot,
    status_payload as runtime_status_payload,
)
from smartcrypto.runtime.lifecycle import (
    build_cli_parser,
    build_healthcheck_payload,
    loop_interval_seconds,
    resolve_status_price,
    run_loop,
    run_once_cycle,
    should_perform_startup_reconcile,
)
from smartcrypto.research.services import (
    run_backtest_service,
    run_monte_carlo_service,
    run_optimize_service,
    run_walk_forward_service,
)
from smartcrypto.research.simulator import (
    block_bootstrap_ohlcv as research_block_bootstrap_ohlcv,
    research_candidate_configs as research_research_candidate_configs,
    simulate_strategy as research_simulate_strategy,
    timeframe_to_seconds as research_timeframe_to_seconds,
    research_wait_bars as research_research_wait_bars,
    synthetic_limit_fill_ratio as research_synthetic_limit_fill_ratio,
    build_synthetic_ohlcv_from_close as research_build_synthetic_ohlcv_from_close,
)
from smartcrypto.runtime.orchestrator import (
    bootstrap_runtime_services,
    run_startup_reconcile,
)
from smartcrypto.state.portfolio import Portfolio
from smartcrypto.state.position_manager import PositionManager
from smartcrypto.state.store import PositionState, StateStore, utc_now

BUILD_ID = "phase-d-2026-03-19-01"


def load_yaml(path: str) -> dict[str, Any]:
    return load_config(path)


def project_root_from_cfg(cfg: dict[str, Any]) -> Path:
    cfg_path = str(cfg.get("__config_path", str(DEFAULT_CONFIG_PATH)) or str(DEFAULT_CONFIG_PATH))
    return project_root_from_config_path(cfg_path)


def dashboard_cache_dir(cfg: dict[str, Any]) -> Path:
    return runtime_dashboard_cache_dir(cfg)


def cache_symbol_token(symbol: str) -> str:
    return runtime_cache_symbol_token(symbol)


def market_cache_file(cfg: dict[str, Any], interval: str) -> Path:
    return runtime_market_cache_file(cfg, interval)


def runtime_status_cache_file(cfg: dict[str, Any]) -> Path:
    return runtime_runtime_status_cache_file(cfg)


def open_orders_cache_file(cfg: dict[str, Any]) -> Path:
    return runtime_open_orders_cache_file(cfg)


def write_market_cache(cfg: dict[str, Any], interval: str, df: pd.DataFrame) -> None:
    runtime_write_market_cache(cfg, interval, df)


def write_runtime_status_cache(cfg: dict[str, Any], status: dict[str, Any]) -> None:
    runtime_write_runtime_status_cache(cfg, status)


def write_open_orders_cache(
    cfg: dict[str, Any], orders: list[dict[str, Any]], error: str = ""
) -> None:
    runtime_write_open_orders_cache(cfg, orders, error=error)


def persist_dashboard_runtime_state(
    cfg: dict[str, Any], exchange: ExchangeAdapter, status: dict[str, Any]
) -> None:
    runtime_persist_dashboard_runtime_state(cfg, exchange, status)


def timeframe_to_seconds(timeframe: str) -> int:
    return research_timeframe_to_seconds(timeframe)


def research_wait_bars(cfg: dict[str, Any]) -> int:
    return research_research_wait_bars(cfg)


def synthetic_limit_fill_ratio(side: str, price_brl: float, row: pd.Series) -> float:
    return research_synthetic_limit_fill_ratio(side, price_brl, row)


def build_synthetic_ohlcv_from_close(
    base: pd.DataFrame, synthetic_close: pd.Series
) -> pd.DataFrame:
    return research_build_synthetic_ohlcv_from_close(base, synthetic_close)


def block_bootstrap_ohlcv(data: pd.DataFrame, runs_seed: int, block_size: int) -> pd.DataFrame:
    return research_block_bootstrap_ohlcv(data, runs_seed=runs_seed, block_size=block_size)


def research_candidate_configs(
    cfg: dict[str, Any],
) -> list[tuple[dict[str, Any], dict[str, float]]]:
    return research_research_candidate_configs(cfg)


def compute_regime(ohlcv: pd.DataFrame) -> tuple[str, float, dict[str, float]]:
    return domain_compute_regime(ohlcv)

def normalize_ramps(
    cfg: dict[str, Any], regime: str, first_buy_brl: float
) -> list[dict[str, float]]:
    return domain_normalize_ramps(cfg, regime, first_buy_brl)

def effective_cycle_cap(cfg: dict[str, Any], requested_cycle_brl: float) -> float:
    return domain_effective_cycle_cap(cfg, requested_cycle_brl)

def fit_ramps_to_cycle(
    ramps: list[dict[str, float]],
    *,
    first_buy_brl: float,
    cycle_cap_brl: float,
) -> tuple[list[dict[str, float]], int, float]:
    return domain_fit_ramps_to_cycle(
        ramps,
        first_buy_brl=first_buy_brl,
        cycle_cap_brl=cycle_cap_brl,
    )

def sanitize_exit_profile(
    *,
    tp_pct: float,
    trailing_activation_pct: float,
    trailing_callback_pct: float,
    stop_loss_pct: float,
    trailing_enabled: bool,
) -> dict[str, float | bool]:
    return domain_sanitize_exit_profile(
        tp_pct=tp_pct,
        trailing_activation_pct=trailing_activation_pct,
        trailing_callback_pct=trailing_callback_pct,
        stop_loss_pct=stop_loss_pct,
        trailing_enabled=trailing_enabled,
    )

def strategy_runtime_diagnostics(params: dict[str, Any]) -> list[dict[str, Any]]:
    return domain_strategy_runtime_diagnostics(params)

def strategy_params(cfg: dict[str, Any], regime: str) -> dict[str, Any]:
    return domain_strategy_params(cfg, regime)

def min_profit_brl(cfg: dict[str, Any]) -> float:
    return domain_min_profit_brl(cfg)

def min_profit_exit_price(
    *, qty_usdt: float, brl_spent: float, fee_rate: float, desired_profit_brl: float
) -> float:
    return domain_min_profit_exit_price(
        qty_usdt=qty_usdt,
        brl_spent=brl_spent,
        fee_rate=fee_rate,
        desired_profit_brl=desired_profit_brl,
    )

def estimate_exit_pnl_brl(
    *, qty_usdt: float, brl_spent: float, price_brl: float, fee_rate: float
) -> float:
    return domain_estimate_exit_pnl_brl(
        qty_usdt=qty_usdt,
        brl_spent=brl_spent,
        price_brl=price_brl,
        fee_rate=fee_rate,
    )

def compute_exit_targets(
    *,
    qty_usdt: float,
    brl_spent: float,
    avg_price_brl: float,
    params: dict[str, Any],
    cfg: dict[str, Any],
) -> tuple[float, float]:
    return domain_compute_exit_targets(
        qty_usdt=qty_usdt,
        brl_spent=brl_spent,
        avg_price_brl=avg_price_brl,
        params=params,
        cfg=cfg,
    )

def sell_reason_uses_profit_floor(reason: str) -> bool:
    return domain_sell_reason_uses_profit_floor(reason)

def can_execute_sell_reason(
    *, position: PositionState, price_brl: float, reason: str, cfg: dict[str, Any]
) -> bool:
    return domain_can_execute_sell_reason(
        qty_usdt=float(position.qty_usdt),
        brl_spent=float(position.brl_spent),
        price_brl=float(price_brl),
        reason=reason,
        cfg=cfg,
    )

def new_bot_order_id(side: str, reason: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    return f"{side.upper()}-{reason}-{stamp}-{uuid.uuid4().hex[:8]}"


def client_order_id_prefix(bot_order_id: str) -> str:
    digest = hashlib.sha1(bot_order_id.encode("utf-8")).hexdigest()[:18]
    return f"SC{digest}".upper()


def inflight_order_lock_seconds(cfg: dict[str, Any]) -> int:
    return runtime_inflight_order_lock_seconds(cfg)

def circuit_breaker_max_errors(cfg: dict[str, Any]) -> int:
    return max(1, int(cfg.get("runtime", {}).get("circuit_breaker_max_errors", 5) or 5))


def circuit_breaker_cooldown_seconds(cfg: dict[str, Any]) -> int:
    return max(30, int(cfg.get("runtime", {}).get("circuit_breaker_cooldown_seconds", 300) or 300))


def live_reconcile_pause_on_mismatch(cfg: dict[str, Any]) -> bool:
    return runtime_live_reconcile_pause_on_mismatch(cfg)

def live_reconcile_qty_tolerance(
    cfg: dict[str, Any], exchange: ExchangeAdapter | None = None
) -> float:
    return runtime_live_reconcile_qty_tolerance(cfg, exchange)

def live_reconcile_allow_extra_base_asset_balance(cfg: dict[str, Any]) -> bool:
    return runtime_live_reconcile_allow_extra_base_asset_balance(cfg)

def bot_managed_open_order_refs(store: StateStore, limit: int = 500) -> tuple[set[str], set[str]]:
    return runtime_bot_managed_open_order_refs(store, limit=limit)

def is_bot_managed_exchange_order(
    order: dict[str, Any],
    *,
    known_exchange_ids: set[str],
    known_client_ids: set[str],
) -> bool:
    return runtime_is_bot_managed_exchange_order(
        order,
        known_exchange_ids=known_exchange_ids,
        known_client_ids=known_client_ids,
    )

def mark_dispatch_unknown(
    store: StateStore,
    *,
    bot_order_id: str,
    side: str,
    reason: str,
    order_type: str,
    requested_price: float | None,
    requested_qty_usdt: float | None,
    requested_brl_value: float | None,
    client_prefix: str,
    error: Exception,
) -> None:
    runtime_mark_dispatch_unknown(
        store,
        bot_order_id=bot_order_id,
        side=side,
        reason=reason,
        order_type=order_type,
        requested_price=requested_price,
        requested_qty_usdt=requested_qty_usdt,
        requested_brl_value=requested_brl_value,
        client_prefix=client_prefix,
        error=error,
    )

recover_dispatch_locks = runtime_recover_dispatch_locks

def active_dispatch_lock_present(cfg: dict[str, Any], store: StateStore) -> bool:
    return runtime_active_dispatch_lock_present(cfg, store)

def reconcile_live_exchange_state(
    cfg: dict[str, Any], store: StateStore, exchange: ExchangeAdapter, *, last_price: float
) -> None:
    runtime_reconcile_live_exchange_state(cfg, store, exchange, last_price=last_price)

def map_exchange_order_state(snapshot: dict[str, Any] | None) -> str:
    return runtime_map_exchange_order_state(snapshot)

def record_execution_report(
    *,
    store: StateStore,
    bot_order_id: str,
    side: str,
    reason: str,
    requested_order_type: str,
    requested_qty_usdt: float | None = None,
    requested_brl_value: float | None = None,
    report: dict[str, Any] | None = None,
) -> None:
    return execution_record_execution_report(
        store=store,
        bot_order_id=bot_order_id,
        side=side,
        reason=reason,
        requested_order_type=requested_order_type,
        requested_qty_usdt=requested_qty_usdt,
        requested_brl_value=requested_brl_value,
        report=report,
    )

def record_simulated_execution(
    *,
    store: StateStore,
    bot_order_id: str,
    side: str,
    reason: str,
    order_type: str,
    price_brl: float,
    qty_usdt: float,
    brl_value: float,
) -> None:
    return execution_record_simulated_execution(
        store=store,
        bot_order_id=bot_order_id,
        side=side,
        reason=reason,
        order_type=order_type,
        price_brl=price_brl,
        qty_usdt=qty_usdt,
        brl_value=brl_value,
    )

def parse_utc_offset(value: str) -> timezone:
    return runtime_parse_utc_offset(value)


def ntfy_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    return runtime_ntfy_cfg(cfg)


def ntfy_client(cfg: dict[str, Any]):
    return runtime_ntfy_client(cfg)


def ntfy_mode_allowed(cfg: dict[str, Any]) -> bool:
    return runtime_ntfy_mode_allowed(cfg)


def publish_ntfy(
    cfg: dict[str, Any], *, title: str, message: str, priority: str = "default", tags: str = ""
) -> None:
    runtime_publish_ntfy(cfg, title=title, message=message, priority=priority, tags=tags)


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
    runtime_send_sell_notification(
        store=store,
        cfg=cfg,
        reason=reason,
        exec_price=exec_price,
        exec_qty=exec_qty,
        pnl_brl=pnl_brl,
        pnl_pct=pnl_pct,
        order_type=order_type,
    )


def send_daily_report_if_due(
    *, store: StateStore, cfg: dict[str, Any], position: PositionState, last_price: float
) -> None:
    runtime_send_daily_report_if_due(store=store, cfg=cfg, position=position, last_price=last_price)


order_type_for = execution_order_type_for
offset_price = execution_offset_price
is_live_mode = execution_is_live_mode
fallback_market_enabled = execution_fallback_market_enabled
entry_fallback_market_enabled = execution_entry_fallback_market_enabled
exit_fallback_market_enabled = execution_exit_fallback_market_enabled
choose_exit_order_type = execution_choose_exit_order_type
set_reentry_block = execution_set_reentry_block
reentry_remaining_seconds = execution_reentry_remaining_seconds
clear_reentry_price_block = execution_clear_reentry_price_block
set_reentry_price_block = execution_set_reentry_price_block
reentry_price_threshold = execution_reentry_price_threshold
post_sell_controls = execution_post_sell_controls
reconcile_flat_state = execution_reconcile_flat_state
build_safety_ladder = execution_build_safety_ladder
replace_dashboard_orders = execution_replace_dashboard_orders


def execute_buy(
    *,
    store: StateStore,
    position: PositionState,
    exchange: ExchangeAdapter,
    price_brl: float,
    brl_value: float,
    reason: str,
    regime: str,
    cfg: dict[str, Any],
    params: dict[str, Any],
) -> PositionState:
    return execution_execute_buy(
        store=store,
        position=position,
        exchange=exchange,
        price_brl=price_brl,
        brl_value=brl_value,
        reason=reason,
        regime=regime,
        cfg=cfg,
        params=params,
    )

def execute_sell(
    *,
    store: StateStore,
    position: PositionState,
    exchange: ExchangeAdapter,
    price_brl: float,
    reason: str,
    regime: str,
    cfg: dict[str, Any],
    params: dict[str, Any],
) -> PositionState:
    return execution_execute_sell(
        store=store,
        position=position,
        exchange=exchange,
        price_brl=price_brl,
        reason=reason,
        regime=regime,
        cfg=cfg,
        params=params,
    )

def cash_available(initial_cash: float, position: PositionState) -> float:
    return initial_cash + position.realized_pnl_brl - position.brl_spent



def log_snapshot(
    store: StateStore,
    *,
    price: float,
    position: PositionState,
    cfg: dict[str, Any],
    regime: str,
    meta: dict[str, Any] | None = None,
) -> None:
    runtime_log_snapshot(
        store,
        price=price,
        position=position,
        cfg=cfg,
        regime=regime,
        meta=meta,
    )


def status_payload(store: StateStore, price: float, cfg: dict[str, Any]) -> dict[str, Any]:
    return runtime_status_payload(store, price, cfg)


def todays_realized_loss_brl(store: StateStore) -> float:

    df = store.read_df("cycles", 2000)
    if df.empty or "closed_at" not in df.columns:
        return 0.0
    closed = df.copy()
    closed["closed_at"] = pd.to_datetime(closed["closed_at"], errors="coerce", utc=True)
    today = pd.Timestamp.utcnow().normalize()
    closed = closed[closed["closed_at"] >= today]
    if closed.empty or "pnl_brl" not in closed.columns:
        return 0.0
    return float(closed["pnl_brl"].fillna(0.0).sum())


def simulate_strategy(cfg: dict[str, Any], ohlcv: pd.DataFrame) -> dict[str, Any]:
    return research_simulate_strategy(cfg, ohlcv)


def backtest(cfg: dict[str, Any], exchange: ExchangeAdapter, store: StateStore) -> dict[str, Any]:
    from smartcrypto.research.services import run_backtest_service

    return run_backtest_service(cfg, exchange, store)
def monte_carlo(
    cfg: dict[str, Any], exchange: ExchangeAdapter, store: StateStore
) -> dict[str, Any]:
    from smartcrypto.research.services import run_monte_carlo_service

    return run_monte_carlo_service(cfg, exchange, store)
def optimize_on_dataset(cfg: dict[str, Any], data: pd.DataFrame) -> dict[str, Any]:
    from smartcrypto.research.optimizer import optimize_on_dataset as research_optimize_on_dataset

    return research_optimize_on_dataset(cfg, data)
def optimize(cfg: dict[str, Any], exchange: ExchangeAdapter, store: StateStore) -> dict[str, Any]:
    from smartcrypto.research.services import run_optimize_service

    return run_optimize_service(cfg, exchange, store)
def walk_forward(
    cfg: dict[str, Any], exchange: ExchangeAdapter, store: StateStore
) -> dict[str, Any]:
    from smartcrypto.research.services import run_walk_forward_service

    return run_walk_forward_service(cfg, exchange, store)
def tick(cfg: dict[str, Any], store: StateStore, exchange: ExchangeAdapter) -> dict[str, Any]:
    return runtime_tick(cfg, store, exchange)

def fallback_price_brl(cfg: dict[str, Any]) -> float:
    simulation_cfg = cfg.get("simulation", {}) or {}
    try:
        return float(simulation_cfg.get("mock_price_brl", 5.2) or 5.2)
    except Exception:
        return 5.2
