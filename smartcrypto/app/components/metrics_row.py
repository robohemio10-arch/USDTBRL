from __future__ import annotations

from typing import Any


def render(metrics: list[dict[str, Any]]) -> None:
    import streamlit as st

    columns = st.columns(len(metrics))
    for idx, metric in enumerate(metrics):
        delta = metric.get("delta")
        if delta is None:
            columns[idx].metric(str(metric["label"]), str(metric["value"]))
        else:
            columns[idx].metric(str(metric["label"]), str(metric["value"]), str(delta))
