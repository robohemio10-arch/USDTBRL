from __future__ import annotations

import tempfile
from pathlib import Path

from smartcrypto.config import normalize_config
from smartcrypto.execution.trading import execute_sell
from smartcrypto.state.store import StateStore


class FakeExchange:
    pass


def build_cfg(root: Path):
    return normalize_config(
        {
            '__config_path': str(root / 'config.yml'),
            'storage': {'db_path': str(root / 'state.sqlite')},
            'execution': {'mode': 'paper', 'fee_rate': 0.001, 'exit_order_type': 'limit'},
            'market': {'symbol': 'USDTBRL', 'timeframe': '1m'},
            'portfolio': {'initial_cash_brl': 1000.0},
            'risk': {},
            'strategy': {'take_profit_pct': 1.0, 'stop_loss_pct': 5.0},
            'notifications': {'ntfy': {'enabled': False}},
        },
        config_path=root / 'config.yml',
    )


def seed_open_position(store: StateStore):
    store.open_cycle(regime='sideways', entry_price_brl=5.0, qty_usdt=10.0, brl_spent=50.0)
    return store.update_position(
        status='open',
        qty_usdt=10.0,
        brl_spent=50.0,
        avg_price_brl=5.0,
        tp_price_brl=5.2,
        stop_price_brl=4.8,
        regime='sideways',
    )


def test_execute_sell_closes_position_in_paper_mode_without_name_errors():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cfg = build_cfg(root)
        store = StateStore(str(cfg['storage']['db_path']))
        position = seed_open_position(store)
        updated = execute_sell(
            store=store,
            position=position,
            exchange=FakeExchange(),
            price_brl=5.5,
            reason='take_profit',
            regime='sideways',
            cfg=cfg,
            params={'tp_pct': 1.0, 'stop_loss_pct': 5.0},
        )
        assert updated.status == 'flat'
        events = store.read_df('order_events', 20)
        assert not events.empty
        assert 'filled' in set(events['state'].astype(str).str.lower())
