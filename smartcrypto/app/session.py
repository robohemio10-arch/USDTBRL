from __future__ import annotations

from typing import Callable

PAGE_OPTIONS = [
    "Resumo",
    "Mercado",
    "Operações",
    "Configuração",
    "NTFY",
    "Proteção",
    "DB",
    "IA & Rollout",
]

AUTO_REFRESH_PAGES = {"Resumo", "Mercado", "Proteção", "DB"}


def ensure_session_defaults() -> None:
    import streamlit as st

    st.session_state.setdefault("auto_refresh_enabled", True)
    st.session_state.setdefault("nav_page", "Resumo")
    st.session_state.setdefault("market_interval", "1 hora")


def current_page(
    query_getter: Callable[[str, str], str],
    page_options: list[str] | None = None,
) -> str:
    import streamlit as st

    options = page_options or PAGE_OPTIONS
    current = query_getter("page", st.session_state.get("nav_page", "Resumo"))
    if current == "Hardening":
        current = "Proteção"
    if current not in options:
        current = "Resumo"
    st.session_state["nav_page"] = current
    return current


def set_current_page(value: str, query_setter: Callable[[str, str], None]) -> None:
    import streamlit as st

    if value not in PAGE_OPTIONS:
        return
    st.session_state["nav_page"] = value
    query_setter("page", value)


def auto_refresh_enabled() -> bool:
    import streamlit as st

    return bool(st.session_state.get("auto_refresh_enabled", True))


def set_auto_refresh_enabled(value: bool) -> None:
    import streamlit as st

    st.session_state["auto_refresh_enabled"] = bool(value)
