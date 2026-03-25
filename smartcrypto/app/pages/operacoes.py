from __future__ import annotations

from typing import Any

from smartcrypto.app.components import order_table


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

    open_orders = ui.load_open_orders_cache(cfg)
    planned = ui.planned_orders_df(cfg)
    states = ui.order_states_df(cfg)
    executions = ui.execution_markers_df(cfg, 200)

    top = st.columns(4)
    top[0].metric("Ordens abertas na exchange", str(len(open_orders)))
    top[1].metric("Ordens planejadas", str(len(planned)))
    top[2].metric("Ordens lógicas", str(len(states)))
    top[3].metric("Negociações", str(len(executions)))
    st.caption(
        "Ordens abertas na exchange são ordens reais ainda pendentes na Binance. Posição aberta e trade já executado não entram nessa contagem."
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
                preview["created_at"] = pd.to_datetime(preview["created_at"], errors="coerce", utc=True)
                preview["created_at"] = preview["created_at"].dt.strftime("%d/%m/%Y %H:%M:%S")
            cols_keep = [
                c
                for c in ["created_at", "side", "price_brl", "qty_usdt", "brl_value", "fee_brl", "source"]
                if c in preview.columns
            ]
            st.dataframe(preview[cols_keep].tail(50).iloc[::-1], width="stretch", hide_index=True)
