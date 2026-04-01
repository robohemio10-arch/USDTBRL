from __future__ import annotations

from smartcrypto.research.rollout import market_scope_allowed


def test_market_scope_allowed_blocks_non_listed_symbol() -> None:
    ok, scope = market_scope_allowed(
        {
            "market": {"symbol": "BTC/BRL", "timeframe": "1m"},
            "research": {"ai_rollout_allowed_symbols": ["USDT/BRL"]},
        }
    )
    assert ok is False
    assert scope["symbol_ok"] is False


def test_market_scope_allowed_respects_policy_enable_flag() -> None:
    ok, scope = market_scope_allowed(
        {
            "market": {"symbol": "USDT/BRL", "timeframe": "1m"},
            "research": {
                "ai_rollout_market_policies": [
                    {"symbol": "USDT/BRL", "timeframe": "1m", "enabled": False}
                ]
            },
        }
    )
    assert ok is False
    assert scope["policy_enabled"] is False
