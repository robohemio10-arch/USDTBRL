from __future__ import annotations

from dataclasses import dataclass

from smartcrypto.domain.enums import OrderSide
from smartcrypto.domain.models import EngineStatus, OrderIntent
from smartcrypto.execution.state_machine import CycleMachine


@dataclass
class ExecutionEngine:
    machine: CycleMachine

    def status(self) -> dict[str, str]:
        snapshot = self.machine.snapshot()
        return {
            "cycle_state": snapshot.cycle_state.value,
            "order_state": snapshot.order_state.value,
        }

    def build_entry_intent(
        self,
        *,
        reason: str,
        order_type: str,
        requested_brl_value: float,
        requested_price_brl: float | None,
    ) -> OrderIntent:
        self.machine.mark_entering()
        return OrderIntent(
            side=OrderSide.BUY,
            order_type=order_type,
            reason=reason,
            requested_price_brl=requested_price_brl,
            requested_qty_usdt=None,
            requested_brl_value=requested_brl_value,
        )

    def build_exit_intent(
        self,
        *,
        reason: str,
        order_type: str,
        requested_qty_usdt: float,
        requested_price_brl: float | None,
        requested_brl_value: float | None,
    ) -> OrderIntent:
        self.machine.mark_exiting()
        return OrderIntent(
            side=OrderSide.SELL,
            order_type=order_type,
            reason=reason,
            requested_price_brl=requested_price_brl,
            requested_qty_usdt=requested_qty_usdt,
            requested_brl_value=requested_brl_value,
        )

    def snapshot(self) -> EngineStatus:
        return self.machine.snapshot()
