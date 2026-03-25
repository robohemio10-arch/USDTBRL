
from __future__ import annotations

from dataclasses import asdict, dataclass

from smartcrypto.state.position_manager import PositionManager
from smartcrypto.state.store import StateStore


@dataclass(frozen=True)
class PortfolioSnapshot:
    status: str
    qty_usdt: float
    average_price_brl: float
    mark_price_brl: float
    position_notional_brl: float
    invested_brl: float
    unrealized_pnl_brl: float
    realized_pnl_brl: float
    equity_brl: float
    drawdown_pct: float


@dataclass(frozen=True)
class PortfolioRuntimeView:
    position: dict[str, float | int | str]
    cash_brl: float
    equity_brl: float
    position_notional_brl: float
    invested_brl: float
    unrealized_pnl_brl: float
    realized_pnl_brl: float
    drawdown_pct: float


class Portfolio:
    def __init__(self, store: StateStore, position_manager: PositionManager | None = None) -> None:
        self.store = store
        self.position_manager = position_manager or PositionManager(store)

    def last_equity(self) -> float | None:
        return self.store.last_equity()

    def compute_drawdown_pct(self) -> float:
        return self.store.compute_drawdown_pct()

    def snapshot(self, *, mark_price_brl: float) -> PortfolioSnapshot:
        position = self.position_manager.current()
        mtm = self.position_manager.mark_to_market(mark_price_brl=mark_price_brl)
        equity = position.realized_pnl_brl + mtm["position_notional_brl"]
        if position.status == "flat":
            equity = position.realized_pnl_brl
        return PortfolioSnapshot(
            status=position.status,
            qty_usdt=position.qty_usdt,
            average_price_brl=position.avg_price_brl,
            mark_price_brl=mark_price_brl,
            position_notional_brl=mtm["position_notional_brl"],
            invested_brl=position.brl_spent,
            unrealized_pnl_brl=mtm["unrealized_pnl_brl"],
            realized_pnl_brl=position.realized_pnl_brl,
            equity_brl=equity,
            drawdown_pct=self.compute_drawdown_pct(),
        )

    def runtime_view(self, *, mark_price_brl: float, initial_cash_brl: float) -> PortfolioRuntimeView:
        position = self.position_manager.current()
        mtm = self.position_manager.mark_to_market(mark_price_brl=mark_price_brl)
        cash_brl = self.position_manager.cash_available(initial_cash_brl=initial_cash_brl)
        equity_brl = cash_brl + mtm["position_notional_brl"]
        position_payload = asdict(position)
        position_payload["unrealized_pnl_brl"] = mtm["unrealized_pnl_brl"]
        return PortfolioRuntimeView(
            position=position_payload,
            cash_brl=round(cash_brl, 8),
            equity_brl=round(equity_brl, 8),
            position_notional_brl=mtm["position_notional_brl"],
            invested_brl=position.brl_spent,
            unrealized_pnl_brl=mtm["unrealized_pnl_brl"],
            realized_pnl_brl=position.realized_pnl_brl,
            drawdown_pct=self.compute_drawdown_pct(),
        )
