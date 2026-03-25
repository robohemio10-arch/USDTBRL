from __future__ import annotations

from typing import Any


def render(cfg: dict[str, Any], status: dict[str, Any], ui: Any) -> None:
    import streamlit as st

    st.subheader("Proteção operacional")
    st.info("Esta aba mostra as proteções do modo live. Locks travam envio duplicado; reconciliações comparam estado local x exchange; mismatches são divergências encontradas; proteção do banco indica que o SQLite está sendo usado com trilha de auditoria e controles de integridade.")
    locks = ui.dispatch_locks_df(cfg)
    recon = ui.reconciliation_df(cfg)
    health = status.get("health", {}) or {}
    portfolio = status.get("portfolio", {}) or {}

    if not locks.empty and "status" in locks.columns:
        active_locks = int(locks["status"].astype(str).str.lower().isin(ui.ACTIVE_DISPATCH_LOCK_STATUSES).sum())
    else:
        active_locks = int(len(locks))

    top = st.columns(5)
    top[0].metric("Locks ativos", str(active_locks))
    top[1].metric("Reconciliações", str(len(recon)))
    mismatches = int((recon["status"].astype(str).str.lower() != "ok").sum()) if not recon.empty and "status" in recon.columns else 0
    top[2].metric("Divergências", str(mismatches))
    top[3].metric("Saúde", str(health.get("status", "unknown")).upper())
    top[4].metric("Drawdown", f"{float(portfolio.get('drawdown_pct', 0.0) or 0.0):.2f}%")

    explain = [
        {
            "Campo": "Locks ativos",
            "Para que serve": "Evitar envio duplicado da mesma ordem enquanto uma tentativa ainda está em andamento.",
        },
        {
            "Campo": "Reconciliações",
            "Para que serve": "Registrar comparações entre o estado local do bot e o que realmente existe na Binance.",
        },
        {
            "Campo": "Divergências",
            "Para que serve": "Mostrar quantas reconciliações encontraram inconsistências que exigem atenção.",
        },
        {
            "Campo": "Proteção do banco",
            "Para que serve": "Indicar que o banco live está sendo usado com auditoria, trilhas de eventos e tabelas de controle.",
        },
    ]
    st.dataframe(explain, width="stretch", hide_index=True)

    left, right = st.columns(2)
    with left:
        st.markdown("#### Locks de despacho")
        if locks.empty:
            st.info("Sem locks registrados.")
        else:
            st.dataframe(locks, width="stretch", hide_index=True)
    with right:
        st.markdown("#### Auditoria de reconciliação")
        if recon.empty:
            st.info("Sem auditoria registrada.")
        else:
            st.dataframe(recon, width="stretch", hide_index=True)
