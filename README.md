# SmartCrypto USDT/BRL Bot

Bot profissional de compra e venda USDT/BRL na Binance, com arquitetura modular, execução endurecida e segregação operacional entre paper e live.

---

## Perfis operacionais

- Paper padrão: `config/config.yml`
- Paper observação/compatibilidade: outros perfis versionados, quando existirem
- Live: `config/live_100usdt.yml`

`config/config.yml` é o perfil canônico de paper.  
`config/live_100usdt.yml` é o perfil canônico de live.

Os caches do dashboard e do healthcheck agora são segregados por perfil operacional para evitar contaminação cruzada entre paper e live.

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
python bot.py --config config/live_100usdt.yml
```

### 6. Rodar o dashboard em paper

```bash
streamlit run dashboard.py -- --config config/config.yml
```

### 7. Rodar o dashboard em live

```bash
streamlit run dashboard.py -- --config config/live_100usdt.yml
```

### 8. Atalho PowerShell para subir live

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_live_100usdt.ps1
```

---

## Regras operacionais

- Não usar banco live com perfil paper.
- Não usar banco paper com perfil live.
- `config/live_100usdt.yml` é o perfil live canônico.
- Preflight falha se a identidade operacional do banco divergir do perfil carregado.
- Reconcile live é fail-closed para divergência material de posição.
- Dashboard e healthcheck não devem compartilhar caches entre perfis diferentes.

---

## Arquitetura

- Runtime: `smartcrypto.runtime.orchestrator`
- Execução: `smartcrypto.execution`
- Estado: `smartcrypto.state`
- Research: `smartcrypto.research`

---

## Shadow Mode

```bash
python scripts/run_shadow_mode.py --config config/config.yml --force
```
