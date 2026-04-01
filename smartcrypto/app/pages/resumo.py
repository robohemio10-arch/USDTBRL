from __future__ import annotations

from typing import Any

from smartcrypto.app.components import candlestick, metrics_row, position_card


def render(cfg: dict[str, Any], status: dict[str, Any], ui: Any) -> None:
    import pandas as pd
    import streamlit as st

    position = status.get("position", {}) or {}
    portfolio = status.get("portfolio", {}) or {}
    flags = status.get("flags", {}) or {}
    hardening = status.get("live_hardening", {}) or {}

    ui.render_time_cards(cfg, status)

    panel = status.get("paper_panel", {}) or {}
    if panel:
        st.markdown("#### Painel operacional do paper")
        pnl_value = ui.safe_float(panel.get("pnl_pct", 0.0))
        pnl_text = f"{pnl_value:.2f}%"
        if pnl_value > 0:
            pnl_text = f":green[{pnl_text}]"
        elif pnl_value < 0:
            pnl_text = f":red[{pnl_text}]"
        panel_df = pd.DataFrame(
            [
                {
                    "Moeda/USDT/BRL": str(panel.get("symbol", "USDT/BRL") or "USDT/BRL"),
                    "Modo Paper/Live": str(panel.get("mode", "paper") or "paper").upper(),
                    "Run sim/não": "SIM" if bool(panel.get("run_active", False)) else "NÃO",
                    "Valor de entrada": ui.format_money(panel.get("entry_price_brl", 0.0)),
                    "Número da rampa": str(ui.safe_int(panel.get("ramp_number", 0))),
                    "Valor médio": ui.format_money(panel.get("avg_price_brl", 0.0)),
                    "Valor atual": ui.format_money(panel.get("current_price_brl", 0.0)),
                    "PNL em %": pnl_text,
                    "Número de ciclos já realizados": str(ui.safe_int(panel.get("closed_cycles", 0))),
                    "Valor empenhado neste ciclo": ui.format_money(panel.get("invested_this_cycle_brl", 0.0)),
                    "Lucro total de todos os ciclos": ui.format_money(panel.get("realized_profit_total_brl", 0.0)),
                    "Soma do montante empenhado em todos os ciclos": ui.format_money(panel.get("total_spent_all_cycles_brl", 0.0)),
                }
            ]
        )
        st.dataframe(panel_df, width="stretch", hide_index=True)

    metrics_row.render(
        [
            {"label": "Preço", "value": ui.format_money(status.get("price_brl", 0.0))},
            {"label": "Caixa", "value": ui.format_money(portfolio.get("cash_brl", status.get("cash_brl", 0.0)))},
            {"label": "Equity", "value": ui.format_money(portfolio.get("equity_brl", status.get("equity_brl", 0.0)))},
            {"label": "Posição USDT", "value": ui.format_qty(position.get("qty_usdt", 0.0))},
            {"label": "Valor da posição", "value": ui.format_money(portfolio.get("position_notional_brl", 0.0))},
            {"label": "Capital investido", "value": ui.format_money(portfolio.get("invested_brl", position.get("brl_spent", 0.0)))},
        ]
    )

    active_locks = hardening.get("active_dispatch_locks", []) or []
    metrics_row.render(
        [
            {"label": "Pausado", "value": "SIM" if bool(status.get("paused", False)) else "NÃO"},
            {
                "label": "Reconciliação pendente",
                "value": "SIM" if bool(flags.get("live_reconcile_required", False)) else "NÃO",
            },
            {"label": "Erros consecutivos", "value": str(ui.safe_int(flags.get("consecutive_error_count", 0)))},
            {"label": "Locks ativos", "value": str(len(active_locks))},
        ]
    )

    market_col, pos_col = st.columns([1.6, 1.0])
    with market_col:
        st.markdown("#### Mercado USDT/BRL")
        interval_label = ui.summary_market_interval_label(cfg)
        df = ui.load_chart_df(cfg, interval_label)
        if df.empty:
            st.info("Sem cache local de candles para o gráfico principal. Execute o backfill do cache.")
        else:
            executions = ui.execution_markers_df(cfg, limit=1000)
            figure = ui.build_market_figure(
                df=df,
                trades=executions,
                position=position,
                title=f"USDT/BRL • {interval_label}",
                show_tp_stop=False,
                interval_label=interval_label,
            )
            figure.update_layout(height=520, margin=dict(l=10, r=10, t=38, b=10))
            candlestick.render(figure)
    with pos_col:
        st.markdown("#### Posição atual")
        position_card.render(
            status,
            format_money=ui.format_money,
            safe_float=ui.safe_float,
            safe_int=ui.safe_int,
        )

    ui.render_trade_bank_chart(cfg)

    lower_left, lower_right = st.columns([1.2, 1])
    with lower_left:
        cycles = ui.cycles_df(cfg, limit=300)
        st.markdown("#### Ciclos recentes")
        if not cycles.empty and "pnl_brl" in cycles.columns:
            pnl = pd.to_numeric(cycles["pnl_brl"], errors="coerce").fillna(0.0)
            metrics_row.render(
                [
                    {"label": "PnL ciclos", "value": ui.format_money(float(pnl.sum()))},
                    {"label": "Ciclos positivos", "value": str(int((pnl > 0).sum()))},
                    {"label": "Ciclos negativos", "value": str(int((pnl < 0).sum()))},
                ]
            )
            preview_cols = [
                c
                for c in ["closed_at", "pnl_brl", "reason", "avg_entry_brl", "exit_price_brl"]
                if c in cycles.columns
            ]
            st.dataframe(cycles[preview_cols].head(15), width="stretch", hide_index=True)
        else:
            st.info("Sem ciclos suficientes para resumir.")
    with lower_right:
        st.markdown("#### Eventos recentes")
        events = ui.bot_events_df(cfg, limit=20)
        if events.empty:
            st.info("Sem eventos recentes.")
        else:
            preview_cols = [c for c in ["created_at", "level", "event_type", "message"] if c in events.columns]
            st.dataframe(events[preview_cols], width="stretch", hide_index=True)
