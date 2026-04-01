# Hotfix

## Corrigido
- dashboard não reduz mais para layout centralizado após refresh/rerun
- lock stale em `data/runtime/instance.lock.json` e `paper_7d.lock.json` passa a ser limpo automaticamente quando o PID do arquivo não existe mais

## Arquivos alterados
- `smartcrypto/app/styles.py`
- `smartcrypto/runtime/instance_lock.py`
- `tests/unit/test_instance_lock.py`
- `tests/unit/test_dashboard_styles.py`

## Validação executada
- `pytest -q tests/unit/test_instance_lock.py tests/unit/test_dashboard_styles.py tests/integration/test_dashboard_imports.py tests/unit/test_dashboard_safety_helpers.py`
