# Arquitetura do Projeto

---

## Visão geral

O projeto está organizado em camadas bem definidas:

- **domain** → regras de negócio
- **execution** → execução de ordens
- **runtime** → orquestração do sistema
- **research** → simulação, otimização e IA
- **state** → persistência e estado
- **infra** → integrações externas
- **app** → dashboard

---

## Estrutura

```
smartcrypto/
  domain/
  execution/
  runtime/
  research/
  state/
  infra/
  app/
```

---

## Caminhos canônicos

- Config: `config/config.yml`
- Runtime: `smartcrypto.runtime.orchestrator`
- Compat runtime: `smartcrypto.runtime.bot_runtime`
- Binance Adapter: `smartcrypto.infra.binance_adapter`
- Estado: `smartcrypto/state/*`
- Store legado: `smartcrypto.state.store`

---

## Princípios

- Separação clara de responsabilidades
- Código modular e testável
- Baixo acoplamento
- Compatibilidade controlada durante transição

---

## Regra principal

Todas as novas funcionalidades devem ser implementadas apenas nos caminhos canônicos.

---

## Estado atual

Arquitetura alvo já implementada com compatibilidade legada preservada.
