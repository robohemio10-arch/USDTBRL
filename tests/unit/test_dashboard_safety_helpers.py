from __future__ import annotations

import importlib
import sys
import types


def _install_streamlit_stubs() -> None:
    class _Sidebar:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def markdown(self, *args, **kwargs):
            return None

        def caption(self, *args, **kwargs):
            return None

    st = types.ModuleType("streamlit")
    st.set_page_config = lambda *args, **kwargs: None
    st.cache_data = lambda *args, **kwargs: (lambda fn: fn)
    st.markdown = lambda *args, **kwargs: None
    st.caption = lambda *args, **kwargs: None
    st.subheader = lambda *args, **kwargs: None
    st.info = lambda *args, **kwargs: None
    st.metric = lambda *args, **kwargs: None
    st.success = lambda *args, **kwargs: None
    st.warning = lambda *args, **kwargs: None
    st.error = lambda *args, **kwargs: None
    st.title = lambda *args, **kwargs: None
    st.columns = lambda n, **kwargs: [types.SimpleNamespace(metric=lambda *a, **k: None, button=lambda *a, **k: False) for _ in range(n)]
    st.button = lambda *args, **kwargs: False
    st.dataframe = lambda *args, **kwargs: None
    st.plotly_chart = lambda *args, **kwargs: None
    st.selectbox = lambda label, options, index=0, **kwargs: options[index]
    st.radio = lambda label, options, index=0, **kwargs: options[index]
    st.toggle = lambda *args, value=False, **kwargs: value
    st.query_params = {}
    st.sidebar = _Sidebar()
    sys.modules["streamlit"] = st

    components = types.ModuleType("streamlit.components.v1")
    components.html = lambda *args, **kwargs: None
    sys.modules["streamlit.components"] = types.ModuleType("streamlit.components")
    sys.modules["streamlit.components.v1"] = components


def _load_dashboard_module():
    _install_streamlit_stubs()
    sys.modules.pop("smartcrypto.app.dashboard_app", None)
    return importlib.import_module("smartcrypto.app.dashboard_app")


def test_normalized_execution_mode_maps_dry_run_to_paper() -> None:
    module = _load_dashboard_module()
    assert module.normalized_execution_mode({"execution": {"mode": "dry_run"}}) == "paper"
    assert module.normalized_execution_mode({"execution": {"mode": "paper"}}) == "paper"
    assert module.normalized_execution_mode({"execution": {"mode": "live"}}) == "live"


def test_dashboard_warnings_detect_live_and_preflight_issue(monkeypatch) -> None:
    module = _load_dashboard_module()
    monkeypatch.setattr(module, "config_path", lambda: types.SimpleNamespace(name="live.yml"))
    monkeypatch.setattr(
        module,
        "dashboard_db_identity",
        lambda cfg: {"db_role": "live", "db_profile_id": "live", "db_symbol": "USDT/BRL"},
    )
    warnings = module.dashboard_warnings(
        {"execution": {"mode": "live"}},
        {"preflight": {"status": "failed"}, "manifest": {"mode": "live"}},
    )
    assert any("LIVE" in item.upper() for item in warnings)
    assert any("PRÉ-FLIGHT" in item.upper() for item in warnings)


def test_dashboard_profile_summary_prefers_db_identity(monkeypatch) -> None:
    module = _load_dashboard_module()
    monkeypatch.setattr(
        module,
        "dashboard_db_identity",
        lambda cfg: {"db_role": "paper", "db_profile_id": "paper_7d", "db_symbol": "USDT/BRL"},
    )
    summary = module.dashboard_profile_summary(
        {"execution": {"mode": "paper"}, "market": {"symbol": "USDT/BRL"}},
        {"manifest": {"experiment_profile": "ignored"}},
    )
    assert summary["role"] == "PAPER"
    assert summary["profile"] == "paper_7d"
    assert summary["symbol"] == "USDT/BRL"
