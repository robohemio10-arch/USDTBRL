from __future__ import annotations

import pandas as pd


def render(df: pd.DataFrame, *, empty_message: str) -> None:
    import streamlit as st

    if df.empty:
        st.info(empty_message)
        return
    st.dataframe(df, width="stretch", hide_index=True)
