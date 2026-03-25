from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import streamlit.components.v1 as components

from smartcrypto.common.constants import DEFAULT_CONFIG_PATH
from smartcrypto.app import session as app_session
from smartcrypto.app import styles as app_styles
from smartcrypto.app.components import position_card, refresh_control
from smartcrypto.app.pages import (
    banco_dados as banco_dados_page,
    configuracao as configuracao_page,
    mercado as mercado_page,
    notificacoes as notificacoes_page,
    operacoes as operacoes_page,
    resumo as resumo_page,
    saude_sistema as saude_sistema_page,
)
from smartcrypto.common.env import (
    dotenv_path_from_cfg,
    load_dotenv_map,
    resolve_env,
    save_dotenv_map,
)
from smartcrypto.config import load_config, save_config
from smartcrypto.infra.notifications import NtfyClient
from smartcrypto.runtime.cache import (
    dashboard_cache_dir,
    market_cache_file,
    runtime_status_cache_file,
)
from smartcrypto.state.portfolio import Portfolio
from smartcrypto.state.position_manager import PositionManager
from smartcrypto.state.store import StateStore

st.set_page_config(
    page_title="SmartCrypto Dashboard", layout="wide", initial_sidebar_state="expanded"
)

APP_TITLE = app_styles.APP_TITLE
APP_SUBTITLE = app_styles.APP_SUBTITLE
AUTO_REFRESH_PAGES = app_session.AUTO_REFRESH_PAGES
ACTIVE_DISPATCH_LOCK_STATUSES = {"pending_submit", "submit_unknown", "submitted", "recovered_open"}


def inject_styles() -> None:
    app_styles.inject_styles()


def tone_for_bool(flag: bool, invert: bool = False) -> str:
    if invert:
        return "bad" if flag else "good"
    return "good" if flag else "neutral"


def chip_html(label: str, value: str, tone: str = "neutral") -> str:
    return f'<span class="sc-chip {tone}"><span>{label}</span><span>{value}</span></span>'


def root_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def config_path() -> Path:
    primary = root_dir() / DEFAULT_CONFIG_PATH
    legacy = root_dir() / "config.yml"
    return primary if primary.exists() else legacy


def get_query_value(name: str, default: str) -> str:
    try:
        value = st.query_params.get(name, default)
        if isinstance(value, list):
            return str(value[0]) if value else str(default)
        return str(value or default)
    except Exception:
        return str(default)


def set_query_value(name: str, value: str) -> None:
    try:
        st.query_params[name] = str(value)
    except Exception:
        pass


def market_symbol_exchange(cfg: dict[str, Any]) -> str:
    return cache_symbol_token(str(cfg.get("market", {}).get("symbol", "USDT/BRL")))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except Exception:
        return default


def parse_datetime_series(values: Any) -> pd.Series:
    series = pd.Series(values)
    try:
        parsed = pd.to_datetime(series, format="ISO8601", errors="coerce", utc=True)
    except Exception:
        parsed = pd.to_datetime(series, errors="coerce", utc=True)
    if parsed.isna().any():
        try:
            fallback = pd.to_datetime(
                series[parsed.isna()], format="mixed", errors="coerce", utc=True
            )
            parsed.loc[parsed.isna()] = fallback
        except Exception:
            fallback = pd.to_datetime(series[parsed.isna()], errors="coerce", utc=True)
            parsed.loc[parsed.isna()] = fallback
    return parsed


def load_cfg() -> dict[str, Any]:
    path = config_path()
    return load_config(path)


def save_cfg(cfg: dict[str, Any]) -> None:
    save_config(config_path(), cfg)


def write_market_cache_df(cfg: dict[str, Any], interval: str, df: pd.DataFrame) -> Path:
    path = market_cache_file(cfg, interval)
    out = df.copy()
    if out.empty:
        payload = {
            "saved_at": pd.Timestamp.utcnow().isoformat(),
            "symbol": str(cfg.get("market", {}).get("symbol", "")),
            "interval": interval,
            "rows": [],
        }
    else:
        if "ts" in out.columns:
            out["ts"] = pd.to_datetime(out["ts"], errors="coerce", utc=True).dt.strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        for col in ["open", "high", "low", "close", "volume"]:
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce")
        payload = {
            "saved_at": pd.Timestamp.utcnow().isoformat(),
            "symbol": str(cfg.get("market", {}).get("symbol", "")),
            "interval": interval,
            "rows": out[
                [c for c in ["ts", "open", "high", "low", "close", "volume"] if c in out.columns]
            ].to_dict(orient="records"),
        }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _fetch_ohlcv_history_public(cfg: dict[str, Any], interval: str, days: int = 30) -> pd.DataFrame:
    base_url = str(cfg.get("exchange", {}).get("base_url", "https://api.binance.com")).rstrip("/")
    symbol = market_symbol_exchange(cfg)
    end_ts = (
        pd.Timestamp.utcnow().tz_localize("UTC")
        if pd.Timestamp.utcnow().tzinfo is None
        else pd.Timestamp.utcnow()
    )
    start_ts = end_ts - pd.Timedelta(days=int(days))
    rows: list[dict[str, Any]] = []
    start_ms = int(start_ts.timestamp() * 1000)
    end_ms = int(end_ts.timestamp() * 1000)
    session = requests.Session()
    while start_ms < end_ms:
        params: dict[str, str | int | float] = {
            "symbol": str(symbol),
            "interval": str(interval),
            "limit": 1000,
            "startTime": start_ms,
            "endTime": end_ms,
        }
        resp = session.get(
            f"{base_url}/api/v3/klines",
            params=params,
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
        if not payload:
            break
        last_open = None
        for row in payload:
            last_open = int(row[0])
            rows.append(
                {
                    "ts": pd.to_datetime(int(row[0]), unit="ms", utc=True),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                }
            )
        if last_open is None:
            break
        next_start = last_open + 1
        if next_start <= start_ms:
            break
        start_ms = next_start
        if len(payload) < 1000:
            break
    if not rows:
        return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows).drop_duplicates(subset=["ts"]).sort_values("ts")
    return df


