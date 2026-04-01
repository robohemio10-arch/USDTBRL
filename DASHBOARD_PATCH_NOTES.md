# Dashboard patch notes

## O que foi corrigido
- Aba **Configuração** atualizada de `dry_run/live` para `paper/live`.
- Dashboard em perfil **live** agora entra em **somente leitura** para edição de configuração.
- Banner e sidebar agora exibem:
  - perfil operacional
  - papel do banco (`PAPER` ou `LIVE`)
  - avisos de pré-flight e divergência de identidade
- Aba **Proteção** agora mostra identidade operacional do banco e alerta divergência paper/live.
- README atualizado com comandos explícitos de dashboard por perfil.

## Validação
- `pytest -q` verde no pacote final.
- Observação: o ambiente de build aqui não tem `streamlit` instalado, então o smoke real de UI não foi executado neste container.
- A dependência continua declarada em `requirements.txt` e `pyproject.toml`.


## Patch extra — layout da navegação e barra superior
- removida a dependência da sidebar como navegação principal
- adicionada navegação horizontal no topo com todas as abas
- sidebar mantida apenas como navegação complementar
- reduzido o header nativo do Streamlit para eliminar a barra branca superior que estava cobrindo conteúdo
- adicionada área de "Controles rápidos do dashboard" no corpo da página como fallback operacional
- validação executada:
  - `pytest -q tests/integration/test_dashboard_imports.py tests/unit/test_dashboard_safety_helpers.py tests/unit/test_runtime_status.py`
