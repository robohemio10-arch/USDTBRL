import pytest


def test_legacy_binance_shim_exports_adapter():
    with pytest.deprecated_call(match=r"smartcrypto\.infra\.binance is deprecated"):
        from smartcrypto.infra.binance import ExchangeAdapter as LegacyExchangeAdapter

    from smartcrypto.infra.binance_adapter import ExchangeAdapter

    assert LegacyExchangeAdapter is ExchangeAdapter
