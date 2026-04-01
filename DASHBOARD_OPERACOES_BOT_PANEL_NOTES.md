# Dashboard Operations Bot Panel Patch

Mudanças aplicadas:
- adicionada a tabela do bot em estilo console dentro da aba **Operações**
- tabela renderizada com layout semelhante ao terminal do bot
- atualização automática parcial a cada 5s usando `st.fragment` quando disponível
- removido o auto-refresh global da página **Operações** para evitar piscar toda a tela
- fallback estático quando a versão do Streamlit não suportar fragmento parcial

Arquivos alterados:
- `smartcrypto/app/pages/operacoes.py`
- `smartcrypto/app/session.py`
- `smartcrypto/app/styles.py`

Teste executado:
- `pytest -q tests/unit/test_dashboard_bot_console_panel.py tests/unit/test_dashboard_styles.py tests/integration/test_dashboard_imports.py`
