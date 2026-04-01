from __future__ import annotations

from smartcrypto.runtime.pricing import fallback_price_brl


def test_fallback_price_brl_uses_simulation_value():
    assert fallback_price_brl({"simulation": {"mock_price_brl": 6.25}}) == 6.25


def test_fallback_price_brl_falls_back_on_invalid_value():
    assert fallback_price_brl({"simulation": {"mock_price_brl": "bad"}}) == 5.2
