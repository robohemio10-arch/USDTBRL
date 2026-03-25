# Legacy Compatibility

Este documento descreve os componentes mantidos temporariamente por compatibilidade.

---

## Componentes legados

- `config.yml`
- `smartcrypto/infra/binance.py`
- `smartcrypto/state/store.py`
- `smartcrypto/runtime/bot_runtime.py`

---

## Motivo

Esses componentes ainda existem para:

- preservar scripts antigos
- evitar quebra de imports
- manter operação estável durante a transição

---

## Caminhos canônicos

Novos desenvolvimentos devem usar:

- Config: `config/config.yml`
- Binance: `smartcrypto.infra.binance_adapter`
- Runtime: `smartcrypto.runtime.orchestrator`
- Estado: `smartcrypto/state/*`

---

## Regras

- ❌ Não adicionar novas funcionalidades nesses arquivos
- ✅ Todo código novo deve usar os caminhos canônicos
- ❌ Não criar dependências novas com legado

---

## Remoção futura

Esses componentes poderão ser removidos quando:

- não houver mais uso interno
- scripts estiverem migrados
- testes não dependerem mais deles

---

## Status

Compatibilidade controlada e documentada.
