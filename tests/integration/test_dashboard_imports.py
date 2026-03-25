def test_dashboard_module_imports() -> None:
    import smartcrypto.app.components.candlestick
    import smartcrypto.app.components.metrics_row
    import smartcrypto.app.components.order_table
    import smartcrypto.app.components.position_card
    import smartcrypto.app.components.refresh_control
    import smartcrypto.app.components.trade_pins
    import smartcrypto.app.pages.banco_dados
    import smartcrypto.app.pages.configuracao
    import smartcrypto.app.pages.mercado
    import smartcrypto.app.pages.notificacoes
    import smartcrypto.app.pages.operacoes
    import smartcrypto.app.pages.resumo
    import smartcrypto.app.pages.saude_sistema
    import smartcrypto.app.session
    import smartcrypto.app.styles

    assert True


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


def test_dashboard_runtime_status_fallback_uses_portfolio_view(tmp_path) -> None:
    _install_streamlit_stubs()
    sys.modules.pop("smartcrypto.app.dashboard_app", None)
    module = importlib.import_module("smartcrypto.app.dashboard_app")
    cfg = {
        "storage": {"db_path": str(tmp_path / "dashboard.sqlite")},
        "portfolio": {"initial_cash_brl": 100.0},
        "dashboard": {"cache_dir": str(tmp_path / "cache")},
    }
    store = module.state_store(cfg)
    store.open_cycle(regime="sideways", entry_price_brl=5.0, qty_usdt=10.0, brl_spent=50.0)
    store.update_position(
        status="open",
        qty_usdt=10.0,
        brl_spent=50.0,
        avg_price_brl=5.0,
        realized_pnl_brl=2.5,
    )

    status = module.load_runtime_status(cfg)

    assert status["portfolio"]["cash_brl"] == 52.5
    assert status["portfolio"]["equity_brl"] == 52.5
    assert status["position"]["qty_usdt"] == 10.0
