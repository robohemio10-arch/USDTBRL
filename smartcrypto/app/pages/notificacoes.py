from __future__ import annotations

from typing import Any


def render(cfg: dict[str, Any], ui: Any) -> None:
    import pandas as pd
    import streamlit as st

    st.subheader("NTFY")
    st.info("Configure o servidor e o tópico do NTFY nesta tela. A atualização automática fica desligada nesta aba para não atrapalhar a digitação.")
    env_path = ui.dotenv_path_from_cfg(ui.config_path())
    env_map = ui.load_dotenv_map(env_path)
    ntfy_cfg = cfg.get("notifications", {}).get("ntfy", {}) or {}

    with st.form("ntfy_form"):
        n1, n2, n3 = st.columns(3)
        enabled = n1.checkbox("Habilitado", value=bool(ntfy_cfg.get("enabled", False)), key="ntfy_enabled")
        sales_enabled = n2.checkbox("Notificar vendas", value=bool(ntfy_cfg.get("sales_enabled", True)), key="ntfy_sales_enabled")
        daily_enabled = n3.checkbox("Relatório diário", value=bool(ntfy_cfg.get("daily_report_enabled", True)), key="ntfy_daily_enabled")

        n4, n5 = st.columns(2)
        server = n4.text_input("Servidor", value=env_map.get("NTFY_SERVER", ui.resolve_env("NTFY_SERVER", "https://ntfy.sh", dotenv_path=env_path)), key="ntfy_server")
        topic = n5.text_input("Tópico", value=env_map.get("NTFY_TOPIC", ui.resolve_env("NTFY_TOPIC", "", dotenv_path=env_path)), key="ntfy_topic", placeholder="ex: smartcrypto-alertas")

        n6, n7, n8 = st.columns(3)
        token = n6.text_input("Token", value=env_map.get("NTFY_TOKEN", ""), type="password", key="ntfy_token")
        username = n7.text_input("Usuário", value=env_map.get("NTFY_USERNAME", ""), key="ntfy_username")
        password = n8.text_input("Senha", value=env_map.get("NTFY_PASSWORD", ""), type="password", key="ntfy_password")

        n9, n10, n11, n12 = st.columns(4)
        report_hour = n9.number_input("Hora do relatório", min_value=0, max_value=23, value=ui.safe_int(ntfy_cfg.get("daily_report_hour", 20)), key="ntfy_report_hour")
        report_minute = n10.number_input("Minuto do relatório", min_value=0, max_value=59, value=ui.safe_int(ntfy_cfg.get("daily_report_minute", 0)), key="ntfy_report_minute")
        notify_live = n11.checkbox("Enviar em LIVE", value=bool(ntfy_cfg.get("notify_live", True)), key="ntfy_notify_live")
        notify_paper = n12.checkbox("Enviar em PAPEL", value=bool(ntfy_cfg.get("notify_paper", True)), key="ntfy_notify_paper")

        save_ntfy = st.form_submit_button("Salvar NTFY", width="stretch")
        if save_ntfy:
            cfg.setdefault("notifications", {}).setdefault("ntfy", {})
            cfg["notifications"]["ntfy"].update(
                {
                    "enabled": bool(enabled),
                    "sales_enabled": bool(sales_enabled),
                    "daily_report_enabled": bool(daily_enabled),
                    "daily_report_hour": int(report_hour),
                    "daily_report_minute": int(report_minute),
                    "notify_live": bool(notify_live),
                    "notify_paper": bool(notify_paper),
                }
            )
            ui.save_cfg(cfg)
            env_map.update(
                {
                    "NTFY_SERVER": server,
                    "NTFY_TOPIC": topic,
                    "NTFY_TOKEN": token,
                    "NTFY_USERNAME": username,
                    "NTFY_PASSWORD": password,
                }
            )
            ui.save_dotenv_map(env_path, env_map)
            st.success("Configuração NTFY salva com sucesso.")
            st.rerun()

    st.caption("Para testar, marque Habilitado = ligado e preencha pelo menos o campo Tópico.")

    test_cols = st.columns([1, 3])
    if test_cols[0].button("Enviar teste", width="stretch"):
        try:
            client = ui.NtfyClient(cfg.get("notifications", {}).get("ntfy", {}) or {})
            client.publish(title="Teste SmartCrypto", message="Teste manual enviado pelo dashboard.", priority="default")
            st.success("Teste enviado com sucesso.")
        except Exception as exc:
            st.error(f"Falha ao enviar NTFY: {exc}")

    st.dataframe(
        pd.DataFrame(
            [
                {"Campo": "Servidor", "Valor": ui.resolve_env("NTFY_SERVER", "https://ntfy.sh", dotenv_path=env_path)},
                {"Campo": "Tópico", "Valor": ui.resolve_env("NTFY_TOPIC", "", dotenv_path=env_path)},
                {"Campo": "Token", "Valor": "••••••" if ui.resolve_env("NTFY_TOKEN", "", dotenv_path=env_path) else ""},
                {"Campo": "Usuário", "Valor": ui.resolve_env("NTFY_USERNAME", "", dotenv_path=env_path)},
                {"Campo": "Senha", "Valor": "••••••" if ui.resolve_env("NTFY_PASSWORD", "", dotenv_path=env_path) else ""},
            ]
        ),
        width="stretch",
        hide_index=True,
    )
