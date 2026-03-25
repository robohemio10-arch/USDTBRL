
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from smartcrypto.state.store import PositionState, StateStore


class PositionManager:
    def __init__(self, store: StateStore) -> None:
        self.store = store

    def current(self) -> PositionState:
        return self.store.get_position()

    def current_dict(self) -> dict[str, Any]:
        return asdict(self.current())

    def has_open_position(self) -> bool:
        return self.current().status != "flat" and self.current().qty_usdt > 0.0

    def cash_available(self, *, initial_cash_brl: float) -> float:
        current = self.current()
        return float(initial_cash_brl) + current.realized_pnl_brl - current.brl_spent

    def mark_to_market(self, *, mark_price_brl: float) -> dict[str, float]:
        current = self.current()
        position_notional_brl = current.qty_usdt * float(mark_price_brl)
        unrealized_pnl_brl = (float(mark_price_brl) - current.avg_price_brl) * current.qty_usdt
        if current.status == "flat" or current.qty_usdt <= 0:
            position_notional_brl = 0.0
            unrealized_pnl_brl = 0.0
        return {
            "position_notional_brl": round(position_notional_brl, 8),
            "unrealized_pnl_brl": round(unrealized_pnl_brl, 8),
        }

    def open_position(
        self,
        *,
        regime: str,
        entry_price_brl: float,
        qty_usdt: float,
        brl_spent: float,
        tp_price_brl: float = 0.0,
        stop_price_brl: float = 0.0,
    ) -> PositionState:
        self.store.open_cycle(
            regime=regime,
            entry_price_brl=entry_price_brl,
            qty_usdt=qty_usdt,
            brl_spent=brl_spent,
        )
        return self.store.update_position(
            status="open",
            qty_usdt=qty_usdt,
            brl_spent=brl_spent,
            avg_price_brl=(brl_spent / qty_usdt) if qty_usdt else 0.0,
            tp_price_brl=tp_price_brl,
            stop_price_brl=stop_price_brl,
            regime=regime,
        )

    def sync_position(
        self,
        *,
        qty_usdt: float,
        brl_spent: float,
        avg_price_brl: float,
        safety_count: int,
    ) -> PositionState:
        self.store.sync_open_cycle(
            qty_usdt=qty_usdt,
            brl_spent=brl_spent,
            safety_count=safety_count,
        )
        return self.store.update_position(
            status="open" if qty_usdt > 0 else "flat",
            qty_usdt=qty_usdt,
            brl_spent=brl_spent,
            avg_price_brl=avg_price_brl,
            safety_count=safety_count,
        )

    def activate_trailing(self, *, anchor_brl: float) -> PositionState:
        return self.store.update_position(
            trailing_active=1,
            trailing_anchor_brl=anchor_brl,
        )

    def update_unrealized_pnl(self, *, mark_price_brl: float) -> PositionState:
        current = self.current()
        if current.qty_usdt <= 0:
            return self.store.update_position(unrealized_pnl_brl=0.0)
        unrealized = (mark_price_brl - current.avg_price_brl) * current.qty_usdt
        return self.store.update_position(unrealized_pnl_brl=unrealized)

    def close_position(
        self,
        *,
        exit_price_brl: float,
        brl_received: float,
        fee_brl: float,
        exit_reason: str,
    ) -> PositionState:
        current = self.current()
        pnl_brl = brl_received - current.brl_spent - fee_brl
        pnl_pct = (pnl_brl / current.brl_spent * 100.0) if current.brl_spent else 0.0
        self.store.close_latest_cycle(
            exit_price_brl=exit_price_brl,
            brl_received=brl_received,
            pnl_brl=pnl_brl,
            pnl_pct=pnl_pct,
            safety_count=current.safety_count,
            exit_reason=exit_reason,
        )
        return self.store.reset_position(
            realized_pnl_brl=current.realized_pnl_brl + pnl_brl,
        )
