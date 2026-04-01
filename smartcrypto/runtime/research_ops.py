from __future__ import annotations

from typing import Any

import pandas as pd

from smartcrypto.infra.binance_adapter import ExchangeAdapter
from smartcrypto.research.optimizer import optimize_on_dataset as research_optimize_on_dataset
from smartcrypto.research.services import (
    run_backtest_service,
    run_monte_carlo_service,
    run_optimize_service,
    run_walk_forward_service,
)
from smartcrypto.research.simulator import simulate_strategy as research_simulate_strategy
from smartcrypto.state.store import StateStore


def simulate_strategy(cfg: dict[str, Any], ohlcv: pd.DataFrame) -> dict[str, Any]:
    return research_simulate_strategy(cfg, ohlcv)


def backtest(cfg: dict[str, Any], exchange: ExchangeAdapter, store: StateStore) -> dict[str, Any]:
    return run_backtest_service(cfg, exchange, store)


def monte_carlo(
    cfg: dict[str, Any], exchange: ExchangeAdapter, store: StateStore
) -> dict[str, Any]:
    return run_monte_carlo_service(cfg, exchange, store)


def optimize_on_dataset(cfg: dict[str, Any], data: pd.DataFrame) -> dict[str, Any]:
    return research_optimize_on_dataset(cfg, data)


def optimize(cfg: dict[str, Any], exchange: ExchangeAdapter, store: StateStore) -> dict[str, Any]:
    return run_optimize_service(cfg, exchange, store)


def walk_forward(
    cfg: dict[str, Any], exchange: ExchangeAdapter, store: StateStore
) -> dict[str, Any]:
    return run_walk_forward_service(cfg, exchange, store)
