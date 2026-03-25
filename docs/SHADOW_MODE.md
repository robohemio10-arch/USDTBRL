# Shadow Mode

O shadow mode roda em paralelo ao runtime live, mas sem disparar ordens. Nesta fase ele usa uma
heurística leve baseada em features, com objetivo de registrar previsões e comparar direção e erro.

## Como rodar

```bash
python scripts/run_shadow_mode.py --config config/config.yml --force
```

## Saída

O script devolve um payload JSON com:

- `enabled`
- `rows`
- `predictions`
- `metrics`
- `methodology`

Quando o modo está habilitado, os resultados também são persistidos em `research_runs`.

## Feature flag

A flag canônica é:

- `research.shadow_mode_enabled`
