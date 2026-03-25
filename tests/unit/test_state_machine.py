import pytest

from smartcrypto.domain.enums import CycleState, OrderState
from smartcrypto.execution.state_machine import CycleMachine


def test_happy_path_transitions() -> None:
    machine = CycleMachine()

    machine.mark_entering()
    machine.mark_submitted()
    machine.mark_long()
    machine.mark_exiting()

    assert machine.cycle_state == CycleState.EXITING
    assert machine.order_state == OrderState.PLANNED


def test_invalid_transition_raises() -> None:
    machine = CycleMachine()

    with pytest.raises(ValueError):
        machine.mark_exiting()
