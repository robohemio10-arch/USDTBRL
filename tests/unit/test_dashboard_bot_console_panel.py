from smartcrypto.app.pages import operacoes


def test_render_console_bot_panel_html_colors_negative_and_positive() -> None:
    html = operacoes.render_console_bot_panel_html(
        {
            "symbol": "USDT/BRL",
            "mode": "paper",
            "run_active": True,
            "entry_price_brl": 5.2,
            "ramp_number": 0,
            "avg_price_brl": 5.21,
            "current_price_brl": 5.19,
            "pnl_pct": -0.18,
            "closed_cycles": 1,
            "invested_this_cycle_brl": 60.06,
            "realized_profit_brl": 10.5,
            "total_spent_all_cycles_brl": 120.12,
        }
    )
    assert "sc-console-panel" in html
    assert "sc-console-neg" in html
    assert "sc-console-pos" in html
    assert "PNL em %" in html
    assert "Lucro total ciclos" in html
