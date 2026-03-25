from smartcrypto.execution.recovery import inflight_order_lock_seconds


def test_inflight_order_lock_seconds_has_floor() -> None:
    cfg = {"runtime": {"inflight_order_lock_seconds": 1}}

    assert inflight_order_lock_seconds(cfg) == 10
