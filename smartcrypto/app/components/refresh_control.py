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
    paused = bool(status.get("paused", False))
    auto_refresh_enabled = bool(st.session_state.get("auto_refresh_enabled", True))
    st.markdown("### Controle rápido")
    c1, c2 = st.columns(2)
    if paused:
        if c1.button("Ativar robô", width="stretch"):
            store.set_flag("paused", False)
            st.success("Bot retomado.")
            st.rerun()
    else:
        if c1.button("Pausar robô", width="stretch"):
            store.set_flag("paused", True)
            st.success("Bot pausado.")
            st.rerun()
    if c2.button("Atualizar agora", width="stretch"):
        st.cache_data.clear()
        st.session_state["_manual_refresh_nonce"] = 1
        st.rerun()

    a1, a2 = st.columns(2)
    if a1.button("Parar atualização automática", width="stretch"):
        st.session_state["auto_refresh_enabled"] = False
        st.success("Atualização automática pausada.")
        st.rerun()
    if a2.button("Voltar atualização automática", width="stretch"):
        st.session_state["auto_refresh_enabled"] = True
        st.success("Atualização automática reativada.")
        st.rerun()

    st.caption(f"Atualização automática: {'ATIVA' if auto_refresh_enabled else 'PAUSADA'}")
