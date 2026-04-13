from __future__ import annotations

from pathlib import Path
from typing import Any


def _normalized_mode(cfg: dict[str, Any]) -> str:
    mode = str(cfg.get("execution", {}).get("mode", "paper") or "paper").strip().lower()
    if mode == "dry_run":
        return "paper"
    return mode if mode in {"paper", "live"} else "paper"


def _config_is_live_profile(ui: Any) -> bool:
    try:
        path = Path(str(ui.config_path()))
        return path.name.lower() in {"live_100usdt.yml"}
    except Exception:
        return False


def _config_is_editable(cfg: dict[str, Any], ui: Any) -> bool:
    mode = _normalized_mode(cfg)
    if mode == "live":
        return False
    if bool(cfg.get("execution", {}).get("allow_live", False)):
        return False
    if _config_is_live_profile(ui):
        return False
    return True



def render(cfg: dict[str, Any], ui: Any) -> None:
    import pandas as pd
    import streamlit as st

    st.subheader("Configuração")
    normalized_mode = _normalized_mode(cfg)
    editable = _config_is_editable(cfg, ui)
    cfg_file = Path(str(ui.config_path())).name

    if editable:
        st.caption(
            f"Perfil carregado: {cfg_file}. Esta aba salva alterações apenas no perfil atual. "
            "Reinicie o bot para aplicar parâmetros de estratégia já em execução."
        )
    else:
        st.warning(
            "Este painel está em modo somente leitura para perfil live. "
            "Use o dashboard em paper para editar parâmetros e promova para live via arquivo/versionamento."
        )

    raw_ramps = cfg.get("strategy", {}).get("ramps", []) or []
    ramps_df = pd.DataFrame(raw_ramps)
    if ramps_df.empty:
        ramps_df = pd.DataFrame(
            [
                {"step_index": 1, "drop_pct": 0.35, "multiplier": 1.0},
                {"step_index": 2, "drop_pct": 0.70, "multiplier": 1.25},
            ]
        )
    if "step_index" not in ramps_df.columns:
        ramps_df["step_index"] = list(range(1, len(ramps_df) + 1))
    if "drop_pct" not in ramps_df.columns:
        ramps_df["drop_pct"] = 0.0
    if "multiplier" not in ramps_df.columns:
        ramps_df["multiplier"] = 1.0
    ramps_df = ramps_df[["step_index", "drop_pct", "multiplier"]].copy()

    with st.form("config_form"):
        c1, c2, c3 = st.columns(3)
        mode = c1.selectbox(
            "Modo",
            ["paper", "live"],
            index=0 if normalized_mode == "paper" else 1,
            disabled=not editable,
        )
        symbol = c2.text_input(
            "Símbolo",
            value=str(cfg.get("market", {}).get("symbol", "USDT/BRL")),
            disabled=not editable,
        )
        valid_timeframes = ["1m", "5m", "15m", "1h", "12h", "1d"]
        current_timeframe = str(cfg.get("market", {}).get("timeframe", "15m"))
        timeframe = c3.selectbox(
            "Timeframe base",
            valid_timeframes,
            index=valid_timeframes.index(current_timeframe if current_timeframe in valid_timeframes else "15m"),
            disabled=not editable,
        )

        p1, p2, p3 = st.columns(3)
        initial_cash = p1.number_input(
            "Capital inicial BRL",
            min_value=0.0,
            value=ui.safe_float(cfg.get("portfolio", {}).get("initial_cash_brl", 10000.0)),
            step=100.0,
            disabled=not editable,
        )
        max_open = p2.number_input(
            "Máximo aberto BRL",
            min_value=0.0,
            value=ui.safe_float(cfg.get("risk", {}).get("max_open_brl", 2500.0)),
            step=50.0,
            disabled=not editable,
        )
        max_daily_loss = p3.number_input(
            "Perda diária máxima BRL",
            min_value=0.0,
            value=ui.safe_float(cfg.get("risk", {}).get("max_daily_loss_brl", 400.0)),
            step=10.0,
            disabled=not editable,
        )

        s1, s2, s3, s4, s5 = st.columns(5)
        first_buy = s1.number_input(
            "Primeira compra BRL",
            min_value=0.0,
            value=ui.safe_float(cfg.get("strategy", {}).get("first_buy_brl", 25.0)),
            step=1.0,
            disabled=not editable,
        )
        max_cycle = s2.number_input(
            "Máximo por ciclo BRL",
            min_value=0.0,
            value=ui.safe_float(cfg.get("strategy", {}).get("max_cycle_brl", 2500.0)),
            step=50.0,
            disabled=not editable,
        )
        take_profit = s3.number_input(
            "Take profit %",
            min_value=0.0,
            value=ui.safe_float(cfg.get("strategy", {}).get("take_profit_pct", 0.65)),
            step=0.01,
            format="%.4f",
            disabled=not editable,
        )
        min_profit = s4.number_input(
            "Lucro mínimo BRL",
            min_value=0.0,
            value=ui.safe_float(cfg.get("strategy", {}).get("min_profit_brl", 0.15)),
            step=0.01,
            format="%.4f",
            disabled=not editable,
        )
        max_active_ramps = s5.number_input(
            "Ramps ativas",
            min_value=0,
            value=ui.safe_int(cfg.get("strategy", {}).get("max_active_ramps", 0)),
            step=1,
            disabled=not editable,
            help="0 = usa todas as ramps que couberem no ciclo. Qualquer valor > 0 limita exatamente quantas ramps podem ficar ativas no ciclo.",
        )

        t1, t2, t3, t4 = st.columns(4)
        trailing_enabled = t1.checkbox(
            "Trailing ativo",
            value=bool(cfg.get("strategy", {}).get("trailing_enabled", True)),
            disabled=not editable,
        )
        trailing_activation = t2.number_input(
            "Trailing activation %",
            min_value=0.0,
            value=ui.safe_float(cfg.get("strategy", {}).get("trailing_activation_pct", 0.45)),
            step=0.01,
            format="%.4f",
            disabled=not editable,
        )
        trailing_callback = t3.number_input(
            "Trailing callback %",
            min_value=0.0,
            value=ui.safe_float(cfg.get("strategy", {}).get("trailing_callback_pct", 0.18)),
            step=0.01,
            format="%.4f",
            disabled=not editable,
        )
        stop_loss = t4.number_input(
            "Stop loss %",
            min_value=0.0,
            value=ui.safe_float(cfg.get("strategy", {}).get("stop_loss_pct", 2.4)),
            step=0.01,
            format="%.4f",
            disabled=not editable,
        )

        e1, e2, e3, e4 = st.columns(4)
        reprice_wait = e1.number_input(
            "Reprice wait s",
            min_value=1,
            value=ui.safe_int(cfg.get("execution", {}).get("reprice_wait_seconds", 10)),
            step=1,
            disabled=not editable,
        )
        reprice_attempts = e2.number_input(
            "Reprice attempts",
            min_value=1,
            value=ui.safe_int(cfg.get("execution", {}).get("reprice_attempts", 6)),
            step=1,
            disabled=not editable,
        )
        entry_fallback = e3.checkbox(
            "Entry fallback market",
            value=bool(cfg.get("execution", {}).get("entry_fallback_market", True)),
            disabled=not editable,
        )
        stop_loss_market = e4.checkbox(
            "Stop loss em market",
            value=bool(cfg.get("strategy", {}).get("stop_loss_market", True)),
            disabled=not editable,
        )

        st.markdown("#### Ramps")
        st.caption(
            "Você controla aqui o gatilho (%) e o tamanho (multiplier) de cada rampa. "
            "O campo 'Ramps ativas' acima define quantas delas o bot pode usar por ciclo."
        )
        ramps_editor = st.data_editor(
            ramps_df,
            hide_index=True,
            num_rows="dynamic" if editable else "fixed",
            disabled=not editable,
            width="stretch",
            column_config={
                "step_index": st.column_config.NumberColumn("Rampa", min_value=1, step=1, format="%d"),
                "drop_pct": st.column_config.NumberColumn("Queda %", min_value=0.0001, step=0.01, format="%.4f"),
                "multiplier": st.column_config.NumberColumn("Multiplicador", min_value=0.0001, step=0.05, format="%.4f"),
            },
        )

        submit = st.form_submit_button("Salvar configuração", width="stretch", disabled=not editable)
        if submit:
            ramps_clean: list[dict[str, float]] = []
            seen_steps: set[int] = set()
            errors: list[str] = []
            editor_df = pd.DataFrame(ramps_editor).copy()

            if editor_df.empty:
                errors.append("Configure pelo menos uma rampa.")
            else:
                for _, row in editor_df.iterrows():
                    try:
                        step_index = int(row.get("step_index", 0))
                        drop_pct = float(row.get("drop_pct", 0.0))
                        multiplier = float(row.get("multiplier", 0.0))
                    except Exception:
                        errors.append("Há valores inválidos nas ramps.")
                        break
                    if step_index <= 0:
                        errors.append("Cada rampa precisa de step_index > 0.")
                    if step_index in seen_steps:
                        errors.append("Não pode haver step_index duplicado.")
                    seen_steps.add(step_index)
                    if drop_pct <= 0:
                        errors.append("Cada rampa precisa de drop_pct > 0.")
                    if multiplier <= 0:
                        errors.append("Cada rampa precisa de multiplier > 0.")
                    ramps_clean.append(
                        {
                            "step_index": step_index,
                            "drop_pct": round(drop_pct, 6),
                            "multiplier": round(multiplier, 6),
                        }
                    )

            ramps_clean.sort(key=lambda item: int(item["step_index"]))

            if errors:
                for message in errors:
                    st.error(message)
            else:
                cfg["execution"]["mode"] = mode
                cfg["execution"]["allow_live"] = bool(mode == "live")
                cfg["market"]["symbol"] = symbol
                cfg["market"]["timeframe"] = timeframe
                cfg["portfolio"]["initial_cash_brl"] = float(initial_cash)
                cfg["risk"]["max_open_brl"] = float(max_open)
                cfg["risk"]["max_daily_loss_brl"] = float(max_daily_loss)
                cfg["strategy"]["first_buy_brl"] = float(first_buy)
                cfg["strategy"]["max_cycle_brl"] = float(max_cycle)
                cfg["strategy"]["take_profit_pct"] = float(take_profit)
                cfg["strategy"]["min_profit_brl"] = float(min_profit)
                cfg["strategy"]["max_active_ramps"] = int(max_active_ramps)
                cfg["strategy"]["trailing_enabled"] = bool(trailing_enabled)
                cfg["strategy"]["trailing_activation_pct"] = float(trailing_activation)
                cfg["strategy"]["trailing_callback_pct"] = float(trailing_callback)
                cfg["strategy"]["stop_loss_pct"] = float(stop_loss)
                cfg["strategy"]["stop_loss_market"] = bool(stop_loss_market)
                cfg["strategy"]["ramps"] = ramps_clean
                cfg["execution"]["reprice_wait_seconds"] = int(reprice_wait)
                cfg["execution"]["reprice_attempts"] = int(reprice_attempts)
                cfg["execution"]["entry_fallback_market"] = bool(entry_fallback)
                cfg["execution"]["exit_fallback_market"] = False
                ui.save_cfg(cfg)
                st.success(
                    "Configuração salva com sucesso. Reinicie o bot para aplicar as ramps e o limite de ramps ativas no runtime."
                )

    active_limit = ui.safe_int(cfg.get("strategy", {}).get("max_active_ramps", 0))
    if active_limit > 0:
        st.info(f"Ramps ativas por ciclo: {active_limit}. O bot vai usar no máximo esse número, respeitando também o teto financeiro do ciclo.")


