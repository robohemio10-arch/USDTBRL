# PAPER_CHECKLIST

## Subida

- [ ] `config/paper_7d.yml` selecionado
- [ ] `config/feature_flags_paper_7d.yaml` selecionado
- [ ] `runtime.experiment_profile=paper_7d`
- [ ] `runtime.protocol_version=paper-v1`
- [ ] `runtime.profile_frozen=true`
- [ ] `runtime.single_instance_enabled=true`
- [ ] `execution.allow_live=false`
- [ ] preflight executado
- [ ] lock de instância validado

## Diário

- [ ] `run_id` visível
- [ ] uptime registrado
- [ ] ciclos registrados
- [ ] decisões IA registradas
- [ ] divergências baseline vs IA registradas
- [ ] incidentes críticos revisados
- [ ] resumo diário exportado

## Interrupção imediata

- [ ] `preflight_failed`
- [ ] `duplicate_instance_blocked`
- [ ] `circuit_breaker_paused`
- [ ] `reconcile_mismatch`
- [ ] `unexpected_shutdown`
