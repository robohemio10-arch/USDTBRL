from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from smartcrypto.research.ml_store import MLStore
from smartcrypto.research.reporting import generate_rollout_report


def _latest_payload(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {}
    value = df.iloc[0].get("payload_json", "{}")
    if isinstance(value, dict):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return {}


def _store_from_cfg(cfg: dict[str, Any]) -> MLStore:
    db_path = str(cfg.get("storage", {}).get("ml_store_path", "data/ml_store.sqlite"))
    return MLStore(db_path)


def _segment_frame(segment: dict[str, Any], key: str) -> pd.DataFrame:
    if not isinstance(segment, dict):
        return pd.DataFrame()
    return pd.DataFrame(segment.get(key, []))


def _render_quant_section(report: dict[str, Any]) -> None:
    quant = dict(report.get("latest_quant_validation", {}) or {})
    if not quant:
        st.caption("Validação quantitativa ainda não gerada.")
        return
    methods = dict(quant.get("methods", {}) or {})
    baseline = dict(methods.get("baseline", {}) or {})
    candidate = dict(methods.get("candidate", {}) or {})
    promotion = dict(quant.get("promotion", {}) or {})
    compare_cols = st.columns(2)
    with compare_cols[0]:
        st.markdown("#### Baseline")
        st.json(baseline)
    with compare_cols[1]:
        st.markdown("#### IA candidata")
        st.json(candidate)
    st.markdown("#### Promoção")
    st.json(promotion)
    segments = dict(quant.get("segments", {}) or {})
    seg_cols = st.columns(2)
    with seg_cols[0]:
        st.caption("Por regime")
        regime = pd.DataFrame(segments.get("by_regime", {}).get(methods.get("baseline_method", "heuristic"), []))
        regime_ai = pd.DataFrame(segments.get("by_regime", {}).get(methods.get("candidate_method", "ai"), []))
        if not regime.empty:
            st.dataframe(regime, use_container_width=True, hide_index=True)
        if not regime_ai.empty:
            st.dataframe(regime_ai, use_container_width=True, hide_index=True)
    with seg_cols[1]:
        st.caption("Por faixa horária")
        hour = pd.DataFrame(segments.get("by_hour", {}).get(methods.get("baseline_method", "heuristic"), []))
        hour_ai = pd.DataFrame(segments.get("by_hour", {}).get(methods.get("candidate_method", "ai"), []))
        if not hour.empty:
            st.dataframe(hour, use_container_width=True, hide_index=True)
        if not hour_ai.empty:
            st.dataframe(hour_ai, use_container_width=True, hide_index=True)


def render(cfg: dict[str, Any], status: dict[str, Any], ui: Any) -> None:
    st.subheader("IA & Rollout")
    st.info(
        "Esta aba mostra o estado da camada preditiva integrada ao runtime: gates de entrada, qualidade de execução, promoção por par/timeframe, calibração, comparativos por regime/faixa horária e validação quantitativa final."
    )
    store = _store_from_cfg(cfg)
    report = generate_rollout_report(store)
    ai_runtime = dict(status.get("ai_runtime", {}))
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Shadow runs", int(report.get("shadow_runs", 0)))
    c2.metric("Rollout events", int(report.get("rollout_events", 0)))
    c3.metric("Modelos", int(report.get("registered_models", 0)))
    c4.metric("Eval trades", int(report.get("evaluation_trade_rows", 0)))
    c5.metric("Gate runtime", "LIBERADO" if bool(ai_runtime.get("effective_entry_gate", False)) else "BLOQUEADO")

    st.markdown("### Estado atual do runtime")
    st.json(ai_runtime or {"enabled": False})

    latest_shadow = report.get("latest_shadow", {}) or _latest_payload(store.read_df("shadow_predictions", limit=1))
    latest_event = report.get("latest_event", {}) or _latest_payload(store.read_df("rollout_events", limit=1))
    validation = dict(latest_shadow.get("validation", {})) if isinstance(latest_shadow, dict) else {}

    overview, segments_tab, calibration_tab, quant_tab, registry_tab = st.tabs([
        "Visão geral",
        "Segmentação",
        "Calibração",
        "Validação Quant",
        "Registro",
    ])
    with overview:
        left, right = st.columns(2)
        with left:
            st.markdown("#### Último shadow")
            st.json(latest_shadow)
        with right:
            st.markdown("#### Último evento de rollout")
            st.json(latest_event)
        empirical = latest_shadow.get("empirical_execution", {}) if isinstance(latest_shadow, dict) else {}
        if empirical:
            st.markdown("#### Ground truth de execução (empírico)")
            st.json(empirical)

    with segments_tab:
        entry_segment = validation.get("entry_filter_segment_comparison", {})
        exec_segment = validation.get("execution_quality_segment_comparison", {})
        pos_segment = validation.get("position_manager_segment_comparison", {})
        for title, segment in [
            ("Entry Filter", entry_segment),
            ("Execution Quality", exec_segment),
            ("Position Manager", pos_segment),
        ]:
            st.markdown(f"#### {title}")
            c_left, c_right = st.columns(2)
            with c_left:
                regime_rows = _segment_frame(segment, "by_regime")
                st.caption("Por regime")
                if regime_rows.empty:
                    st.caption("Sem dados por regime.")
                else:
                    st.dataframe(regime_rows, use_container_width=True, hide_index=True)
            with c_right:
                hour_rows = _segment_frame(segment, "by_hour")
                st.caption("Por faixa horária")
                if hour_rows.empty:
                    st.caption("Sem dados por hora.")
                else:
                    st.dataframe(hour_rows, use_container_width=True, hide_index=True)

    with calibration_tab:
        calibration = report.get("calibration", {}) if isinstance(report, dict) else {}
        st.markdown("#### Métricas de calibração")
        cols = st.columns(3)
        for col, name in zip(cols, ["entry_filter", "execution_quality", "position_manager"], strict=False):
            with col:
                st.caption(name)
                st.json(calibration.get(name, {}))

    with quant_tab:
        _render_quant_section(report)

    with registry_tab:
        st.markdown("#### Registro de modelos")
        models_df = store.read_df("model_registry", limit=20)
        if models_df.empty:
            st.caption("Nenhum modelo registrado ainda.")
        else:
            st.dataframe(models_df[[c for c in models_df.columns if c != "artifact_json"]], use_container_width=True, hide_index=True)
        st.markdown("#### Relatórios quantitativos recentes")
        eval_df = store.read_df("evaluation_reports", limit=10)
        if eval_df.empty:
            st.caption("Nenhum relatório quantitativo salvo ainda.")
        else:
            st.dataframe(eval_df[[c for c in eval_df.columns if c != "payload_json"]], use_container_width=True, hide_index=True)
