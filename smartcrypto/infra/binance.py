from __future__ import annotations

import warnings

import warnings

warnings.warn(
    "smartcrypto.infra.binance is deprecated; use smartcrypto.infra.binance_adapter",
    DeprecationWarning,
    stacklevel=2,
)

from smartcrypto.infra.binance_adapter import *  # noqa