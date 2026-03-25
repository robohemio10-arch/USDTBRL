from __future__ import annotations

from typing import Any


def render(cfg: dict[str, Any], ui: Any) -> None:
    import streamlit as st

    st.subheader("Banco de dados")
    st.info("A aba DB serve para inspeção técnica do SQLite do robô: posição, trades, ciclos, flags, locks e auditoria. É útil para diagnóstico, conferência e suporte.")
    tables = ui.list_tables(cfg)
    info_cols = st.columns(3)
    info_cols[0].metric("Arquivo DB", ui.db_path_from_cfg(cfg).name)
    info_cols[1].metric("Tabelas", str(len(tables)))
    info_cols[2].metric("Existe", "SIM" if ui.db_path_from_cfg(cfg).exists() else "NÃO")

    if not tables:
        st.info("Banco ainda não existe ou está vazio.")
        return

    table = st.selectbox("Tabela", tables, index=0)
    limit = st.selectbox("Linhas", [50, 100, 200, 500], index=1)
    df = ui.read_table(cfg, table, int(limit))
    if df.empty:
        st.info("Sem dados para mostrar.")
    else:
        st.dataframe(df, width="stretch", hide_index=True)
