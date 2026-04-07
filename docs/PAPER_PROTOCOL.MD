# PAPER_PROTOCOL

- protocol_version: paper-v1
- profile_id: paper_7d
- profile_version: 2026.03.26
- mode: paper
- live_trading_allowed: false

## Startup checklist

- Confirmar `config/config.yml`
- Confirmar `config/feature_flags.yaml`
- Confirmar `runtime.profile_frozen=true`
- Confirmar `runtime.experiment_profile=paper_7d`
- Confirmar `runtime.protocol_version=paper-v1`
- Confirmar `runtime.single_instance_enabled=true`
- Confirmar `execution.allow_live=false`
- Executar `python scripts/run_paper_preflight.py`
- Executar `python scripts/check_single_instance.py`

## Daily checklist

- Registrar `run_id`
- Registrar duração da sessão
- Registrar número de ciclos
- Registrar erros críticos
- Registrar divergências baseline vs IA
- Registrar veto/override da IA
- Registrar PnL e drawdown quando disponíveis
- Exportar resumo diário

## Stop criteria

- `preflight_failed`
- `duplicate_instance_blocked`
- `bot_tick_error` recorrente
- `circuit_breaker_paused`
- `reconcile_mismatch`
- `unexpected_shutdown`

## GO / NO-GO para live parcial

### GO
- 7 dias de paper com perfil oficial
- zero incidentes críticos sem explicação
- rastreabilidade íntegra por `run_id`
- IA observável com baseline real persistida
- export diário consistente

### NO-GO
- qualquer boot fora do perfil oficial
- qualquer instância duplicada
- sessões sem `run_id`
- ausência de artefatos diários

