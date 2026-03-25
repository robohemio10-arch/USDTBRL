from __future__ import annotations

from smartcrypto.runtime import bot_runtime
from smartcrypto.runtime import compat


def test_bot_runtime_reexports_compat_symbols():
    cfg = {"simulation": {"mock_price_brl": 5.55}}
    assert bot_runtime.fallback_price_brl(cfg) == compat.fallback_price_brl(cfg)
    assert callable(bot_runtime.status_payload)
    assert callable(bot_runtime.recover_dispatch_locks)
