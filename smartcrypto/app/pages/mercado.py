from __future__ import annotations

from typing import Any

from smartcrypto.app.components import candlestick, trade_pins


def render(cfg: dict[str, Any], status: dict[str, Any], ui: Any) -> None:
    import pandas as pd
    import streamlit as st

    st.subheader("Mercado")
    interval_label = st.radio(
        "Intervalo",
        options=list(ui.interval_map().keys()),
        horizontal=True,
        key="market_interval",
    )

    if st.button("Baixar/atualizar 30 dias", key="market_backfill_button", width="content"):
        written = ui.backfill_all_market_caches(cfg, days=30)
        if written:
            st.success(f"Cache atualizado em {len(written)} intervalo(s).")
        else:
            st.warning("Não foi possível atualizar o cache agora.")

    df = ui.load_chart_df(cfg, interval_label)
    cache_meta = ui.interval_map()[interval_label]
    cache_code = str(cache_meta["code"])
    cache_path = ui.market_cache_file(cfg, cache_code) if cache_code not in {"7d", "30d"} else ui.market_cache_file(cfg, "1d")

    if df.empty:
        st.warning(
            "Sem cache local para esse intervalo. Execute: python scripts/backfill_market_cache.py --config config/config.yml"
        )
        fallback_label = ui.summary_market_interval_label(cfg)
        if fallback_label != interval_label:
            df = ui.load_chart_df(cfg, fallback_label)
            if not df.empty:
                st.caption(
                    f"Mostrando fallback do intervalo {fallback_label} até o cache principal ser preenchido."
                )
                interval_label = fallback_label
        if df.empty:
            return

    bars = ui.market_visible_bars_for_interval(interval_label)
    df = df.tail(bars).copy()

    last = df.iloc[-1]
    first_visible = df.iloc[0]
    high_visible = float(pd.to_numeric(df["high"], errors="coerce").max())
    low_visible = float(pd.to_numeric(df["low"], errors="coerce").min())
    change_pct = ((ui.safe_float(last["close"]) / max(ui.safe_float(first_visible["open"]), 1e-9)) - 1.0) * 100.0

    metrics = st.columns(5)
    metrics[0].metric("Último fechamento", ui.format_money(last["close"]))
    metrics[1].metric("Variação janela", f"{change_pct:.2f}%")
    metrics[2].metric("Máxima", ui.format_money(high_visible))
    metrics[3].metric("Mínima", ui.format_money(low_visible))
    metrics[4].metric("Velas visíveis", str(len(df)))
    st.caption(f"Fonte local: {cache_path}")

    executions = ui.execution_markers_df(cfg, limit=1000)
    visible_executions = ui.filter_executions_for_chart_window(executions, df, interval_label)
    position = status.get("position", {}) or {}
    figure = ui.build_market_figure(
        df=df,
        trades=executions,
        position=position,
        title=f"USDT/BRL • {interval_label}",
        show_tp_stop=True,
        white_theme=True,
        interval_label=interval_label,
    )
    figure.update_layout(height=680, margin=dict(l=10, r=10, t=38, b=10))
    candlestick.render(figure)

    if visible_executions.empty:
        st.info("Nenhuma compra ou venda executada caiu dentro da janela visível do gráfico.")
    else:
        st.caption(f"Execuções visíveis no gráfico: {len(visible_executions)}")

    lower_left, lower_right = st.columns([1.0, 1.0])
    with lower_left:
        st.markdown("#### Últimas velas")
        preview = df[["ts", "open", "high", "low", "close", "volume"]].copy()
        preview["ts"] = preview["ts"].dt.strftime("%d/%m/%Y %H:%M")
        st.dataframe(preview.tail(12).iloc[::-1], width="stretch", hide_index=True)
    with lower_right:
        trade_pins.render_table(
            visible_executions,
            title="Negociações visíveis no gráfico",
            columns=["created_at", "side", "qty_usdt", "price_brl", "brl_value", "fee_brl", "source"],
        )
