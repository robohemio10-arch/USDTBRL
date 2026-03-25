from __future__ import annotations

import argparse

from smartcrypto.runtime.lifecycle import (
    build_cli_parser,
    build_healthcheck_payload,
    loop_interval_seconds,
    resolve_status_price,
    run_once_cycle,
    should_perform_startup_reconcile,
)


class _DummyStore:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict]] = []
        self.flags: dict[str, object] = {}

    def add_event(self, level: str, code: str, payload: dict) -> None:
        self.events.append((level, code, payload))

    def set_flag(self, key: str, value: object) -> None:
        self.flags[key] = value


class _DummyLogger:
    def __init__(self) -> None:
        self.warning_calls: list[tuple[str, dict]] = []
        self.info_calls: list[tuple[str, dict]] = []

    def warning(self, code: str, **payload) -> None:
        self.warning_calls.append((code, payload))

    def info(self, code: str, **payload) -> None:
        self.info_calls.append((code, payload))


class _RaisingExchange:
    def get_last_price(self) -> float:
        raise RuntimeError("boom")


class _OkExchange:
    def get_last_price(self) -> float:
        return 5.25


def test_build_cli_parser_defaults() -> None:
    parser = build_cli_parser("config/config.yml")
    args = parser.parse_args([])
    assert args.config == "config/config.yml"
    assert args.once is False
    assert args.status is False


def test_should_perform_startup_reconcile() -> None:
    cfg = {"runtime": {"startup_reconcile": True}}
    args = argparse.Namespace(
        backtest=False,
        monte_carlo=False,
        optimize=False,
        walk_forward=False,
    )
    assert should_perform_startup_reconcile(cfg, is_live=True, args=args) is True
    args.backtest = True
    assert should_perform_startup_reconcile(cfg, is_live=True, args=args) is False


def test_loop_interval_seconds() -> None:
    assert loop_interval_seconds({"runtime": {"loop_seconds": 7}}) == 7
    assert loop_interval_seconds({"runtime": {"loop_seconds": 0}}) == 20


def test_resolve_status_price_falls_back() -> None:
    store = _DummyStore()
    logger = _DummyLogger()
    price = resolve_status_price(
        {"simulation": {"mock_price_brl": 5.2}},
        _RaisingExchange(),
        store,
        logger,
        fallback_price_fn=lambda cfg: 4.99,
    )
    assert price == 4.99
    assert store.events[0][1] == "status_price_fallback"
    assert logger.warning_calls[0][0] == "status_price_fallback"


def test_resolve_status_price_uses_exchange() -> None:
    store = _DummyStore()
    logger = _DummyLogger()
    assert (
        resolve_status_price(
            {"simulation": {"mock_price_brl": 5.2}},
            _OkExchange(),
            store,
            logger,
            fallback_price_fn=lambda cfg: 4.99,
        )
        == 5.25
    )
    assert store.events == []


def test_build_healthcheck_payload_contains_status(tmp_path) -> None:
    from smartcrypto.state.store import StateStore

    db_path = tmp_path / "health.sqlite"
    store = StateStore(str(db_path))
    payload = build_healthcheck_payload(
        {
            "storage": {"db_path": str(db_path)},
            "execution": {"mode": "paper"},
            "market": {"timeframe": "1m"},
        },
        store,
    )
    assert "status" in payload


def test_run_once_cycle_resets_errors_and_persists() -> None:
    store = _DummyStore()
    logger = _DummyLogger()
    persisted: list[dict] = []

    result = run_once_cycle(
        {"runtime": {}},
        store,
        _OkExchange(),
        logger,
        tick_fn=lambda cfg, s, e: {"price_brl": 5.1, "equity_brl": 101.0},
        persist_runtime_state_fn=lambda cfg, e, status: persisted.append(status),
    )

    assert result["price_brl"] == 5.1
    assert store.flags["consecutive_error_count"] == 0
    assert persisted and persisted[0]["equity_brl"] == 101.0
    assert logger.info_calls[0][0] == "tick_once_ok"
