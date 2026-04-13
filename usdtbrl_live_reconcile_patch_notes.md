# Patch: startup reconcile fail-closed em live

Arquivos alterados:
- `smartcrypto/config.py`
- `smartcrypto/runtime/orchestrator.py`
- `tests/unit/test_startup_reconcile.py`

Mudanças:
- adiciona `runtime.startup_reconcile_fail_closed: true` ao default config;
- faz `run_startup_reconcile()` tratar `needs_action=True` como falha real;
- em falha de startup reconcile:
  - marca `live_reconcile_required = true`
  - marca `paused = true`
  - grava `startup_reconcile_failed` na auditoria
  - relança erro em live quando `startup_reconcile_fail_closed` estiver ativo;
- adiciona testes para:
  - fail-closed por mismatch
  - modo configurável sem raise
  - caminho de sucesso

Validação:
- `pytest -q tests/unit/test_startup_reconcile.py`
- `pytest -q`

Resultado:
- suíte verde no snapshot patchado.
