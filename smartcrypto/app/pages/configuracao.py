from __future__ import annotations

from typing import Any


def render(cfg: dict[str, Any], ui: Any) -> None:
    import pandas as pd
    import streamlit as st

    st.subheader("Configuração")
    with st.form("config_form"):
        c1, c2, c3 = st.columns(3)
        mode = c1.selectbox("Modo", ["dry_run", "live"], index=0 if str(cfg.get("execution", {}).get("mode", "dry_run")) == "dry_run" else 1)
        symbol = c2.text_input("Símbolo", value=str(cfg.get("market", {}).get("symbol", "USDT/BRL")))
        valid_timeframes = ["1m", "5m", "15m", "1h", "12h", "1d"]
        current_timeframe = str(cfg.get("market", {}).get("timeframe", "15m"))
        timeframe = c3.selectbox("Timeframe base", valid_timeframes, index=valid_timeframes.index(current_timeframe if current_timeframe in valid_timeframes else "15m"))

        p1, p2, p3 = st.columns(3)
        initial_cash = p1.number_input("Capital inicial BRL", min_value=0.0, value=ui.safe_float(cfg.get("portfolio", {}).get("initial_cash_brl", 10000.0)), step=100.0)
        max_open = p2.number_input("Máximo aberto BRL", min_value=0.0, value=ui.safe_float(cfg.get("risk", {}).get("max_open_brl", 2500.0)), step=50.0)
        max_daily_loss = p3.number_input("Perda diária máxima BRL", min_value=0.0, value=ui.safe_float(cfg.get("risk", {}).get("max_daily_loss_brl", 400.0)), step=10.0)

        s1, s2, s3, s4 = st.columns(4)
        first_buy = s1.number_input("Primeira compra BRL", min_value=0.0, value=ui.safe_float(cfg.get("strategy", {}).get("first_buy_brl", 25.0)), step=1.0)
        max_cycle = s2.number_input("Máximo por ciclo BRL", min_value=0.0, value=ui.safe_float(cfg.get("strategy", {}).get("max_cycle_brl", 2500.0)), step=50.0)
        take_profit = s3.number_input("Take profit %", min_value=0.0, value=ui.safe_float(cfg.get("strategy", {}).get("take_profit_pct", 0.65)), step=0.01, format="%.4f")
        min_profit = s4.number_input("Lucro mínimo BRL", min_value=0.0, value=ui.safe_float(cfg.get("strategy", {}).get("min_profit_brl", 0.15)), step=0.01, format="%.4f")

        t1, t2, t3, t4 = st.columns(4)
        trailing_enabled = t1.checkbox("Trailing ativo", value=bool(cfg.get("strategy", {}).get("trailing_enabled", True)))
        trailing_activation = t2.number_input("Trailing activation %", min_value=0.0, value=ui.safe_float(cfg.get("strategy", {}).get("trailing_activation_pct", 0.45)), step=0.01, format="%.4f")
        trailing_callback = t3.number_input("Trailing callback %", min_value=0.0, value=ui.safe_float(cfg.get("strategy", {}).get("trailing_callback_pct", 0.18)), step=0.01, format="%.4f")
        stop_loss = t4.number_input("Stop loss %", min_value=0.0, value=ui.safe_float(cfg.get("strategy", {}).get("stop_loss_pct", 2.4)), step=0.01, format="%.4f")

        e1, e2, e3, e4 = st.columns(4)
        reprice_wait = e1.number_input("Reprice wait s", min_value=1, value=ui.safe_int(cfg.get("execution", {}).get("reprice_wait_seconds", 10)), step=1)
        reprice_attempts = e2.number_input("Reprice attempts", min_value=1, value=ui.safe_int(cfg.get("execution", {}).get("reprice_attempts", 6)), step=1)
        entry_fallback = e3.checkbox("Entry fallback market", value=bool(cfg.get("execution", {}).get("entry_fallback_market", True)))
        stop_loss_market = e4.checkbox("Stop loss em market", value=bool(cfg.get("strategy", {}).get("stop_loss_market", True)))

        submit = st.form_submit_button("Salvar configuração", width="stretch")
        if submit:
            cfg["execution"]["mode"] = mode
            cfg["market"]["symbol"] = symbol
            cfg["market"]["timeframe"] = timeframe
            cfg["portfolio"]["initial_cash_brl"] = float(initial_cash)
            cfg["risk"]["max_open_brl"] = float(max_open)
            cfg["risk"]["max_daily_loss_brl"] = float(max_daily_loss)
            cfg["strategy"]["first_buy_brl"] = float(first_buy)
            cfg["strategy"]["max_cycle_brl"] = float(max_cycle)
            cfg["strategy"]["take_profit_pct"] = float(take_profit)
            cfg["strategy"]["min_profit_brl"] = float(min_profit)
            cfg["strategy"]["trailing_enabled"] = bool(trailing_enabled)
            cfg["strategy"]["trailing_activation_pct"] = float(trailing_activation)
            cfg["strategy"]["trailing_callback_pct"] = float(trailing_callback)
            cfg["strategy"]["stop_loss_pct"] = float(stop_loss)
            cfg["strategy"]["stop_loss_market"] = bool(stop_loss_market)
            cfg["execution"]["reprice_wait_seconds"] = int(reprice_wait)
            cfg["execution"]["reprice_attempts"] = int(reprice_attempts)
            cfg["execution"]["entry_fallback_market"] = bool(entry_fallback)
            cfg["execution"]["exit_fallback_market"] = False
            ui.save_cfg(cfg)
            st.success("Configuração salva com sucesso.")

    ramps = pd.DataFrame(cfg.get("strategy", {}).get("ramps", []) or [])
    st.markdown("#### Ramps")
    if ramps.empty:
        st.info("Sem ramps configuradas.")
    else:
        st.dataframe(ramps, width="stretch", hide_index=True)
