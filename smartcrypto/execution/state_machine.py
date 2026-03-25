from __future__ import annotations

from dataclasses import dataclass

from smartcrypto.domain.enums import CycleState, OrderState
from smartcrypto.domain.models import EngineStatus


@dataclass
class CycleMachine:
    cycle_state: CycleState = CycleState.FLAT
    order_state: OrderState = OrderState.IDLE

    def _guard(self, *, allowed_cycle: set[CycleState], allowed_order: set[OrderState]) -> None:
        if self.cycle_state not in allowed_cycle or self.order_state not in allowed_order:
            raise ValueError(
                f"invalid_transition cycle={self.cycle_state.value} order={self.order_state.value}"
            )

    def mark_entering(self) -> None:
        self._guard(
            allowed_cycle={CycleState.FLAT, CycleState.RECONCILING},
            allowed_order={OrderState.IDLE, OrderState.CANCELLED, OrderState.FAILED},
        )
        self.cycle_state = CycleState.ENTERING
        self.order_state = OrderState.PLANNED

    def mark_submitted(self) -> None:
        self._guard(
            allowed_cycle={CycleState.ENTERING, CycleState.EXITING},
            allowed_order={OrderState.PLANNED},
        )
        self.order_state = OrderState.SUBMITTED

    def mark_partial(self) -> None:
        self._guard(
            allowed_cycle={CycleState.ENTERING, CycleState.EXITING},
            allowed_order={OrderState.SUBMITTED, OrderState.PARTIALLY_FILLED},
        )
        self.order_state = OrderState.PARTIALLY_FILLED

    def mark_long(self) -> None:
        self._guard(
            allowed_cycle={CycleState.ENTERING},
            allowed_order={OrderState.SUBMITTED, OrderState.PARTIALLY_FILLED, OrderState.PLANNED},
        )
        self.cycle_state = CycleState.LONG
        self.order_state = OrderState.FILLED

    def mark_exiting(self) -> None:
        self._guard(
            allowed_cycle={CycleState.LONG},
            allowed_order={OrderState.FILLED, OrderState.IDLE},
        )
        self.cycle_state = CycleState.EXITING
        self.order_state = OrderState.PLANNED

    def mark_reconciling(self) -> None:
        self.cycle_state = CycleState.RECONCILING

    def mark_failed(self) -> None:
        self.order_state = OrderState.FAILED

    def reset(self) -> None:
        self.cycle_state = CycleState.FLAT
        self.order_state = OrderState.IDLE

    def snapshot(self) -> EngineStatus:
        return EngineStatus(cycle_state=self.cycle_state, order_state=self.order_state)
