from smartcrypto.infra.binance import ExchangeAdapter as LegacyExchangeAdapter
from smartcrypto.infra.binance_adapter import ExchangeAdapter as NewExchangeAdapter


def test_legacy_binance_import_shim_points_to_new_adapter():
    assert LegacyExchangeAdapter is NewExchangeAdapter
