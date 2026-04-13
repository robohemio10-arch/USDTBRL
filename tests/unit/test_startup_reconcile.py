from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from smartcrypto.execution.reconcile import ReconcileResult
from smartcrypto.infra.database import SQLiteDatabase
from smartcrypto.runtime.audit import read_recent_runtime_events
from smartcrypto.runtime.orchestrator import StartupReconcileFailedError, run_startup_reconcile


class _StoreStub:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict | None]] = []
        self.flags: dict[str, object] = {}

    def add_event(self, level: str, event: str, details: dict | None = None) -> None:
        self.events.append((level, event, details))

    def set_flag(self, key: str, value: object) -> None:
        self.flags[key] = value


class _LoggerStub:
    def __init__(self) -> None:
        self.info_calls: list[tuple[str, dict]] = []
        self.error_calls: list[tuple[str, dict]] = []

    def info(self, event: str, **kwargs) -> None:
        self.info_calls.append((event, kwargs))

    def error(self, event: str, **kwargs) -> None:
        self.error_calls.append((event, kwargs))


class _ExchangeStub:
    def get_last_price(self) -> float:
        return 5.25


def _context(tmp_path: Path, *, fail_closed: bool = True) -> SimpleNamespace:
    database = SQLiteDatabase(str(tmp_path / "runtime.sqlite"))
    return SimpleNamespace(
        config={
            "execution": {"mode": "live"},
            "runtime": {"startup_reconcile_fail_closed": fail_closed},
            "market": {"symbol": "USDT/BRL", "timeframe": "1m"},
            "__operational_manifest": {"run_id": "run-1", "build_id": "build-1"},
        },
        database=database,
        store=_StoreStub(),
        exchange=_ExchangeStub(),
    )


def test_run_startup_reconcile_raises_when_reconcile_requires_action(tmp_path: Path) -> None:
    context = _context(tmp_path)
    logger = _LoggerStub()

    with pytest.raises(StartupReconcileFailedError, match="exchange_qty_diverges_from_local_position"):
        run_startup_reconcile(
            context,
            logger,
            build_id="build-1",
            recover_dispatch_locks_fn=lambda cfg, store, exchange: None,
            reconcile_live_exchange_state_fn=lambda cfg, store, exchange, last_price: ReconcileResult(
                needs_action=True,
                reason="exchange_qty_diverges_from_local_position",
            ),
        )

    events = read_recent_runtime_events(context.database, limit=5)
    assert events.iloc[0]["event"] == "startup_reconcile_failed"
    assert context.store.flags["live_reconcile_required"] is True
    assert context.store.flags["paused"] is True
    assert context.store.events[-1][1] == "live_startup_reconcile_failed"
    assert logger.error_calls[-1][0] == "live_startup_reconcile_failed"


def test_run_startup_reconcile_can_be_configured_not_to_raise(tmp_path: Path) -> None:
    context = _context(tmp_path, fail_closed=False)
    logger = _LoggerStub()

    run_startup_reconcile(
        context,
        logger,
        build_id="build-1",
        recover_dispatch_locks_fn=lambda cfg, store, exchange: None,
        reconcile_live_exchange_state_fn=lambda cfg, store, exchange, last_price: ReconcileResult(
            needs_action=True,
            reason="exchange_position_exists_while_local_flat",
        ),
    )

    events = read_recent_runtime_events(context.database, limit=5)
    assert events.iloc[0]["event"] == "startup_reconcile_failed"
    assert context.store.flags["live_reconcile_required"] is True
    assert context.store.flags["paused"] is True
    assert logger.error_calls[-1][0] == "live_startup_reconcile_failed"


def test_run_startup_reconcile_records_success_when_ok(tmp_path: Path) -> None:
    context = _context(tmp_path)
    logger = _LoggerStub()

    run_startup_reconcile(
        context,
        logger,
        build_id="build-1",
        recover_dispatch_locks_fn=lambda cfg, store, exchange: None,
        reconcile_live_exchange_state_fn=lambda cfg, store, exchange, last_price: ReconcileResult(
            needs_action=False,
            reason="ok",
        ),
    )

    events = read_recent_runtime_events(context.database, limit=5)
    assert events.iloc[0]["event"] == "startup_reconcile_ok"
    assert context.store.events[-1][1] == "live_startup_reconciled"
    assert logger.info_calls[-1][0] == "live_startup_reconciled"
