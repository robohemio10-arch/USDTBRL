from __future__ import annotations

from typing import Any

from smartcrypto.research.backtest import run_backtest
from smartcrypto.research.montecarlo import run_monte_carlo
from smartcrypto.research.optimizer import optimize
from smartcrypto.research.walkforward import run_walkforward


def run_backtest_service(cfg: dict[str, Any], exchange: Any, store: Any) -> dict[str, Any]:
    return run_backtest(cfg, exchange, store)


def run_monte_carlo_service(cfg: dict[str, Any], exchange: Any, store: Any) -> dict[str, Any]:
    return run_monte_carlo(cfg, exchange, store)


def run_optimize_service(cfg: dict[str, Any], exchange: Any, store: Any) -> dict[str, Any]:
    return optimize(cfg, exchange, store)


def run_walk_forward_service(cfg: dict[str, Any], exchange: Any, store: Any) -> dict[str, Any]:
    return run_walkforward(cfg, exchange, store)
