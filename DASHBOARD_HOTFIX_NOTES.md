# Dashboard hotfix

- Corrigido `NameError: cache_symbol_token` na aba Mercado ao clicar em Atualizar.
- Causa: `dashboard_app.py` usava `cache_symbol_token(...)` sem importar a função de `smartcrypto.runtime.cache`.
- Patch aplicado: import explícito restaurado.
