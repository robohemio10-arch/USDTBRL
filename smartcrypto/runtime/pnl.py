from __future__ import annotations

import pandas as pd

from smartcrypto.state.store import PositionState, StateStore


def cash_available(initial_cash: float, position: PositionState) -> float:
    return float(initial_cash) + float(position.realized_pnl_brl) - float(position.brl_spent)


def todays_realized_loss_brl(store: StateStore) -> float:
    df = store.read_df("cycles", 2000)
    if df.empty or "closed_at" not in df.columns:
        return 0.0
    closed = df.copy()
    closed["closed_at"] = pd.to_datetime(closed["closed_at"], errors="coerce", utc=True)
    today = pd.Timestamp.utcnow().normalize()
    closed = closed[closed["closed_at"] >= today]
    if closed.empty or "pnl_brl" not in closed.columns:
        return 0.0
    return float(closed["pnl_brl"].fillna(0.0).sum())
