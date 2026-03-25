from __future__ import annotations

import json

from smartcrypto.common.constants import DEFAULT_CONFIG_PATH
from smartcrypto.execution.trading import (
    execute_buy as execution_execute_buy,
    execute_sell as execution_execute_sell,
    record_execution_report as execution_record_execution_report,
    record_simulated_execution as execution_record_simulated_execution,
)
from smartcrypto.runtime.tick_cycle import tick as runtime_tick
from smartcrypto.runtime.compat import (
    backtest,
    circuit_breaker_cooldown_seconds,
    circuit_breaker_max_errors,
    fallback_price_brl,
    is_live_mode,
    monte_carlo,
    optimize,
    persist_dashboard_runtime_state,
    reconcile_live_exchange_state,
    recover_dispatch_locks,
    set_reentry_block,
    status_payload,
    walk_forward,
)
from smartcrypto.runtime.lifecycle import (
    build_cli_parser,
    build_healthcheck_payload,
    loop_interval_seconds,
    resolve_status_price,
    run_loop,
    run_once_cycle,
    should_perform_startup_reconcile,
)
from smartcrypto.runtime.orchestrator import bootstrap_runtime_services, run_startup_reconcile

BUILD_ID = "phase-d-2026-03-19-01"

from smartcrypto.runtime.compat import *  # noqa: F401,F403,E402


def record_execution_report(**kwargs):
    return execution_record_execution_report(**kwargs)


def record_simulated_execution(**kwargs):
    return execution_record_simulated_execution(**kwargs)


def execute_buy(**kwargs):
    return execution_execute_buy(**kwargs)


def execute_sell(**kwargs):
    return execution_execute_sell(**kwargs)


def tick(cfg, store, exchange):
    return runtime_tick(cfg, store, exchange)


def main() -> None:
    parser = build_cli_parser(str(DEFAULT_CONFIG_PATH))
    args = parser.parse_args()

    services = bootstrap_runtime_services(args.config)
    context = services.context
    cfg = context.config
    store = context.store
    exchange = context.exchange
    logger = services.logger

    if should_perform_startup_reconcile(cfg, is_live=is_live_mode(cfg), args=args):
        run_startup_reconcile(
            context,
            logger,
            build_id=BUILD_ID,
            recover_dispatch_locks_fn=recover_dispatch_locks,
            reconcile_live_exchange_state_fn=reconcile_live_exchange_state,
        )

    if args.status:
        price = resolve_status_price(
            cfg,
            exchange,
            store,
            logger,
            fallback_price_fn=fallback_price_brl,
        )
        print(json.dumps(status_payload(store, price, cfg), indent=2, ensure_ascii=False))
        return
    if args.healthcheck:
        print(json.dumps(build_healthcheck_payload(cfg, store), indent=2, ensure_ascii=False))
        return
    if args.backtest:
        print(json.dumps(backtest(cfg, exchange, store), indent=2, ensure_ascii=False))
        return
    if args.monte_carlo:
        print(json.dumps(monte_carlo(cfg, exchange, store), indent=2, ensure_ascii=False))
        return
    if args.optimize:
        print(json.dumps(optimize(cfg, exchange, store), indent=2, ensure_ascii=False))
        return
    if args.walk_forward:
        print(json.dumps(walk_forward(cfg, exchange, store), indent=2, ensure_ascii=False))
        return
    if args.once:
        result = run_once_cycle(
            cfg,
            store,
            exchange,
            logger,
            tick_fn=tick,
            persist_runtime_state_fn=persist_dashboard_runtime_state,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    loop_seconds = loop_interval_seconds(cfg)
    store.add_event(
        "INFO",
        "bot_started",
        {"config": args.config, "loop_seconds": loop_seconds, "build_id": BUILD_ID},
    )
    logger.info("bot_started", config=args.config, loop_seconds=loop_seconds, build_id=BUILD_ID)
    run_loop(
        cfg,
        store,
        exchange,
        logger,
        tick_fn=tick,
        persist_runtime_state_fn=persist_dashboard_runtime_state,
        circuit_breaker_max_errors_fn=circuit_breaker_max_errors,
        circuit_breaker_cooldown_seconds_fn=circuit_breaker_cooldown_seconds,
        set_reentry_block_fn=set_reentry_block,
    )


if __name__ == "__main__":
    main()
