from __future__ import annotations

from typing import Any, Callable


def render_sidebar_runtime_controls(
    cfg: dict[str, Any],
    status: dict[str, Any],
    *,
    state_store: Callable[[dict[str, Any]], Any],
) -> None:
    import streamlit as st

    store = state_store(cfg)
    flags = dict(status.get("flags", {}) or {})
    paused = bool(status.get("paused", False))
    auto_refresh_enabled = bool(st.session_state.get("auto_refresh_enabled", True))
    pause_after_sell_requested = bool(
        flags.get("pause_after_sell_requested", store.get_flag("pause_after_sell_requested", False))
    )

    st.markdown("### Controles do robô")
    if st.button("Ativar robô", key="sidebar_activate_bot", width="stretch", type="primary"):
        store.set_flag("paused", False)
        st.success("Bot ativado.")
        st.rerun()

    if st.button(
        "Pausar robô imediatamente",
        key="sidebar_pause_bot_now",
        width="stretch",
        type="secondary",
    ):
        store.set_flag("paused", True)
        st.success("Bot pausado imediatamente.")
        st.rerun()

    if st.button(
        "Pausar auto-refresh",
        key="sidebar_pause_auto_refresh",
        width="stretch",
        disabled=not auto_refresh_enabled,
    ):
        st.session_state["auto_refresh_enabled"] = False
        st.success("Auto-refresh pausado.")
        st.rerun()

    if st.button(
        "Ativar auto-refresh",
        key="sidebar_resume_auto_refresh",
        width="stretch",
        disabled=auto_refresh_enabled,
    ):
        st.session_state["auto_refresh_enabled"] = True
        st.success("Auto-refresh ativado.")
        st.rerun()

    if st.button(
        "Pausar robô após a venda",
        key="sidebar_pause_after_sell",
        width="stretch",
        type="secondary" if pause_after_sell_requested else "primary",
    ):
        next_value = not pause_after_sell_requested
        store.set_flag("pause_after_sell_requested", next_value)
        if next_value:
            st.success("Pausa após venda armada.")
        else:
            st.success("Pausa após venda desarmada.")
        st.rerun()

    bot_status = "PAUSADO" if paused else "ATIVO"
    auto_status = "ATIVO" if auto_refresh_enabled else "PAUSADO"
    after_sell_status = "ARMADA" if pause_after_sell_requested else "DESLIGADA"

    st.markdown(
        f"""
        <div class="sc-sidebar-card">
            <div class="sc-sidebar-kv"><span>Status do robô</span><strong>{bot_status}</strong></div>
            <div class="sc-sidebar-kv"><span>Auto-refresh</span><strong>{auto_status}</strong></div>
            <div class="sc-sidebar-kv"><span>Pausa após venda</span><strong>{after_sell_status}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
