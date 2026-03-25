from smartcrypto.execution.engine import ExecutionEngine
from smartcrypto.execution.state_machine import CycleMachine


def test_engine_status_smoke() -> None:
    engine = ExecutionEngine(machine=CycleMachine())

    assert engine.status() == {"cycle_state": "flat", "order_state": "idle"}
