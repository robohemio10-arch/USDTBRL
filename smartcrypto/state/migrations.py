from __future__ import annotations

import sqlite3

MIGRATIONS: list[tuple[str, str]] = [
    (
        "0001_initial_schema",
        """
        create table if not exists schema_migrations (
            id integer primary key autoincrement,
            name text not null unique,
            applied_at text not null default current_timestamp
        );

        create table if not exists bot_state (
            key text primary key,
            value text not null
        );

        create table if not exists positions (
            id integer primary key autoincrement,
            status text not null default 'flat',
            qty_usdt real not null default 0,
            brl_spent real not null default 0,
            avg_price_brl real not null default 0,
            realized_pnl_brl real not null default 0,
            unrealized_pnl_brl real not null default 0,
            tp_price_brl real not null default 0,
            stop_price_brl real not null default 0,
            safety_count integer not null default 0,
            regime text not null default 'sideways',
            trailing_active integer not null default 0,
            trailing_anchor_brl real not null default 0,
            updated_at text not null default ''
        );

        create table if not exists planned_orders (
            id integer primary key autoincrement,
            side text,
            order_type text,
            price_brl real,
            qty_usdt real,
            brl_value real,
            reason text,
            status text,
            updated_at text
        );

        create table if not exists pending_orders (
            id integer primary key autoincrement,
            side text,
            order_type text,
            price_brl real,
            qty_usdt real,
            brl_value real,
            reason text,
            status text,
            updated_at text
        );

        create table if not exists order_events (
            id integer primary key autoincrement,
            bot_order_id text not null,
            parent_bot_order_id text,
            exchange_order_id text,
            client_order_id text,
            side text,
            order_type text,
            state text,
            reason text,
            price_brl real,
            qty_usdt real,
            executed_qty_usdt real,
            brl_value real,
            source text,
            note text,
            payload text,
            event_time text not null
        );

        create index if not exists idx_order_events_bot_order_id on order_events(bot_order_id);
        create index if not exists idx_order_events_exchange_order_id on order_events(exchange_order_id);
        create index if not exists idx_order_events_event_time on order_events(event_time);

        create table if not exists safety_ladder (
            id integer primary key autoincrement,
            step_index integer,
            trigger_price_brl real,
            order_brl real,
            expected_qty_usdt real,
            status text
        );

        create table if not exists trades (
            id integer primary key autoincrement,
            created_at text,
            side text,
            price_brl real,
            qty_usdt real,
            brl_value real,
            fee_brl real,
            reason text,
            mode text,
            regime text
        );

        create table if not exists cycles (
            id integer primary key autoincrement,
            opened_at text,
            closed_at text,
            regime text,
            entry_price_brl real,
            exit_price_brl real,
            qty_usdt real,
            brl_spent real,
            brl_received real,
            pnl_brl real,
            pnl_pct real,
            safety_count integer,
            exit_reason text,
            status text
        );

        create table if not exists snapshots (
            id integer primary key autoincrement,
            ts text,
            last_price_brl real,
            equity_brl real,
            cash_brl real,
            pos_value_brl real,
            realized_pnl_brl real,
            unrealized_pnl_brl real,
            drawdown_pct real,
            regime text,
            meta_json text
        );

        create table if not exists bot_events (
            id integer primary key autoincrement,
            ts text,
            level text,
            event text,
            details_json text
        );

        create table if not exists regime_observations (
            id integer primary key autoincrement,
            ts text,
            regime text,
            score real,
            features_json text
        );

        create table if not exists research_runs (
            id integer primary key autoincrement,
            ts text,
            run_type text,
            name text,
            params_json text,
            results_json text
        );
        """,
    ),
    (
        "0002_live_runtime_hardening",
        """
        create table if not exists reconciliation_audit (
            id integer primary key autoincrement,
            ts text not null,
            action text not null,
            local_status text,
            local_qty_usdt real,
            exchange_qty_usdt real,
            exchange_open_orders integer,
            details_json text
        );

        create table if not exists order_dispatch_locks (
            bot_order_id text primary key,
            side text,
            reason text,
            order_type text,
            client_order_id text,
            status text,
            requested_price_brl real,
            requested_qty_usdt real,
            requested_brl_value real,
            created_at text not null,
            updated_at text not null,
            details_json text
        );

        create index if not exists idx_order_dispatch_locks_status on order_dispatch_locks(status);
        create index if not exists idx_order_dispatch_locks_updated_at on order_dispatch_locks(updated_at);
        """,
    ),
    (
        "0003_trade_audit_and_identity",
        """
        alter table trades add column bot_order_id text;
        alter table trades add column client_order_id text;
        alter table trades add column exchange_order_id text;
        alter table trades add column run_id text;
        alter table trades add column source text;
        create unique index if not exists idx_trades_bot_order_id_unique on trades(bot_order_id);
        create index if not exists idx_trades_client_order_id on trades(client_order_id);
        create index if not exists idx_trades_exchange_order_id on trades(exchange_order_id);
        """,
    ),
]


def apply_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        create table if not exists schema_migrations (
            id integer primary key autoincrement,
            name text not null unique,
            applied_at text not null default current_timestamp
        )
        """
    )
    applied = {
        row[0]
        for row in conn.execute("select name from schema_migrations order by id asc").fetchall()
    }
    for name, sql in MIGRATIONS:
        if name in applied:
            continue
        try:
            conn.executescript(sql)
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            if "duplicate column name" not in message and "already exists" not in message:
                raise
        conn.execute("insert into schema_migrations(name) values (?)", (name,))
