
from __future__ import annotations

from smartcrypto.runtime import bot_runtime


def test_execute_buy_wrapper_uses_execution_module(monkeypatch):
    called = {}

    def fake(**kwargs):
        called.update(kwargs)
        return "ok"

    monkeypatch.setattr(bot_runtime, "execution_execute_buy", fake)

    result = bot_runtime.execute_buy(
        store="store",
        position="position",
        exchange="exchange",
        price_brl=1.0,
        brl_value=2.0,
        reason="initial_entry",
        regime="range",
        cfg={"execution": {}},
        params={},
    )

    assert result == "ok"
    assert called["store"] == "store"
    assert called["brl_value"] == 2.0


def test_tick_wrapper_uses_runtime_tick(monkeypatch):
    called = {}

    def fake(cfg, store, exchange):
        called["cfg"] = cfg
        called["store"] = store
        called["exchange"] = exchange
        return {"status": "ok"}

    monkeypatch.setattr(bot_runtime, "runtime_tick", fake)

    result = bot_runtime.tick({"market": {}}, "store", "exchange")

    assert result == {"status": "ok"}
    assert called["store"] == "store"
