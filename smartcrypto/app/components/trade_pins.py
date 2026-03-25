from __future__ import annotations

import pandas as pd


def render_table(df: pd.DataFrame, *, title: str, columns: list[str]) -> None:
    import streamlit as st

    st.markdown(f"#### {title}")
    if df.empty:
        st.info("Sem compras ou vendas executadas dentro da janela do gráfico.")
        return
    preview = df.copy()
    if "created_at" in preview.columns:
        preview["created_at"] = pd.to_datetime(preview["created_at"], errors="coerce", utc=True)
        preview["created_at"] = preview["created_at"].dt.strftime("%d/%m/%Y %H:%M:%S")
    cols_keep = [column for column in columns if column in preview.columns]
    st.dataframe(preview[cols_keep].tail(20).iloc[::-1], width="stretch", hide_index=True)