def ensure_market_cache_interval(
    cfg: dict[str, Any], interval_code: str, *, force: bool = False
) -> tuple[pd.DataFrame, str]:
    target_code = "1d" if interval_code in {"7d", "30d"} else interval_code
    cache_path = market_cache_file(cfg, target_code)
    df = load_market_cache_df(str(cache_path))
    if not force and not df.empty:
        return df, f"cache local: {cache_path.name}"
    try:
        df = _fetch_ohlcv_history_public(cfg, target_code, days=30)
        if not df.empty:
            write_market_cache_df(cfg, target_code, df)
            st.cache_data.clear()
            return df, f"cache atualizado: {cache_path.name}"
    except Exception as exc:
        st.warning(f"Não foi possível baixar candles de {target_code} agora: {exc}")
    return load_market_cache_df(str(cache_path)), f"cache local: {cache_path.name}"


def open_orders_cache_file(cfg: dict[str, Any]) -> Path:
    return (
        dashboard_cache_dir(cfg)
        / f"open_orders_{cache_symbol_token(cfg.get('market', {}).get('symbol', 'USDTBRL'))}.json"
    )


def read_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}
        return cast(dict[str, Any], payload)
    except Exception:
        return {}


@st.cache_data(ttl=5, show_spinner=False)
def load_market_cache_df(path_str: str) -> pd.DataFrame:
    path = Path(path_str)
    payload = read_json_file(path)
    rows = payload.get("rows", [])
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    rename_map = {
        "open_price": "open",
        "high_price": "high",
        "low_price": "low",
        "close_price": "close",
        "base_volume": "volume",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    if "ts" not in df.columns and "open_time" in df.columns:
        df["ts"] = df["open_time"]
    df["ts"] = parse_datetime_series(df.get("ts"))
    df = df.dropna(subset=["ts"]).drop_duplicates(subset=["ts"]).sort_values("ts")
    for col in ["open", "high", "low", "close", "volume"]:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df[["ts", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def db_path_from_cfg(cfg: dict[str, Any]) -> Path:
    raw = str(
        cfg.get("storage", {}).get("db_path", "data/usdtbrl_live.sqlite")
        or "data/usdtbrl_live.sqlite"
    )
    path = Path(raw)
    if not path.is_absolute():
        path = root_dir() / path
    return path


def state_store(cfg: dict[str, Any]) -> StateStore:
    return StateStore(str(db_path_from_cfg(cfg)))


def position_manager(cfg: dict[str, Any]) -> PositionManager:
    return PositionManager(state_store(cfg))


def portfolio(cfg: dict[str, Any]) -> Portfolio:
    return Portfolio(state_store(cfg), position_manager=position_manager(cfg))


def query_df(cfg: dict[str, Any], sql: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    path = db_path_from_cfg(cfg)
    if not path.exists():
        return pd.DataFrame()
    with sqlite3.connect(path) as conn:
        try:
            return pd.read_sql_query(sql, conn, params=params)
        except Exception:
            return pd.DataFrame()


def list_tables(cfg: dict[str, Any]) -> list[str]:
    path = db_path_from_cfg(cfg)
    if not path.exists():
        return []
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "select name from sqlite_master where type='table' order by name"
        ).fetchall()
    return [row[0] for row in rows]


def read_table(cfg: dict[str, Any], table: str, limit: int = 200) -> pd.DataFrame:
    if table not in list_tables(cfg):
        return pd.DataFrame()
    sql = f"select * from {table} order by rowid desc limit ?"
    return query_df(cfg, sql, (int(limit),))



def load_runtime_status(cfg: dict[str, Any]) -> dict[str, Any]:
    payload = read_json_file(runtime_status_cache_file(cfg))
    status_obj = payload.get("status", {}) if isinstance(payload, dict) else {}
    if isinstance(status_obj, dict) and status_obj:
        return cast(dict[str, Any], status_obj)
    store = state_store(cfg)
    runtime_portfolio = portfolio(cfg).runtime_view(
        mark_price_brl=0.0,
        initial_cash_brl=safe_float(cfg.get("portfolio", {}).get("initial_cash_brl", 0.0)),
    )
    return {
        "time": "",
        "price_brl": 0.0,
        "paused": bool(store.get_flag("paused", False)),
        "position": runtime_portfolio.position,
        "portfolio": {
            "cash_brl": runtime_portfolio.cash_brl,
            "equity_brl": runtime_portfolio.equity_brl,
            "position_notional_brl": runtime_portfolio.position_notional_brl,
            "invested_brl": runtime_portfolio.invested_brl,
            "unrealized_pnl_brl": runtime_portfolio.unrealized_pnl_brl,
            "realized_pnl_brl": runtime_portfolio.realized_pnl_brl,
            "drawdown_pct": runtime_portfolio.drawdown_pct,
        },
        "cash_brl": runtime_portfolio.cash_brl,
        "equity_brl": runtime_portfolio.equity_brl,
        "flags": {
            "force_sell_requested": bool(store.get_flag("force_sell_requested", False)),
            "reset_cycle_requested": bool(store.get_flag("reset_cycle_requested", False)),
            "reentry_block_until": store.get_flag("reentry_block_until", 0),
            "reentry_remaining_seconds": 0,
            "reentry_price_below": store.get_flag("reentry_price_below", 0.0),
            "live_reconcile_required": bool(store.get_flag("live_reconcile_required", False)),
            "consecutive_error_count": safe_int(store.get_flag("consecutive_error_count", 0)),
        },
        "live_hardening": {
            "active_dispatch_locks": [],
        },
    }


def load_open_orders_cache(cfg: dict[str, Any]) -> pd.DataFrame:
    payload = read_json_file(open_orders_cache_file(cfg))
    rows = payload.get("orders", []) if isinstance(payload, dict) else []
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    if "updated_at" in df.columns:
        df["updated_at"] = pd.to_datetime(df["updated_at"], errors="coerce", utc=True)
    return df


def format_money(value: Any) -> str:
    number = safe_float(value)
    return f"R$ {number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_qty(value: Any) -> str:
    return f"{safe_float(value):,.4f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_dt_local(value: Any) -> str:
    try:
        ts = pd.to_datetime(value, errors="coerce", utc=True)
        if pd.isna(ts):
            return "—"
        if not isinstance(ts, pd.Timestamp):
            return "—"
        local_tz = datetime.now().astimezone().tzinfo
        return str(ts.tz_convert(local_tz).strftime("%d/%m/%Y %H:%M:%S"))
    except Exception:
        return "—"


def now_local_text() -> str:
    return datetime.now().astimezone().strftime("%d/%m/%Y %H:%M:%S")


def infer_bot_started_at(cfg: dict[str, Any], status: dict[str, Any]) -> str:
    events = bot_events_df(cfg, limit=5000)
    if not events.empty:
        if "event_type" in events.columns:
            started = events[events["event_type"].astype(str).str.lower() == "bot_started"]
            if not started.empty and "ts" in started.columns:
                ts = started.sort_values("ts").iloc[-1]["ts"]
                return format_dt_local(ts)
    candidates: list[Any] = []
    snap = snapshots_df(cfg, limit=5000)
    if not snap.empty and "ts" in snap.columns:
        candidates.append(snap["ts"].min())
    trades = trades_df(cfg, limit=5000)
    if not trades.empty and "created_at" in trades.columns:
        candidates.append(trades["created_at"].min())
    cycles = cycles_df(cfg, limit=5000)
    if not cycles.empty:
        if "opened_at" in cycles.columns:
            candidates.append(cycles["opened_at"].min())
        if "closed_at" in cycles.columns:
            candidates.append(cycles["closed_at"].min())
    pos = status.get("position", {}) or {}
    if pos.get("updated_at"):
        candidates.append(pos.get("updated_at"))
    candidates = [c for c in candidates if not pd.isna(parse_datetime_series([c]).iloc[0])]
    if not candidates:
        return "—"
    return format_dt_local(min(parse_datetime_series(candidates)))


def render_time_cards(cfg: dict[str, Any], status: dict[str, Any]) -> None:
    pos = status.get("position", {}) or {}
    last_update = format_dt_local(status.get("time") or pos.get("updated_at"))
    started_at = infer_bot_started_at(cfg, status)

    cols = st.columns(3)
    with cols[0]:
        components.html(
            """
            <div id="sc-live-clock-card" style="background:linear-gradient(180deg,#d7dbe0 0%,#c7ccd4 100%);border:1px solid #b0b7c3;border-radius:14px;padding:0.8rem 0.95rem;box-shadow:0 6px 16px rgba(15,23,42,.10);font-family:Arial,sans-serif;color:#111827;">
                <div style="font-size:0.98rem;font-weight:900;color:#374151;margin-bottom:0.25rem;">Hora local exata</div>
                <div id="sc-live-clock-value" style="font-size:1.35rem;font-weight:900;color:#111827;">--:--:--</div>
            </div>
            <script>
            const root = window.parent.document;
            function pad(v){ return String(v).padStart(2, "0"); }
            function tick(){
                const now = new Date();
                const dd = pad(now.getDate());
                const mm = pad(now.getMonth()+1);
                const yyyy = now.getFullYear();
                const hh = pad(now.getHours());
                const mi = pad(now.getMinutes());
                const ss = pad(now.getSeconds());
                const el = document.getElementById("sc-live-clock-value");
                if (el){ el.textContent = `${dd}/${mm}/${yyyy} ${hh}:${mi}:${ss}`; }
            }
            tick();
            setInterval(tick, 1000);
            </script>
            """,
            height=100,
        )
    card_items = [
        ("Última atualização do bot", last_update),
        ("Início do bot", started_at),
    ]
    for col, (label, value) in zip(cols[1:], card_items):
        with col:
            st.markdown(
                f"""
                <div class="sc-time-card">
                    <div class="sc-time-label"><strong>{label}</strong></div>
                    <div class="sc-time-value">{value}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def inject_auto_refresh(interval_ms: int = 60000, *, enabled: bool = True) -> None:
    if not enabled:
        return
    components.html(
        f"""
        <script>
        const key = "smartcrypto-dashboard-auto-refresh";
        const timerKey = "smartcrypto-dashboard-auto-refresh-timer";
        const now = Date.now();
        const last = Number(sessionStorage.getItem(key) || "0");
        const remaining = (!last || (now - last) >= {int(interval_ms)}) ? {int(interval_ms)} : Math.max(1000, {int(interval_ms)} - (now - last));
        const oldTimer = window.parent[timerKey];
        if (oldTimer) clearTimeout(oldTimer);
        window.parent[timerKey] = setTimeout(() => {{
            sessionStorage.setItem(key, String(Date.now()));
            window.parent.location.reload();
        }}, remaining);
        </script>
        """,
        height=0,
        width=0,
    )


def chart_interval_timedelta(interval_label: str, df: pd.DataFrame | None = None) -> pd.Timedelta:
    code = str(interval_map().get(interval_label, {}).get("code", "")).lower()
    mapping = {
        "1m": pd.Timedelta(minutes=1),
        "5m": pd.Timedelta(minutes=5),
        "15m": pd.Timedelta(minutes=15),
        "1h": pd.Timedelta(hours=1),
        "12h": pd.Timedelta(hours=12),
        "1d": pd.Timedelta(days=1),
        "7d": pd.Timedelta(days=7),
        "30d": pd.Timedelta(days=30),
    }
    if code in mapping:
        return mapping[code]
    if df is not None and not df.empty and "ts" in df.columns and len(df) > 1:
        diffs = pd.Series(df["ts"]).sort_values().diff().dropna()
        if not diffs.empty:
            return diffs.median()
    return pd.Timedelta(minutes=1)


def execution_markers_df(cfg: dict[str, Any], limit: int = 1000) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    trades = trades_df(cfg, limit=limit)
    if not trades.empty and {"created_at", "side", "price_brl"}.issubset(trades.columns):
        trade_cols = [
            c
            for c in [
                "created_at",
                "side",
                "price_brl",
                "qty_usdt",
                "brl_value",
                "fee_brl",
                "execution_mode",
            ]
            if c in trades.columns
        ]
        trade_df = trades[trade_cols].copy()
        trade_df["source"] = "trade"
        frames.append(trade_df)

    if "order_events" in list_tables(cfg):
        order_df = query_df(
            cfg,
            """
            select
                event_time as created_at,
                side,
                price_brl,
                coalesce(executed_qty_usdt, qty_usdt) as qty_usdt,
                brl_value,
                note
            from order_events
            where lower(state) in ('filled', 'partially_filled')
            order by id desc
            limit ?
            """,
            (int(limit),),
        )
        if not order_df.empty and {"created_at", "side", "price_brl"}.issubset(order_df.columns):
            for col in ["price_brl", "qty_usdt", "brl_value"]:
                if col in order_df.columns:
                    order_df[col] = pd.to_numeric(order_df[col], errors="coerce").fillna(0.0)
            order_df["created_at"] = parse_datetime_series(order_df["created_at"])
            order_df["fee_brl"] = 0.0
            order_df["execution_mode"] = "order_event"
            order_df["source"] = "order_event"
            order_df = order_df[
                [
                    c
                    for c in [
                        "created_at",
                        "side",
                        "price_brl",
                        "qty_usdt",
                        "brl_value",
                        "fee_brl",
                        "execution_mode",
                        "source",
                    ]
                    if c in order_df.columns
                ]
            ]
            frames.append(order_df)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    if "created_at" in combined.columns:
        combined["created_at"] = parse_datetime_series(combined["created_at"])
    for col in ["price_brl", "qty_usdt", "brl_value", "fee_brl"]:
        if col in combined.columns:
            combined[col] = pd.to_numeric(combined[col], errors="coerce").fillna(0.0)
    combined = combined.dropna(subset=["created_at", "price_brl"])
    dedupe_cols = [
        c for c in ["created_at", "side", "price_brl", "qty_usdt"] if c in combined.columns
    ]
    if dedupe_cols:
        combined = combined.drop_duplicates(subset=dedupe_cols, keep="first")
    return combined.sort_values("created_at").reset_index(drop=True)


def filter_executions_for_chart_window(
    executions: pd.DataFrame, df: pd.DataFrame, interval_label: str
) -> pd.DataFrame:
    if (
        executions.empty
        or df.empty
        or "created_at" not in executions.columns
        or "ts" not in df.columns
    ):
        return pd.DataFrame()
    delta = chart_interval_timedelta(interval_label, df)
    start_ts = pd.to_datetime(df["ts"].min(), utc=True) - delta
    end_ts = pd.to_datetime(df["ts"].max(), utc=True) + delta
    visible = executions[
        (executions["created_at"] >= start_ts) & (executions["created_at"] <= end_ts)
    ].copy()
    return visible.sort_values("created_at").reset_index(drop=True)


def interval_label_from_code(code: str) -> str:
    normalized = str(code or "1h").lower()
    for label, meta in interval_map().items():
        if str(meta.get("code", "")).lower() == normalized:
            return label
    return "1 hora"


def build_market_figure(
    df: pd.DataFrame,
    trades: pd.DataFrame,
    position: dict[str, Any],
    title: str,
    show_tp_stop: bool = False,
    white_theme: bool = False,
    interval_label: str = "1 minuto",
) -> go.Figure:
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        row_heights=[0.86, 0.14],
    )
    fig.add_trace(
        go.Candlestick(
            x=df["ts"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="Preço",
            increasing_line_color="#0ECB81",
            decreasing_line_color="#F6465D",
            increasing_fillcolor="#0ECB81",
            decreasing_fillcolor="#F6465D",
            whiskerwidth=0.6,
        ),
        row=1,
        col=1,
    )
    volume_colors = ["#0ECB81" if c >= o else "#F6465D" for o, c in zip(df["open"], df["close"])]
    fig.add_trace(
        go.Bar(
            x=df["ts"],
            y=df["volume"],
            name="Volume",
            marker_color=volume_colors,
            opacity=0.42,
        ),
        row=2,
        col=1,
    )

    visible_low = float(pd.to_numeric(df["low"], errors="coerce").min())
    visible_high = float(pd.to_numeric(df["high"], errors="coerce").max())
    visible_span = max(visible_high - visible_low, max(abs(visible_high), 1.0) * 0.0025)
    price_pad = max(visible_span * 0.32, max(abs(visible_high), 1.0) * 0.0018)

    avg_price = safe_float(position.get("avg_price_brl", 0.0))
    tp_price = safe_float(position.get("tp_price_brl", 0.0))
    stop_price = safe_float(position.get("stop_price_brl", 0.0))
    overlay_prices: list[float] = []
    if avg_price > 0:
        overlay_prices.append(avg_price)
    if show_tp_stop and tp_price > 0 and tp_price <= visible_high + (visible_span * 2.0):
        overlay_prices.append(tp_price)
    if show_tp_stop and stop_price > 0 and stop_price >= visible_low - (visible_span * 2.0):
        overlay_prices.append(stop_price)

    y_min = visible_low - price_pad
    y_max = visible_high + price_pad
    if overlay_prices:
        y_min = min(y_min, min(overlay_prices) - (price_pad * 0.40))
        y_max = max(y_max, max(overlay_prices) + (price_pad * 0.40))

    if avg_price > 0:
        fig.add_hline(
            y=avg_price,
            line_dash="solid",
            line_color="#3B82F6",
            annotation_text="Preço médio",
            row=1,
            col=1,
        )
    if show_tp_stop and tp_price > 0 and tp_price <= y_max:
        fig.add_hline(
            y=tp_price, line_dash="solid", line_color="#0ECB81", annotation_text="TP", row=1, col=1
        )
    if show_tp_stop and stop_price > 0 and stop_price >= y_min:
        fig.add_hline(
            y=stop_price,
            line_dash="solid",
            line_color="#F6465D",
            annotation_text="Stop",
            row=1,
            col=1,
        )

    trade_window = filter_executions_for_chart_window(trades, df, interval_label)
    if not trade_window.empty and {"created_at", "price_brl", "side"}.issubset(
        trade_window.columns
    ):
        buy_df = trade_window[trade_window["side"].astype(str).str.lower() == "buy"]
        sell_df = trade_window[trade_window["side"].astype(str).str.lower() == "sell"]
        if not buy_df.empty:
            fig.add_trace(
                go.Scatter(
                    x=buy_df["created_at"],
                    y=buy_df["price_brl"],
                    mode="markers+text",
                    text=["B"] * len(buy_df),
                    textposition="top center",
                    textfont=dict(size=11, color="#065F46"),
                    name="Compras",
                    marker=dict(
                        symbol="triangle-up",
                        size=18,
                        color="#0ECB81",
                        line=dict(color="#064E3B", width=1.2),
                    ),
                    hovertemplate="Compra<br>%{x}<br>Preço: R$ %{y:.4f}<extra></extra>",
                ),
                row=1,
                col=1,
            )
        if not sell_df.empty:
            fig.add_trace(
                go.Scatter(
                    x=sell_df["created_at"],
                    y=sell_df["price_brl"],
                    mode="markers+text",
                    text=["S"] * len(sell_df),
                    textposition="bottom center",
                    textfont=dict(size=11, color="#991B1B"),
                    name="Vendas",
                    marker=dict(
                        symbol="triangle-down",
                        size=18,
                        color="#F6465D",
                        line=dict(color="#7F1D1D", width=1.2),
                    ),
                    hovertemplate="Venda<br>%{x}<br>Preço: R$ %{y:.4f}<extra></extra>",
                ),
                row=1,
                col=1,
            )

    if white_theme:
        fig.update_layout(
            template="plotly_white",
            height=660,
            margin=dict(l=10, r=10, t=35, b=10),
            title=title,
            xaxis_rangeslider_visible=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            font=dict(color="#111827"),
            hovermode="x unified",
        )
        fig.update_xaxes(showgrid=True, gridcolor="#e5e7eb", zeroline=False)
        fig.update_yaxes(showgrid=True, gridcolor="#e5e7eb", zeroline=False)
    else:
        fig.update_layout(
            template="plotly_dark",
            height=660,
            margin=dict(l=10, r=10, t=35, b=10),
            title=title,
            xaxis_rangeslider_visible=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            paper_bgcolor="#0b1220",
            plot_bgcolor="#0b1220",
            hovermode="x unified",
        )

    fig.update_xaxes(range=[df["ts"].min(), df["ts"].max()], showspikes=True, spikemode="across")
    fig.update_yaxes(title_text="Preço BRL", row=1, col=1, range=[y_min, y_max])
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    return fig


def render_position_table(status: dict[str, Any]) -> None:
    position_card.render(
        status,
        format_money=format_money,
        safe_float=safe_float,
        safe_int=safe_int,
    )


def render_bank_evolution_chart(cfg: dict[str, Any]) -> None:
    st.markdown("#### Evolução da banca")
    initial_cash = safe_float(cfg.get("portfolio", {}).get("initial_cash_brl", 0.0))
    cycles = cycles_df(cfg, limit=5000)
    now_ts = pd.Timestamp.utcnow()
    if cycles.empty or "closed_at" not in cycles.columns or "pnl_brl" not in cycles.columns:
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=[now_ts],
                y=[initial_cash],
                mode="lines+markers",
                name="Banca",
                line=dict(color="#2563EB", width=3),
            )
        )
        fig.update_layout(
            template="plotly_dark",
            height=360,
            margin=dict(l=10, r=10, t=20, b=10),
            paper_bgcolor="#0b1220",
            plot_bgcolor="#0b1220",
        )
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        return

    closed = cycles.dropna(subset=["closed_at"]).sort_values("closed_at").copy()
    if closed.empty:
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=[now_ts],
                y=[initial_cash],
                mode="lines+markers",
                name="Banca",
                line=dict(color="#2563EB", width=3),
            )
        )
        fig.update_layout(
            template="plotly_dark",
            height=360,
            margin=dict(l=10, r=10, t=20, b=10),
            paper_bgcolor="#0b1220",
            plot_bgcolor="#0b1220",
        )
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        return

    closed["pnl_brl"] = pd.to_numeric(closed["pnl_brl"], errors="coerce").fillna(0.0)
    closed["bank_brl"] = initial_cash + closed["pnl_brl"].cumsum()
    bank_df = pd.concat(
        [
            pd.DataFrame({"closed_at": [closed["closed_at"].min()], "bank_brl": [initial_cash]}),
            closed[["closed_at", "bank_brl"]],
        ],
        ignore_index=True,
    )

    local_tz = datetime.now().astimezone().tzinfo
    daily = closed.copy()
    daily["local_day"] = daily["closed_at"].dt.tz_convert(local_tz).dt.floor("D")
    daily = daily.groupby("local_day", as_index=False)["pnl_brl"].sum()
    daily["label"] = daily["pnl_brl"].apply(format_money)

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(
            x=bank_df["closed_at"],
            y=bank_df["bank_brl"],
            mode="lines+markers",
            name="Banca",
            line=dict(color="#2563EB", width=3, shape="hv"),
            marker=dict(size=8, color="#2563EB"),
        ),
        secondary_y=False,
    )
    if not daily.empty:
        colors = ["#16A34A" if v >= 0 else "#DC2626" for v in daily["pnl_brl"]]
        fig.add_trace(
            go.Scatter(
                x=daily["local_day"],
                y=daily["pnl_brl"],
                mode="lines+markers+text",
                name="Lucro do dia",
                line=dict(color="#F59E0B", width=2, dash="dot"),
                marker=dict(size=20, color=colors, line=dict(color="#111827", width=1)),
                text=daily["label"],
                textposition="top center",
                textfont=dict(size=12, color="#E5E7EB"),
            ),
            secondary_y=True,
        )

    fig.update_layout(
        template="plotly_dark",
        height=380,
        margin=dict(l=10, r=10, t=20, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        paper_bgcolor="#0b1220",
        plot_bgcolor="#0b1220",
    )
    fig.update_yaxes(title_text="Banca (BRL)", secondary_y=False)
    fig.update_yaxes(title_text="Lucro do dia (BRL)", secondary_y=True)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def interval_map() -> dict[str, dict[str, Any]]:
    return {
        "1 minuto": {"code": "1m", "bars": 120},
        "5 minutos": {"code": "5m", "bars": 144},
        "15 minutos": {"code": "15m", "bars": 160},
        "1 hora": {"code": "1h", "bars": 120},
        "12 horas": {"code": "12h", "bars": 90},
        "24 horas": {"code": "1d", "bars": 60},
        "7 dias": {"code": "7d", "bars": 52},
        "1 mês": {"code": "30d", "bars": 24},
    }


def trades_df(cfg: dict[str, Any], limit: int = 500) -> pd.DataFrame:
    df = query_df(cfg, "select * from trades order by id desc limit ?", (int(limit),))
    if df.empty:
        return df
    for col in ["price_brl", "qty_usdt", "brl_value", "fee_brl"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    if "created_at" in df.columns:
        df["created_at"] = parse_datetime_series(df["created_at"])
    return df


def cycles_df(cfg: dict[str, Any], limit: int = 500) -> pd.DataFrame:
    df = query_df(cfg, "select * from cycles order by id desc limit ?", (int(limit),))
    if df.empty:
        return df
    for col in [
        "entry_price_brl",
        "exit_price_brl",
        "qty_usdt",
        "brl_spent",
        "brl_received",
        "pnl_brl",
        "pnl_pct",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    if "opened_at" in df.columns:
        df["opened_at"] = parse_datetime_series(df["opened_at"])
    if "closed_at" in df.columns:
        df["closed_at"] = parse_datetime_series(df["closed_at"])
    return df


def snapshots_df(cfg: dict[str, Any], limit: int = 1000) -> pd.DataFrame:
    df = query_df(cfg, "select * from snapshots order by id desc limit ?", (int(limit),))
    if df.empty:
        return df
    if "ts" in df.columns:
        df["ts"] = parse_datetime_series(df["ts"])
    for col in ["price_brl", "cash_brl", "equity_brl"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df.sort_values("ts")


def planned_orders_df(cfg: dict[str, Any], limit: int = 50) -> pd.DataFrame:
    if "planned_orders" in list_tables(cfg):
        df = query_df(cfg, "select * from planned_orders order by id desc limit ?", (int(limit),))
    elif "pending_orders" in list_tables(cfg):
        df = query_df(cfg, "select * from pending_orders order by id desc limit ?", (int(limit),))
    else:
        df = pd.DataFrame()
    if df.empty:
        return df
    for col in ["price_brl", "qty_usdt", "brl_value"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df


def order_states_df(cfg: dict[str, Any], limit: int = 100) -> pd.DataFrame:
    if "order_events" not in list_tables(cfg):
        return pd.DataFrame()
    sql = """
        with ranked as (
            select
                *,
                row_number() over (
                    partition by bot_order_id
                    order by datetime(event_time) desc, id desc
                ) as rn
            from order_events
        )
        select
            bot_order_id,
            parent_bot_order_id,
            exchange_order_id,
            client_order_id,
            side,
            order_type,
            state,
            reason,
            price_brl,
            qty_usdt,
            executed_qty_usdt,
            brl_value,
            source,
            note,
            event_time
        from ranked
        where rn = 1
        order by datetime(event_time) desc, bot_order_id desc
        limit ?
    """
    df = query_df(cfg, sql, (int(limit),))
    if df.empty:
        return df
    for col in ["price_brl", "qty_usdt", "executed_qty_usdt", "brl_value"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    if "event_time" in df.columns:
        df["event_time"] = parse_datetime_series(df["event_time"])
    return df


def bot_events_df(cfg: dict[str, Any], limit: int = 200) -> pd.DataFrame:
    df = query_df(cfg, "select * from bot_events order by id desc limit ?", (int(limit),))
    if df.empty:
        return df
    if "ts" in df.columns:
        df["ts"] = parse_datetime_series(df["ts"])
    return df


def dispatch_locks_df(cfg: dict[str, Any], limit: int = 50) -> pd.DataFrame:
    if "order_dispatch_locks" not in list_tables(cfg):
        return pd.DataFrame()
    df = query_df(cfg, "select * from order_dispatch_locks order by id desc limit ?", (int(limit),))
    return df


def reconciliation_df(cfg: dict[str, Any], limit: int = 50) -> pd.DataFrame:
    if "reconciliation_audit" not in list_tables(cfg):
        return pd.DataFrame()
    df = query_df(cfg, "select * from reconciliation_audit order by id desc limit ?", (int(limit),))
    return df


def render_header(cfg: dict[str, Any], status: dict[str, Any]) -> None:
    mode = str(cfg.get("execution", {}).get("mode", "dry_run")).upper()
    symbol = str(cfg.get("market", {}).get("symbol", "USDT/BRL"))
    time_text = str(status.get("time", "") or "sem snapshot")
    paused = bool(status.get("paused", False))
    flags = status.get("flags", {}) or {}

    left, right = st.columns([1.5, 1])
    with left:
        st.title(APP_TITLE)
        st.caption(f"{APP_SUBTITLE} • {symbol} • snapshot {time_text}")
        chips = [
            chip_html("Modo", mode, "warn" if mode == "LIVE" else "good"),
            chip_html("Bot", "PAUSADO" if paused else "ATIVO", tone_for_bool(paused, invert=True)),
            chip_html(
                "Reconciliação",
                "PENDENTE" if bool(flags.get("live_reconcile_required", False)) else "OK",
                "warn" if bool(flags.get("live_reconcile_required", False)) else "good",
            ),
            chip_html(
                "Erros",
                str(safe_int(flags.get("consecutive_error_count", 0))),
                "bad" if safe_int(flags.get("consecutive_error_count", 0)) > 0 else "good",
            ),
        ]
        st.markdown(f'<div class="sc-chip-wrap">{"".join(chips)}</div>', unsafe_allow_html=True)
    with right:
        market_tf = str(cfg.get("market", {}).get("timeframe", "1m"))
        st.markdown(
            f"""
            <div class="sc-card">
                <div class="sc-section-title">Contexto atual</div>
                <div class="sc-kv"><span>Par</span><span>{symbol}</span></div>
                <div class="sc-kv"><span>Timeframe base</span><span>{market_tf}</span></div>
                <div class="sc-kv"><span>Modo</span><span>{mode}</span></div>
                <div class="sc-kv"><span>Snapshot</span><span>{time_text}</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def summary_market_interval_label(cfg: dict[str, Any]) -> str:
    base_code = str(cfg.get("market", {}).get("timeframe", "1h") or "1h")
    label = interval_label_from_code(base_code)
    return label if label in interval_map() else "1 hora"


def render_summary_market_chart(cfg: dict[str, Any], status: dict[str, Any]) -> None:
    st.markdown("#### Mercado USDT/BRL")
    interval_label = summary_market_interval_label(cfg)
    df = load_chart_df(cfg, interval_label)
    if df.empty:
        st.info("Sem cache local de candles para o gráfico principal. Execute o backfill do cache.")
        return
    executions = execution_markers_df(cfg, limit=1000)
    position = status.get("position", {}) or {}
    fig = build_market_figure(
        df=df,
        trades=executions,
        position=position,
        title=f"USDT/BRL • {interval_label}",
        show_tp_stop=False,
        interval_label=interval_label,
    )
    fig.update_layout(height=520, margin=dict(l=10, r=10, t=38, b=10))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def render_trade_bank_chart(cfg: dict[str, Any]) -> None:
    st.markdown("#### Evolução da banca")
    initial_cash = safe_float(cfg.get("portfolio", {}).get("initial_cash_brl", 0.0))
    cycles = cycles_df(cfg, limit=5000)
    if cycles.empty or "closed_at" not in cycles.columns or "pnl_brl" not in cycles.columns:
        st.info("A curva da banca aparece após o fechamento do primeiro ciclo.")
        return

    closed = cycles.dropna(subset=["closed_at"]).sort_values("closed_at").copy()
    if closed.empty:
        st.info("A curva da banca aparece após o fechamento do primeiro ciclo.")
        return

    closed["pnl_brl"] = pd.to_numeric(closed["pnl_brl"], errors="coerce").fillna(0.0)
    closed = closed[closed["closed_at"].notna()].copy()
    if closed.empty:
        st.info("A curva da banca aparece após o fechamento do primeiro ciclo.")
        return

    closed["bank_brl"] = initial_cash + closed["pnl_brl"].cumsum()
    bank_df = pd.concat(
        [
            pd.DataFrame({"closed_at": [closed["closed_at"].iloc[0]], "bank_brl": [initial_cash]}),
            closed[["closed_at", "bank_brl"]],
        ],
        ignore_index=True,
    )

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=bank_df["closed_at"],
            y=bank_df["bank_brl"],
            mode="lines+markers",
            name="Banca",
            line=dict(color="#2563EB", width=3, shape="hv"),
            marker=dict(size=12, color="#2563EB"),
        )
    )

    cycle_colors = ["#16A34A" if v >= 0 else "#DC2626" for v in closed["pnl_brl"]]
    cycle_text = [format_money(v) for v in closed["pnl_brl"]]
    fig.add_trace(
        go.Scatter(
            x=closed["closed_at"],
            y=closed["bank_brl"],
            mode="markers+text",
            name="Ciclos fechados",
            marker=dict(size=22, color=cycle_colors, line=dict(color="#111827", width=1.5)),
            text=cycle_text,
            textposition="top center",
            textfont=dict(size=12, color="#111827"),
            hovertemplate="Fechamento: %{x}<br>Resultado: %{text}<br>Banca: R$ %{y:.2f}<extra></extra>",
        )
    )

    fig.update_layout(
        template="plotly_white",
        height=360,
        margin=dict(l=10, r=10, t=20, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#ffffff",
        xaxis_title="Negociações concluídas",
        yaxis_title="Banca (BRL)",
    )
    fig.update_xaxes(showgrid=True, gridcolor="#e5e7eb")
    fig.update_yaxes(showgrid=True, gridcolor="#e5e7eb")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def render_overview(cfg: dict[str, Any], status: dict[str, Any]) -> None:
    resumo_page.render(cfg, status, sys.modules[__name__])


def visible_bars_for_interval(interval_label: str) -> int:
    return safe_int(interval_map().get(interval_label, {}).get("bars", 180), 180)


def market_visible_bars_for_interval(interval_label: str) -> int:
    custom = {
        "1 minuto": 90,
        "5 minutos": 96,
        "15 minutos": 96,
        "1 hora": 72,
        "12 horas": 60,
        "24 horas": 45,
        "7 dias": 30,
        "1 mês": 18,
    }
    return safe_int(
        custom.get(interval_label, visible_bars_for_interval(interval_label)),
        visible_bars_for_interval(interval_label),
    )


def load_chart_df(cfg: dict[str, Any], interval_label: str) -> pd.DataFrame:
    meta = interval_map()[interval_label]
    code = str(meta["code"])
    if code in {"7d", "30d"}:
        base_df = load_market_cache_df(str(market_cache_file(cfg, "1d")))
        if base_df.empty:
            return base_df
        rule = "7D" if code == "7d" else "30D"
        agg = (
            base_df.set_index("ts")
            .resample(rule, label="right", closed="right")
            .agg(
                open=("open", "first"),
                high=("high", "max"),
                low=("low", "min"),
                close=("close", "last"),
                volume=("volume", "sum"),
            )
            .dropna()
            .reset_index()
        )
        df = agg
    else:
        path = market_cache_file(cfg, code)
        df = load_market_cache_df(str(path))
    if df.empty:
        return df
    bars = visible_bars_for_interval(interval_label)
    return df.tail(bars).copy()


def ensure_interval_cache(cfg: dict[str, Any], interval_label: str, days: int = 30) -> Path:
    meta = interval_map()[interval_label]
    code = str(meta["code"])
    target_code = "1d" if code in {"7d", "30d"} else code
    path = market_cache_file(cfg, target_code)
    current = load_market_cache_df(str(path)) if path.exists() else pd.DataFrame()
    if current.empty:
        fetched = _fetch_ohlcv_history_public(cfg, target_code, days=days)
        if not fetched.empty:
            write_market_cache_df(cfg, target_code, fetched)
    return path


def backfill_all_market_caches(cfg: dict[str, Any], days: int = 30) -> list[Path]:
    written: list[Path] = []
    for code in ["1m", "5m", "15m", "1h", "12h", "1d"]:
        fetched = _fetch_ohlcv_history_public(cfg, code, days=days)
        if not fetched.empty:
            written.append(write_market_cache_df(cfg, code, fetched))
    return written


def get_current_market_interval(cfg: dict[str, Any]) -> str:
    current = get_query_value(
        "market", st.session_state.get("market_interval", summary_market_interval_label(cfg))
    )
    if current not in interval_map():
        current = summary_market_interval_label(cfg)
    st.session_state["market_interval"] = current
    return current


def set_current_market_interval(value: str) -> None:
    if value not in interval_map():
        return
    st.session_state["market_interval"] = value
    set_query_value("market", value)


def render_interval_buttons(current: str) -> str:
    labels = list(interval_map().keys())
    cols = st.columns(4)
    selected = current
    for idx, label in enumerate(labels):
        with cols[idx % 4]:
            if st.button(
                label,
                key=f"mkt_btn_{label}",
                width="stretch",
                type="primary" if label == current else "secondary",
            ):
                selected = label
    if selected != current:
        set_current_market_interval(selected)
        st.rerun()
    return selected


def get_current_page(page_options: list[str]) -> str:
    current = get_query_value("page", st.session_state.get("nav_page", "Resumo"))
    if current not in page_options:
        current = "Resumo"
    st.session_state["nav_page"] = current
    return current


def render_sidebar_navigation(page_options: list[str], current: str) -> str:
    selected = current
    for label in page_options:
        if st.button(
            label,
            key=f"nav_btn_{label}",
            width="stretch",
            type="primary" if label == current else "secondary",
        ):
            selected = label
    if selected != current:
        st.session_state["nav_page"] = selected
        set_query_value("page", selected)
        st.rerun()
    return selected


def render_market(cfg: dict[str, Any], status: dict[str, Any]) -> None:
    mercado_page.render(cfg, status, sys.modules[__name__])


def render_orders(cfg: dict[str, Any], status: dict[str, Any]) -> None:
    operacoes_page.render(cfg, status, sys.modules[__name__])


def render_config(cfg: dict[str, Any]) -> None:
    configuracao_page.render(cfg, sys.modules[__name__])


def render_ntfy(cfg: dict[str, Any]) -> None:
    notificacoes_page.render(cfg, sys.modules[__name__])


def render_sidebar_runtime_controls(cfg: dict[str, Any], status: dict[str, Any]) -> None:
    refresh_control.render_sidebar_runtime_controls(
        cfg,
        status,
        state_store=state_store,
    )


def render_db(cfg: dict[str, Any]) -> None:
    banco_dados_page.render(cfg, sys.modules[__name__])


def render_hardening(cfg: dict[str, Any], status: dict[str, Any]) -> None:
    saude_sistema_page.render(cfg, status, sys.modules[__name__])


def main() -> None:
    inject_styles()
    cfg = load_cfg()
    status = load_runtime_status(cfg)

    app_session.ensure_session_defaults()
    page_options = list(app_session.PAGE_OPTIONS)
    current_page = app_session.current_page(get_query_value, page_options)

    inject_auto_refresh(
        60000,
        enabled=app_session.auto_refresh_enabled() and current_page in AUTO_REFRESH_PAGES,
    )

    render_header(cfg, status)

    with st.sidebar:
        render_sidebar_runtime_controls(cfg, status)
        st.markdown("---")
        st.markdown("### Navegação")
        page = render_sidebar_navigation(page_options, current_page)
        app_session.set_current_page(page, set_query_value)
        st.markdown("---")
        st.markdown(
            f"""
            <div class="sc-card">
                <div class="sc-section-title">Ambiente</div>
                <div class="sc-kv"><span>DB</span><span>{db_path_from_cfg(cfg).name}</span></div>
                <div class="sc-kv"><span>Config</span><span>{config_path().name}</span></div>
                <div class="sc-kv"><span>Cache</span><span>{dashboard_cache_dir(cfg).name}</span></div>
                <div class="sc-kv"><span>Auto refresh</span><span>{"ATIVO" if app_session.auto_refresh_enabled() and page in AUTO_REFRESH_PAGES else "PAUSADO"}</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if page in AUTO_REFRESH_PAGES:
            st.caption("O painel pode atualizar automaticamente a cada 1 minuto.")
        else:
            st.caption(
                "Nesta aba a atualização automática fica desligada para facilitar edição e diagnóstico."
            )

    if page == "Resumo":
        render_overview(cfg, status)
    elif page == "Mercado":
        render_market(cfg, status)
    elif page == "Operações":
        render_orders(cfg, status)
    elif page == "Configuração":
        render_config(cfg)
    elif page == "NTFY":
        render_ntfy(cfg)
    elif page == "Proteção":
        render_hardening(cfg, status)
    else:
        render_db(cfg)


