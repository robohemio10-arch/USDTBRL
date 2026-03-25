from decimal import Decimal

from smartcrypto.domain.enums import CycleState
from smartcrypto.domain.models import PositionView


def test_position_view_notional() -> None:
    position = PositionView(
        symbol="USDTBRL",
        quantity=Decimal("10"),
        average_price=Decimal("5.00"),
        mark_price=Decimal("5.10"),
        cycle_state=CycleState.LONG,
    )

    assert position.notional == Decimal("51.00")
