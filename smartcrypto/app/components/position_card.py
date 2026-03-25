from __future__ import annotations

from typing import Any, Callable


def render(
    status: dict[str, Any],
    *,
    format_money: Callable[[Any], str],
    safe_float: Callable[..., float],
    safe_int: Callable[..., int],
) -> None:
    import streamlit as st

    position = status.get("position", {}) or {}
    current_price = safe_float(status.get("price_brl", 0.0))
    avg_price = safe_float(position.get("avg_price_brl", 0.0))
    qty = safe_float(position.get("qty_usdt", 0.0))
    current_pnl = ((current_price - avg_price) * qty) if avg_price > 0 and qty > 0 else 0.0
    pnl_color = "#15803d" if current_pnl >= 0 else "#b91c1c"
    rows = [
        ("Status", position.get("status", "flat")),
        ("Preço médio", format_money(avg_price)),
        ("Preço atual", format_money(current_price)),
        (
            "PnL atual x preço médio",
            f'<span style="font-weight:900;color:{pnl_color}">{format_money(current_pnl)}</span>',
        ),
        ("BRL gasto", format_money(position.get("brl_spent", 0.0))),
        ("Take Profit", format_money(position.get("tp_price_brl", 0.0))),
        ("Stop", format_money(position.get("stop_price_brl", 0.0))),
        ("Rampa atual", str(safe_int(position.get("safety_count", 0)))),
        ("Regime", str(position.get("regime", "sideways"))),
        ("Trailing", "ATIVO" if safe_int(position.get("trailing_active", 0)) else "OFF"),
        ("Âncora trailing", format_money(position.get("trailing_anchor_brl", 0.0))),
    ]
    body = "".join(f"<tr><td>{label}</td><td>{value}</td></tr>" for label, value in rows)
    st.markdown(
        f"""
        <table class="sc-table">
            <thead><tr><th>Campo</th><th>Valor</th></tr></thead>
            <tbody>{body}</tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )
