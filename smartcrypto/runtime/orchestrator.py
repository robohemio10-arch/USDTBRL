from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from smartcrypto.common.constants import DEFAULT_CONFIG_PATH
from smartcrypto.common.logging_utils import BotLogger
from smartcrypto.config import load_config
from smartcrypto.infra.binance_adapter import ExchangeAdapter
from smartcrypto.infra.database import SQLiteDatabase
from smartcrypto.runtime.feature_flags import load_feature_flags
from smartcrypto.state.bot_events import BotEventStore
from smartcrypto.state.dispatch_locks import DispatchLockStore
from smartcrypto.state.order_events import OrderEventStore
from smartcrypto.state.order_projections import OrderProjectionStore
from smartcrypto.state.portfolio import Portfolio
from smartcrypto.state.position_manager import PositionManager
from smartcrypto.state.reconciliation_audit import ReconciliationAuditStore
from smartcrypto.state.snapshots import SnapshotStore
from smartcrypto.state.store import StateStore


@dataclass(frozen=True)
class RuntimeContext:
    config: dict[str, Any]
    database: SQLiteDatabase
    store: StateStore
    position_manager: PositionManager
    portfolio: Portfolio
    order_projections: OrderProjectionStore
    order_events: OrderEventStore
    snapshots: SnapshotStore
    bot_events: BotEventStore
    dispatch_locks: DispatchLockStore
    reconciliation_audit: ReconciliationAuditStore
    exchange: ExchangeAdapter
    feature_flags: dict[str, bool]


@dataclass(frozen=True)
class RuntimeServices:
    context: RuntimeContext
    logger: BotLogger
    config_path: str


def resolve_config_path(path: str | Path | None = None) -> Path:
    candidate = Path(path) if path else DEFAULT_CONFIG_PATH
    return candidate


def bootstrap_feature_flags(config_dir: str | Path = "config") -> dict[str, bool]:
    return load_feature_flags(Path(config_dir) / "feature_flags.yaml")


def bootstrap_runtime_context(config_path: str | Path | None = None) -> RuntimeContext:
    resolved_config_path = resolve_config_path(config_path)
    config = load_config(str(resolved_config_path))
    db_path = str(config["storage"]["db_path"])
    database = SQLiteDatabase(db_path)
    store = StateStore(db_path, database=database)
    position_manager = PositionManager(store)
    portfolio = Portfolio(store, position_manager=position_manager)
    exchange = ExchangeAdapter(config)
    feature_flags = bootstrap_feature_flags(Path(resolved_config_path).parent)
    return RuntimeContext(
        config=config,
        database=database,
        store=store,
        position_manager=position_manager,
        portfolio=portfolio,
        order_projections=store.order_projections,
        order_events=store.order_events,
        snapshots=store.snapshots,
        bot_events=store.bot_events,
        dispatch_locks=store.dispatch_locks,
        reconciliation_audit=store.reconciliation_audit,
        exchange=exchange,
        feature_flags=feature_flags,
    )


def bootstrap_runtime_services(config_path: str | Path | None = None) -> RuntimeServices:
    resolved_config_path = resolve_config_path(config_path)
    context = bootstrap_runtime_context(resolved_config_path)
    context.config["__config_path"] = str(resolved_config_path.resolve())
    logger = BotLogger(context.config)
    return RuntimeServices(
        context=context,
        logger=logger,
        config_path=str(resolved_config_path),
    )


def run_startup_reconcile(
    context: RuntimeContext,
    logger: Any,
    *,
    build_id: str,
    recover_dispatch_locks_fn: Callable[[dict[str, Any], StateStore, ExchangeAdapter], None],
    reconcile_live_exchange_state_fn: Callable[..., Any],
) -> None:
    cfg = context.config
    store = context.store
    exchange = context.exchange
    try:
        recover_dispatch_locks_fn(cfg, store, exchange)
        reconcile_live_exchange_state_fn(cfg, store, exchange, last_price=exchange.get_last_price())
        store.add_event("INFO", "live_startup_reconciled", {"build_id": build_id})
        logger.info("live_startup_reconciled", build_id=build_id)
    except Exception as exc:
        store.add_event("ERROR", "live_startup_reconcile_failed", {"error": str(exc)})
        logger.error("live_startup_reconcile_failed", error=str(exc))
