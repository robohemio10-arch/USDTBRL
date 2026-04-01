from __future__ import annotations

from html import escape
from typing import Any

from smartcrypto.app.components import order_table


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _console_panel_cells(panel: dict[str, Any]) -> tuple[list[tuple[str, str]], set[int], set[int]]:
    realized_profit = _safe_float(
        panel.get("realized_profit_brl", panel.get("realized_profit_total_brl"))
    )
    pnl_value = _safe_float(panel.get("pnl_pct"))
    columns = [
        ("Moeda/USDT/BRL", str(panel.get("symbol", "USDT/BRL") or "USDT/BRL")),
        ("Modo Paper/Live", str(panel.get("mode", "paper") or "paper").upper()),
        ("Run sim/não", "SIM" if bool(panel.get("run_active", False)) else "NÃO"),
        ("Valor de entrada", f"{_safe_float(panel.get('entry_price_brl')):,.4f}"),
        ("Número da rampa", str(_safe_int(panel.get("ramps_done", panel.get("ramp_number"))))),
        ("Valor médio", f"{_safe_float(panel.get('avg_price_brl')):,.4f}"),
        ("Valor atual", f"{_safe_float(panel.get('current_price_brl')):,.4f}"),
        ("PNL em %", f"{pnl_value:,.2f}%"),
        ("Ciclos realizados", str(_safe_int(panel.get("closed_cycles")))),
        ("Empenhado neste ciclo", f"{_safe_float(panel.get('invested_this_cycle_brl')):,.2f}"),
        ("Lucro total ciclos", f"{realized_profit:,.2f}"),
        ("Montante total ciclos", f"{_safe_float(panel.get('total_spent_all_cycles_brl')):,.2f}"),
    ]
    positive_indexes: set[int] = set()
    negative_indexes: set[int] = set()
    if pnl_value > 0:
        positive_indexes.add(7)
    elif pnl_value < 0:
        negative_indexes.add(7)
    if realized_profit > 0:
        positive_indexes.add(10)
    elif realized_profit < 0:
        negative_indexes.add(10)
    return columns, positive_indexes, negative_indexes


def render_console_bot_panel_html(panel: dict[str, Any]) -> str:
    columns, positive_indexes, negative_indexes = _console_panel_cells(panel)
    header_cells = "".join(
        f'<th class="sc-console-th">{escape(label)}</th>' for label, _ in columns
    )
    value_cells: list[str] = []
    for idx, (_, value) in enumerate(columns):
        classes = ["sc-console-td"]
        if idx in positive_indexes:
            classes.append("sc-console-pos")
        elif idx in negative_indexes:
            classes.append("sc-console-neg")
        else:
            classes.append("sc-console-neutral")
        value_cells.append(f'<td class="{" ".join(classes)}">{escape(str(value))}</td>')
    values_html = "".join(value_cells)
    return (
        '<div class="sc-console-panel">'
        '<table class="sc-console-grid">'
        "<thead><tr>"
        + header_cells
        + "</tr></thead>"
        "<tbody><tr>"
        + values_html
        + "</tr></tbody>"
        "</table>"
        "</div>"
    )


def _render_bot_console_panel(cfg: dict[str, Any], status: dict[str, Any], ui: Any) -> None:
    import streamlit as st

    runtime_status = ui.load_runtime_status(cfg)
    latest = runtime_status or status or {}
    panel = dict(latest.get("paper_panel", {}) or {})
    if not panel:
        st.info("Painel do bot ainda sem dados de paper para exibir.")
        return
    st.markdown("#### Painel do bot")
    st.markdown(render_console_bot_panel_html(panel), unsafe_allow_html=True)
    updated_at = str(latest.get("time", "") or "")
    if updated_at:
        st.caption(f"Atualização parcial automática do painel do bot • {updated_at}")


def render(cfg: dict[str, Any], status: dict[str, Any], ui: Any) -> None:
    import pandas as pd
    import streamlit as st

    st.subheader("Operações")
    store = ui.state_store(cfg)
    action_cols = st.columns(4)
    if action_cols[0].button("Pausar bot", width="stretch"):
        store.set_flag("paused", True)
        st.success("Flag paused = True")
    if action_cols[1].button("Retomar bot", width="stretch"):
        store.set_flag("paused", False)
        st.success("Flag paused = False")
    if action_cols[2].button("Solicitar force sell", width="stretch"):
        store.set_flag("force_sell_requested", True)
        st.success("Flag force_sell_requested = True")
    if action_cols[3].button("Solicitar reset de ciclo", width="stretch"):
        store.set_flag("reset_cycle_requested", True)
        st.success("Flag reset_cycle_requested = True")

    fragment_api = getattr(st, "fragment", None)
    if callable(fragment_api):
        @fragment_api(run_every="5s")
        def _bot_console_fragment() -> None:
            _render_bot_console_panel(cfg, status, ui)

        _bot_console_fragment()
    else:
        _render_bot_console_panel(cfg, status, ui)

    open_orders = ui.load_open_orders_cache(cfg)
    planned = ui.planned_orders_df(cfg)
    states = ui.order_states_df(cfg)
    executions = ui.execution_markers_df(cfg, 200)

    top = st.columns(4)
    top[0].metric("Ordens abertas na exchange", str(len(open_orders)))
    top[1].metric("Ordens tampas", str(len(planned)))
    top[2].metric("Ordens lógicas", str(len(states)))
    top[3].metric("Negociações", str(len(executions)))
    st.caption(
        "Ordens abertas na exchange são ordens reais ainda pendentes na Binance. "
        "Posição aberta e trade já executado não entram nessa contagem."
    )

    st.markdown("#### Situação operacional")
    left, right = st.columns(2)
    with left:
        order_table.render(open_orders, empty_message="Sem ordens reais abertas na exchange.")
    with right:
        order_table.render(planned, empty_message="Sem ordens planejadas.")

    lower_left, lower_right = st.columns(2)
    with lower_left:
        st.markdown("#### Estado atual por ordem lógica")
        order_table.render(states, empty_message="Sem eventos de ordens.")
    with lower_right:
        st.markdown("#### Negociações")
        if executions.empty:
            st.info("Sem negociações.")
        else:
            preview = executions.copy()
            if "created_at" in preview.columns:
                preview["created_at"] = pd.to_datetime(
                    preview["created_at"], errors="coerce", utc=True
                )
                preview["created_at"] = preview["created_at"].dt.strftime("%d/%m/%Y %H:%M:%S")
            cols_keep = [
                c
                for c in [
                    "created_at",
                    "side",
                    "price_brl",
                    "qty_usdt",
                    "brl_value",
                    "fee_brl",
                    "source",
                ]
                if c in preview.columns
            ]
            st.dataframe(preview[cols_keep].tail(50).iloc[::-1], width="stretch", hide_index=True)
