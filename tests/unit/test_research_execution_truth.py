from pathlib import Path
import sqlite3

from smartcrypto.research.execution_truth import load_empirical_execution_summary
from smartcrypto.state.migrations import apply_migrations


def test_load_empirical_execution_summary_reads_order_events(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    conn = sqlite3.connect(db_path)
    apply_migrations(conn)
    conn.execute(
        "insert into order_events(bot_order_id, side, order_type, state, price_brl, qty_usdt, executed_qty_usdt, brl_value, source, note, payload, event_time) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("buy-1", "buy", "limit", "submitted", 5.00, 10.0, 0.0, 50.0, "exchange", "attempt_1", "{}", "2026-01-01T00:00:00Z"),
    )
    conn.execute(
        "insert into order_events(bot_order_id, side, order_type, state, price_brl, qty_usdt, executed_qty_usdt, brl_value, source, note, payload, event_time) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("buy-1", "buy", "limit", "filled", 5.01, 10.0, 10.0, 50.1, "exchange", "attempt_1", "{}", "2026-01-01T00:00:05Z"),
    )
    conn.commit()
    conn.close()
    summary = load_empirical_execution_summary({"storage": {"db_path": str(db_path)}})
    assert summary["available"] is True
    assert summary["rows"] == 1
    assert summary["fill_rate"] == 1.0
    assert summary["median_cost_bps"] > 0.0
