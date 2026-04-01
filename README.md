# SmartCrypto USDT/BRL Bot

Bot profissional de compra e venda USDT/BRL na Binance, com arquitetura modular, execução endurecida e segregação operacional entre paper e live.

---

## Perfis operacionais

- Paper padrão: `config/config.yml`
- Paper 7d: `config/paper_7d.yml`
- Live: `config/live.yml`

`config/config.yml` agora é **paper-only** e usa banco paper dedicado.  
`config/live.yml` é o perfil explícito para operação live.

---

## Setup rápido

### 1. Criar arquivo `.env`

```bash
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
NTFY_TOPIC=...
```

### 2. Rodar migração do banco paper

```bash
python scripts/migrate_db.py --config config/config.yml
```

### 3. Verificar saúde do perfil paper

```bash
python scripts/healthcheck.py --config config/config.yml
```

### 4. Rodar o bot em paper

```bash
python bot.py --config config/config.yml
```

### 5. Rodar o bot em live

```bash
python bot.py --config config/live.yml
```

### 6. Rodar o dashboard em paper

```bash
streamlit run dashboard.py -- --config config/config.yml
```

### 7. Rodar o dashboard em live

```bash
streamlit run dashboard.py -- --config config/live.yml
```

---

## Regras operacionais

- Não usar banco live com perfil paper.
- Não usar `config.live.yml` em código novo. Ele permanece apenas por compatibilidade.
- Preflight agora falha se a identidade operacional do banco divergir do perfil carregado.
- Reconcile live agora é fail-closed para divergência material de posição.

---

## Arquitetura

- Runtime: `smartcrypto.runtime.orchestrator`
- Execução: `smartcrypto.execution`
- Estado: `smartcrypto.state`
- Research: `smartcrypto.research`

---

## Shadow Mode

```bash
python scripts/run_shadow_mode.py --config config/paper_7d.yml --force
```
