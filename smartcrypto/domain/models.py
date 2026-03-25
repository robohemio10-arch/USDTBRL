from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from smartcrypto.domain.enums import CycleState, OrderSide, OrderState, RegimeType


@dataclass(frozen=True)
class PositionView:
    symbol: str
    quantity: Decimal
    average_price: Decimal
    mark_price: Decimal
    cycle_state: CycleState

    @property
    def notional(self) -> Decimal:
        return self.quantity * self.mark_price


@dataclass(frozen=True)
class SignalDecision:
    should_buy: bool
    should_sell: bool
    confidence: float
    reason: str


@dataclass(frozen=True)
class BotSnapshot:
    symbol: str
    regime: RegimeType
    equity_brl: Decimal
    has_position: bool
    features: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class RegimeSnapshot:
    regime: RegimeType
    score: float
    features: dict[str, float]


@dataclass(frozen=True)
class OrderIntent:
    side: OrderSide
    order_type: str
    reason: str
    requested_price_brl: float | None
    requested_qty_usdt: float | None
    requested_brl_value: float | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EngineStatus:
    cycle_state: CycleState
    order_state: OrderState
