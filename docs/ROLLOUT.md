# Rollout e Estado da Migração

---

## Status atual

- Arquitetura modular implementada
- Separação clara entre domain, execution, runtime e research
- Dashboard modularizado
- Runtime desacoplado

---

## Compatibilidade preservada

Componentes mantidos intencionalmente:

- `config.yml`
- `smartcrypto.infra.binance`
- `smartcrypto.state.store`
- `smartcrypto.runtime.bot_runtime`

---

## Regras atuais

- Código novo deve usar apenas caminhos canônicos
- Componentes legados não devem receber novas funcionalidades

---

## Caminhos canônicos

- Config: `config/config.yml`
- Runtime: `smartcrypto.runtime.orchestrator`
- Binance: `smartcrypto.infra.binance_adapter`
- Estado: `smartcrypto/state/*`

---

## Estado do repositório

- Snapshot limpo
- Logs removidos
- Caches removidos
- Estrutura organizada

---

## Próximo estágio

- Remoção gradual do legado
- Evolução de strategy e execution
- Expansão de research e IA
