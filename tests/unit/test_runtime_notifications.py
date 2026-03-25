from __future__ import annotations

from pathlib import Path

from smartcrypto.runtime.notifications import ntfy_mode_allowed, parse_utc_offset, send_sell_notification
from smartcrypto.state.store import StateStore


def test_parse_utc_offset_supports_negative_offsets() -> None:
    offset = parse_utc_offset("-03:30")
    assert offset.utcoffset(None).total_seconds() == -(3 * 3600 + 30 * 60)


def test_ntfy_mode_allowed_respects_paper_flag() -> None:
    cfg = {
        "execution": {"mode": "paper"},
        "notifications": {"ntfy": {"notify_live": True, "notify_paper": False}},
    }
    assert ntfy_mode_allowed(cfg) is False


def test_send_sell_notification_records_error_when_publish_fails(tmp_path: Path, monkeypatch) -> None:
    store = StateStore(str(tmp_path / "notifications.sqlite"))
    cfg = {
        "market": {"symbol": "USDT/BRL"},
        "execution": {"mode": "live"},
        "notifications": {"ntfy": {"enabled": True, "sales_enabled": True}},
    }

    def explode(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("smartcrypto.runtime.notifications.publish_ntfy", explode)

    send_sell_notification(
        store=store,
        cfg=cfg,
        reason="take_profit",
        exec_price=5.2,
        exec_qty=10.0,
        pnl_brl=2.0,
        pnl_pct=4.0,
        order_type="limit",
    )

    events = store.read_df("bot_events", 10)
    assert not events.empty
    assert events.iloc[0]["event"] == "ntfy_sell_failed"
