from __future__ import annotations

from typing import Any


def render(cfg: dict[str, Any], status: dict[str, Any], ui: Any) -> None:
    import pandas as pd
    import streamlit as st

    st.subheader("Proteção operacional")
    st.info(
        "Esta aba mostra as proteções do modo live. Locks travam envio duplicado; "
        "reconciliações comparam estado local x exchange; mismatches são divergências "
        "encontradas; a identidade operacional do banco ajuda a impedir mistura paper/live."
    )
    locks = ui.dispatch_locks_df(cfg)
    recon = ui.reconciliation_df(cfg)
    health = status.get("health", {}) or {}
    portfolio = status.get("portfolio", {}) or {}
    operational_status = ui.load_operational_status(cfg, status)
    manifest = dict(operational_status.get("manifest", {}) or {})
    preflight = dict(operational_status.get("preflight", {}) or {})
    identity = ui.dashboard_db_identity(cfg)
    expected_mode = ui.normalized_execution_mode(cfg)

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

    identity_rows = [
        {"Campo": "Modo esperado", "Valor": expected_mode.upper()},
        {"Campo": "DB role", "Valor": str(identity.get("db_role", "n/d") or "n/d").upper()},
        {"Campo": "DB profile", "Valor": str(identity.get("db_profile_id", "n/d") or "n/d")},
        {"Campo": "DB symbol", "Valor": str(identity.get("db_symbol", "n/d") or "n/d")},
        {"Campo": "Manifest mode", "Valor": str(manifest.get("mode", "n/d") or "n/d").upper()},
        {"Campo": "Pré-flight", "Valor": str(preflight.get("status", "unknown")).upper()},
    ]
    st.markdown("#### Identidade operacional")
    st.dataframe(pd.DataFrame(identity_rows), width="stretch", hide_index=True)

    current_role = str(identity.get("db_role", "")).strip().lower()
    if current_role and current_role != expected_mode:
        st.error(
            f"Identidade operacional divergente: DB={current_role.upper()} enquanto a configuração está em {expected_mode.upper()}."
        )

    explain = [
        {
            "Campo": "Locks ativos",
            "Para que serve": "Evitar envio duplicado da mesma ordem enquanto uma tentativa ainda está em andamento.",
        },
        {
            "Campo": "Reconciliações",
            "Para que serve": "Registrar comparações entre o estado local do bot e o que realmente existe na exchange.",
        },
        {
            "Campo": "Divergências",
            "Para que serve": "Mostrar quantas reconciliações encontraram inconsistências que exigem atenção.",
        },
        {
            "Campo": "Identidade operacional",
            "Para que serve": "Garantir que o banco aberto pelo dashboard pertence ao papel correto: paper ou live.",
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
