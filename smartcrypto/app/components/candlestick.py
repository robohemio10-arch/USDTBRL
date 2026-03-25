from __future__ import annotations


def render(figure, *, height: int | None = None) -> None:
    import streamlit as st

    if height is not None:
        figure.update_layout(height=height)
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
