from __future__ import annotations

from smartcrypto.runtime import bot_runtime, compat


def test_bot_runtime_keeps_expected_explicit_exports():
    assert bot_runtime.status_payload is compat.status_payload
    assert bot_runtime.recover_dispatch_locks is compat.recover_dispatch_locks
    assert bot_runtime.persist_dashboard_runtime_state is compat.persist_dashboard_runtime_state
    assert callable(bot_runtime.backtest)
    assert callable(bot_runtime.optimize)
    assert callable(bot_runtime.walk_forward)
    assert callable(bot_runtime.fallback_price_brl)
