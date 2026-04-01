# Sidebar + alerta operacional patch

Alterações aplicadas:
- Sidebar fixa com 5 botões operacionais:
  1. Ativar robô
  2. Pausar robô imediatamente
  3. Pausar auto-refresh
  4. Ativar auto-refresh
  5. Pausar robô após a venda
- Painel lateral com status do robô, auto-refresh e pausa após venda.
- Banner operacional no topo para destacar:
  - robô pausado
  - circuit breaker acionado
  - último erro recente
  - reconciliação pendente
- Suporte funcional para `pause_after_sell_requested`:
  - o botão arma/desarma a pausa
  - após a próxima venda, o bot pausa e limpa a flag
- CSS para manter sidebar visível e com largura estável.

Arquivos alterados:
- smartcrypto/app/components/refresh_control.py
- smartcrypto/app/dashboard_app.py
- smartcrypto/app/styles.py
- smartcrypto/execution/controls.py
- smartcrypto/runtime/status.py

Validação executada:
- py_compile nos arquivos alterados
