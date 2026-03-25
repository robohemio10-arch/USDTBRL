from smartcrypto.domain.enums import CycleState, RegimeType


def test_cycle_state_values_are_stable() -> None:
    assert CycleState.FLAT.value == "flat"
    assert CycleState.LONG.value == "long"


def test_regime_values_are_stable() -> None:
    assert RegimeType.BULL.value == "bull"
    assert RegimeType.BEAR.value == "bear"
