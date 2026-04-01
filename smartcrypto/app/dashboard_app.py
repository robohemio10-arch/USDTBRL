from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import streamlit.components.v1 as components
from plotly.subplots import make_subplots

from smartcrypto.app import session as app_session
from smartcrypto.app import styles as app_styles
from smartcrypto.app.components import position_card, refresh_control
from smartcrypto.app.config_io import (
    config_consistency_status,
    config_path,
    load_cfg,
    root_dir,
    save_cfg,
)
from smartcrypto.app.data_access import (
    bot_events_df,
    cycles_df,
    db_path_from_cfg,
    dispatch_locks_df,
    list_tables,
    load_open_orders_cache,
    load_runtime_status as load_runtime_status_fallback,
    order_states_df,
    parse_datetime_series,
    planned_orders_df,
    portfolio,
    position_manager,
    query_df,
    read_json_file,
    read_table,
    reconciliation_df,
    safe_float,
    safe_int,
    snapshots_df,
    state_store,
    trades_df,
)
from smartcrypto.app.pages import (
    banco_dados as banco_dados_page,
    configuracao as configuracao_page,
    ia_rollout as ia_rollout_page,
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
from smartcrypto.infra.notifications import NtfyClient
from smartcrypto.runtime.cache import (
    cache_symbol_token,
    dashboard_cache_dir,
    market_cache_file,
    runtime_status_cache_file,
)
from smartcrypto.runtime.status import runtime_status_summary

st.set_page_config(
    page_title="SmartCrypto Dashboard", layout="wide", initial_sidebar_state="expanded"
)

APP_TITLE = app_styles.APP_TITLE
APP_SUBTITLE = app_styles.APP_SUBTITLE
AUTO_REFRESH_PAGES = app_session.AUTO_REFRESH_PAGES
ACTIVE_DISPATCH_LOCK_STATUSES = {"pending_submit", "submit_unknown", "submitted", "recovered_open"}

IA_ROLLOUT_PAGE_LABEL = "IA & Rollout"
if IA_ROLLOUT_PAGE_LABEL not in app_session.PAGE_OPTIONS:
    app_session.PAGE_OPTIONS = [*app_session.PAGE_OPTIONS, IA_ROLLOUT_PAGE_LABEL]


def inject_styles() -> None:
    app_styles.inject_styles()


def tone_for_bool(flag: bool, invert: bool = False) -> str:
    if invert:
        return "bad" if flag else "good"
    return "good" if flag else "neutral"


def chip_html(label: str, value: str, tone: str = "neutral") -> str:
    return f'<span class="sc-chip {tone}"><span>{label}</span><span>{value}</span></span>'


def normalized_execution_mode(cfg: dict[str, Any]) -> str:
    mode = str(cfg.get("execution", {}).get("mode", "paper") or "paper").strip().lower()
    if mode == "dry_run":
        return "paper"
    return mode if mode in {"paper", "live"} else "paper"


def dashboard_db_identity(cfg: dict[str, Any]) -> dict[str, str]:
    try:
        return state_store(cfg).read_operational_identity()
    except Exception:
        return {}


def dashboard_profile_summary(cfg: dict[str, Any], operational_status: dict[str, Any] | None = None) -> dict[str, str]:
    operational_status = operational_status or {}
    manifest = dict(operational_status.get("manifest", {}) or {})
    identity = dashboard_db_identity(cfg)
    profile = str(identity.get("db_profile_id") or manifest.get("experiment_profile") or "n/d")
    role = str(identity.get("db_role") or normalized_execution_mode(cfg) or "n/d")
    symbol = str(identity.get("db_symbol") or cfg.get("market", {}).get("symbol", "n/d") or "n/d")
    return {
        "profile": profile,
        "role": role.upper(),
        "symbol": symbol.upper(),
    }


def dashboard_warnings(cfg: dict[str, Any], operational_status: dict[str, Any] | None = None) -> list[str]:
    operational_status = operational_status or {}
    warnings: list[str] = []
    mode = normalized_execution_mode(cfg)
    manifest = dict(operational_status.get("manifest", {}) or {})
    preflight = dict(operational_status.get("preflight", {}) or {})
    identity = dashboard_db_identity(cfg)
    config_name = config_path().name.lower()

    if mode == "live":
        warnings.append("Dashboard carregado com perfil LIVE. Use-o apenas para observação e diagnóstico.")
    if config_name in {"live.yml", "config.live.yml"}:
        warnings.append("O dashboard está usando um arquivo de configuração live.")
    if str(preflight.get("status", "")).lower() not in {"", "ok"}:
        warnings.append(f"Pré-flight reporta {str(preflight.get('status', 'unknown')).upper()}.")
    expected_role = mode
    current_role = str(identity.get("db_role", "")).strip().lower()
    if current_role and current_role != expected_role:
        warnings.append(f"DB com identidade {current_role} divergente do modo {expected_role}.")
    manifest_mode = str(manifest.get("mode", "")).strip().lower()
    if manifest_mode and manifest_mode != mode:
        warnings.append(f"Manifesto operacional em {manifest_mode} diverge da configuração {mode}.")
    return warnings


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



def load_runtime_status(cfg: dict[str, Any]) -> dict[str, Any]:
    return load_runtime_status_fallback(cfg, runtime_status_cache_file)


def load_operational_status(cfg: dict[str, Any], status: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        return runtime_status_summary(
            cfg,
            state_store(cfg),
            price=safe_float((status or {}).get("price_brl", 0.0)),
        )
    except Exception:
        return {
            "manifest": dict(cfg.get("__operational_manifest", {}) or {}),
            "preflight": dict(cfg.get("__preflight", {}) or {}),
            "flags": dict(cfg.get("__feature_flags", {}) or {}),
            "mode": str(cfg.get("execution", {}).get("mode", "") or ""),
            "ai_summary": {
                "total": 0,
                "divergence_count": 0,
                "veto_count": 0,
                "override_count": 0,
                "stages": {},
                "latest_stage": "disabled",
            },
            "critical_events": [],
            "runtime": status or {},
        }


def render_operational_status_block(cfg: dict[str, Any], operational_status: dict[str, Any]) -> None:
    manifest = dict(operational_status.get("manifest", {}) or {})
    preflight = dict(operational_status.get("preflight", {}) or {})
    ai_summary = dict(operational_status.get("ai_summary", {}) or {})
    flags = dict(operational_status.get("flags", {}) or {})
    active_flags = [name for name, enabled in flags.items() if bool(enabled)]
    critical_events = list(operational_status.get("critical_events", []) or [])
    latest_event = critical_events[0] if critical_events else {}
    profile = dashboard_profile_summary(cfg, operational_status)
    st.markdown(
        f"""
        <div class="sc-card">
            <div class="sc-section-title">Manifesto operacional</div>
            <div class="sc-kv"><span>Modo efetivo</span><span>{str(manifest.get("mode", normalized_execution_mode(cfg))).upper()}</span></div>
            <div class="sc-kv"><span>Perfil</span><span>{profile["profile"]}</span></div>
            <div class="sc-kv"><span>Papel do DB</span><span>{profile["role"]}</span></div>
            <div class="sc-kv"><span>Config</span><span>{Path(str(manifest.get("config_path", cfg.get("__config_path", "")))).name or "n/d"}</span></div>
            <div class="sc-kv"><span>DB</span><span>{Path(str(manifest.get("db_path", cfg.get("storage", {}).get("db_path", "")))).name or "n/d"}</span></div>
            <div class="sc-kv"><span>Build</span><span>{str(manifest.get("build_id", "n/d")) or "n/d"}</span></div>
            <div class="sc-kv"><span>Run ID</span><span>{str(manifest.get("run_id", operational_status.get("run_id", "n/d"))) or "n/d"}</span></div>
            <div class="sc-kv"><span>Pré-flight</span><span>{str(preflight.get("status", "unknown")).upper()}</span></div>
            <div class="sc-kv"><span>Flags ativas</span><span>{len(active_flags)}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if active_flags:
        st.caption("Flags ativas: " + ", ".join(active_flags[:8]))
    for warning_text in dashboard_warnings(cfg, operational_status):
        st.warning(warning_text)
    if latest_event:
        st.caption(
            f"Último evento crítico: {latest_event.get('level', '')} • {latest_event.get('event', '')} • {latest_event.get('ts', '')}"
        )
    st.caption(
        "IA: decisões={total} • divergências={divergence_count} • vetos={veto_count} • overrides={override_count} • estágio={latest_stage}".format(
            total=ai_summary.get("total", 0),
            divergence_count=ai_summary.get("divergence_count", 0),
            veto_count=ai_summary.get("veto_count", 0),
            override_count=ai_summary.get("override_count", 0),
            latest_stage=ai_summary.get("latest_stage", "disabled"),
        )
    )



def render_top_operational_alert(status: dict[str, Any], operational_status: dict[str, Any] | None = None) -> None:
    operational_status = operational_status or {}
    health = dict(status.get("health", {}) or {})
    issues = list(health.get("issues", []) or [])
    recent_errors = list(health.get("recent_error_logs", []) or [])
    paused = bool(status.get("paused", False))
    flags = dict(status.get("flags", {}) or {})
    critical_events = list(operational_status.get("critical_events", []) or [])

    tone = "info"
    title = ""
    details: list[str] = []

    latest_recent = recent_errors[-1] if recent_errors else {}
    latest_critical = critical_events[0] if critical_events else {}

    if paused:
        tone = "bad"
        title = "Robô pausado"
        details.append("O runtime está pausado e não vai abrir novas operações até ser reativado.")
    if any(str(item.get("event", "")).lower() == "circuit_breaker_paused" for item in recent_errors):
        tone = "bad"
        title = "Circuit breaker acionado"
        details.append("O bot entrou em proteção após falhas consecutivas no runtime.")
    if flags.get("live_reconcile_required", False):
        tone = "warn"
        title = title or "Reconciliação pendente"
        details.append("Existe reconciliação pendente antes de novas ações operacionais.")
    if latest_recent:
        event_name = str(latest_recent.get("event", "") or "erro_recente")
        error_fields = dict(latest_recent.get("fields", {}) or {})
        error_text = str(error_fields.get("error", "") or "").strip()
        details.append(f"Último evento: {event_name}.")
        if error_text:
            details.append(error_text[:220])
    elif latest_critical:
        tone = "warn" if tone == "info" else tone
        title = title or "Atenção operacional"
        details.append(
            f"Evento crítico recente: {latest_critical.get('event', 'n/d')} em {latest_critical.get('ts', 'n/d')}."
        )

    if not title and issues:
        tone = "warn"
        title = "Atenção operacional"
        details.extend(str(item.get("message", "") or "").strip() for item in issues[:2] if item.get("message"))

    if not title:
        return

    details_html = "".join(
        f"<li>{detail}</li>" for detail in details if str(detail).strip()
    )
    st.markdown(
        f"""
        <div class="sc-operational-banner {tone}">
            <div class="sc-operational-banner-title">{title}</div>
            <ul class="sc-operational-banner-list">{details_html}</ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_panel(
    cfg: dict[str, Any],
    status: dict[str, Any],
    operational_status: dict[str, Any],
    page_options: list[str],
    page: str,
) -> None:
    profile = dashboard_profile_summary(cfg, operational_status)
    with st.sidebar:
        st.markdown("## Painel do robô")
        render_sidebar_runtime_controls(cfg, status)
        st.markdown("### Navegação")
        render_sidebar_navigation(page_options, page)
        st.markdown(
            f"""
            <div class="sc-sidebar-card">
                <div class="sc-sidebar-kv"><span>DB</span><strong>{db_path_from_cfg(cfg).name}</strong></div>
                <div class="sc-sidebar-kv"><span>Config</span><strong>{config_path().name}</strong></div>
                <div class="sc-sidebar-kv"><span>Perfil</span><strong>{profile["profile"]}</strong></div>
                <div class="sc-sidebar-kv"><span>Papel do DB</span><strong>{profile["role"]}</strong></div>
                <div class="sc-sidebar-kv"><span>Cache</span><strong>{dashboard_cache_dir(cfg).name}</strong></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        render_operational_status_block(cfg, operational_status)

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



def _aligned_trade_pins(
    trade_window: pd.DataFrame,
    df: pd.DataFrame,
    interval_label: str,
) -> pd.DataFrame:
    if trade_window.empty or "created_at" not in trade_window.columns:
        return pd.DataFrame()
    aligned = trade_window.copy()
    aligned["created_at"] = parse_datetime_series(aligned["created_at"])
    aligned = aligned.dropna(subset=["created_at"]).sort_values("created_at").reset_index(drop=True)
    if aligned.empty:
        return pd.DataFrame()
    candles = pd.DataFrame({"pin_x": pd.to_datetime(df["ts"], utc=True)}).sort_values("pin_x")
    tolerance = chart_interval_timedelta(interval_label, df)
    merged = pd.merge_asof(
        aligned,
        candles,
        left_on="created_at",
        right_on="pin_x",
        direction="nearest",
        tolerance=tolerance,
    )
    merged["pin_x"] = merged["pin_x"].fillna(merged["created_at"])
    return merged


def _add_trade_pin_layer(
    fig: go.Figure,
    trades: pd.DataFrame,
    *,
    side: str,
    marker_symbol: str,
    marker_color: str,
    marker_border: str,
    text_color: str,
    label_text: str,
    text_position: str,
    row: int,
    col: int,
) -> None:
    side_df = trades[trades["side"].astype(str).str.lower() == side].copy()
    if side_df.empty:
        return
    for _, entry in side_df.tail(24).iterrows():
        fig.add_vline(
            x=entry["pin_x"],
            line_color=marker_color,
            line_dash="dot",
            line_width=1.1,
            opacity=0.24,
            row=row,
            col=col,
        )
    hovertemplate = (
        f"{label_text}<br>%{{customdata[0]}}<br>Preço: R$ %{{y:.4f}}"
        "<br>Qtd: %{customdata[1]:.4f}<extra></extra>"
    )
    fig.add_trace(
        go.Scatter(
            x=side_df["pin_x"],
            y=side_df["price_brl"],
            mode="markers+text",
            text=[label_text[0]] * len(side_df),
            textposition="middle center",
            textfont=dict(size=10, color=text_color, family="Arial Black"),
            name=label_text,
            marker=dict(
                symbol=marker_symbol,
                size=19,
                color=marker_color,
                line=dict(color=marker_border, width=1.6),
            ),
            customdata=list(
                zip(
                    side_df["created_at"].dt.strftime("%d/%m/%Y %H:%M:%S"),
                    pd.to_numeric(side_df.get("qty_usdt", 0.0), errors="coerce").fillna(0.0),
                )
            ),
            hovertemplate=hovertemplate,
            cliponaxis=False,
        ),
        row=row,
        col=col,
    )

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
        pin_window = _aligned_trade_pins(trade_window, df, interval_label)
        if not pin_window.empty:
            _add_trade_pin_layer(
                fig,
                pin_window,
                side="buy",
                marker_symbol="triangle-up",
                marker_color="#16A34A",
                marker_border="#14532D",
                text_color="#F8FAFC",
                label_text="Compra",
                text_position="top center",
                row=1,
                col=1,
            )
            _add_trade_pin_layer(
                fig,
                pin_window,
                side="sell",
                marker_symbol="triangle-down",
                marker_color="#DC2626",
                marker_border="#7F1D1D",
                text_color="#F8FAFC",
                label_text="Venda",
                text_position="bottom center",
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


def render_header(cfg: dict[str, Any], status: dict[str, Any], operational_status: dict[str, Any] | None = None) -> None:
    mode = normalized_execution_mode(cfg).upper()
    symbol = str(cfg.get("market", {}).get("symbol", "USDT/BRL"))
    time_text = str(status.get("time", "") or "sem snapshot")
    paused = bool(status.get("paused", False))
    flags = status.get("flags", {}) or {}
    operational_status = operational_status or {}
    manifest = dict(operational_status.get("manifest", {}) or {})
    preflight = dict(operational_status.get("preflight", {}) or {})
    profile = dashboard_profile_summary(cfg, operational_status)

    left, right = st.columns([1.5, 1])
    with left:
        st.title(APP_TITLE)
        st.caption(f"{APP_SUBTITLE} • {symbol} • snapshot {time_text}")
        chips = [
            chip_html("Modo", mode, "warn" if mode == "LIVE" else "good"),
            chip_html("DB", profile["role"], "warn" if profile["role"] == "LIVE" else "good"),
            chip_html(
                "Pré-flight",
                str(preflight.get("status", "unknown")).upper(),
                "good" if str(preflight.get("status", "")).lower() == "ok" else "bad",
            ),
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
        render_top_operational_alert(status, operational_status)
        for warning_text in dashboard_warnings(cfg, operational_status):
            st.warning(warning_text)
    with right:
        market_tf = str(cfg.get("market", {}).get("timeframe", "1m"))
        cfg_status = config_consistency_status()
        if cfg_status["both_exist"] and not cfg_status["same_content"]:
            mode_text = f"principal={cfg_status['primary_mode'] or 'n/d'} • legado={cfg_status['legacy_mode'] or 'n/d'}"
            st.warning(f"Arquivos de configuração divergentes detectados: {mode_text}. O dashboard usa {cfg_status['canonical_path'].name}.")

        st.markdown(
            f"""
            <div class="sc-card">
                <div class="sc-section-title">Contexto atual</div>
                <div class="sc-kv"><span>Par</span><span>{symbol}</span></div>
                <div class="sc-kv"><span>Timeframe base</span><span>{market_tf}</span></div>
                <div class="sc-kv"><span>Modo</span><span>{mode}</span></div>
                <div class="sc-kv"><span>Perfil</span><span>{profile["profile"]}</span></div>
                <div class="sc-kv"><span>Papel do DB</span><span>{profile["role"]}</span></div>
                <div class="sc-kv"><span>Build</span><span>{str(manifest.get("build_id", "n/d")) or "n/d"}</span></div>
                <div class="sc-kv"><span>Pré-flight</span><span>{str(preflight.get("status", "unknown")).upper()}</span></div>
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


def render_top_navigation(page_options: list[str], current: str) -> str:
    st.markdown('<div class="sc-top-nav-title">Abas do dashboard</div>', unsafe_allow_html=True)
    st.caption("Use esta navegação principal. A sidebar virou complementar, para evitar depender do menu lateral.")
    selected = current
    columns_per_row = 4
    for start in range(0, len(page_options), columns_per_row):
        row = page_options[start : start + columns_per_row]
        cols = st.columns(len(row))
        for idx, label in enumerate(row):
            with cols[idx]:
                if st.button(
                    label,
                    key=f"top_nav_btn_{label}",
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
    status = load_runtime_status_fallback(cfg, runtime_status_cache_file)
    operational_status = load_operational_status(cfg, status)

    app_session.ensure_session_defaults()
    page_options = list(app_session.PAGE_OPTIONS)
    current_page = app_session.current_page(get_query_value, page_options)

    inject_auto_refresh(
        60000,
        enabled=app_session.auto_refresh_enabled() and current_page in AUTO_REFRESH_PAGES,
    )

    render_header(cfg, status, operational_status)
    page = render_top_navigation(page_options, current_page)
    app_session.set_current_page(page, set_query_value)

    render_sidebar_panel(cfg, status, operational_status, page_options, page)

    with st.expander("Status operacional detalhado", expanded=False):
        profile = dashboard_profile_summary(cfg, operational_status)
        st.markdown(
            f"""
            <div class="sc-card">
                <div class="sc-section-title">Ambiente</div>
                <div class="sc-kv"><span>DB</span><span>{db_path_from_cfg(cfg).name}</span></div>
                <div class="sc-kv"><span>Config</span><span>{config_path().name}</span></div>
                <div class="sc-kv"><span>Perfil</span><span>{profile["profile"]}</span></div>
                <div class="sc-kv"><span>Papel do DB</span><span>{profile["role"]}</span></div>
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
    elif page == IA_ROLLOUT_PAGE_LABEL:
        ia_rollout_page.render(cfg, status, sys.modules[__name__])
    else:
        render_db(cfg)




if __name__ == "__main__":
    main()
