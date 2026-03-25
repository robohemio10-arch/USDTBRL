from smartcrypto.domain.enums import OrderSide
from smartcrypto.execution.engine import ExecutionEngine
from smartcrypto.execution.state_machine import CycleMachine


def test_engine_builds_entry_intent() -> None:
    engine = ExecutionEngine(machine=CycleMachine())

    intent = engine.build_entry_intent(
        reason="first_entry",
        order_type="limit",
        requested_brl_value=300.0,
        requested_price_brl=5.0,
    )

    assert intent.side == OrderSide.BUY
    assert engine.status()["cycle_state"] == "entering"
