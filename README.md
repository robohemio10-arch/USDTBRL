# SmartCrypto USDT/BRL Bot

Bot profissional de compra e venda USDT/BRL na Binance, com arquitetura modular, execução robusta e suporte a research e shadow mode.

\---

## 🚀 Setup rápido

### 1\. Criar arquivo `.env`

```
BINANCE\_API\_KEY=...
BINANCE\_API\_SECRET=...
NTFY\_TOPIC=...
```

\---

### 2\. Rodar migração do banco

```
python scripts/migrate\_db.py --config config/config.yml
```

\---

### 3\. Verificar saúde do sistema

```
python scripts/healthcheck.py --config config/config.yml
```

\---

### 4\. Rodar o bot

```
python bot.py --config config/config.yml
```

\---

### 5\. Rodar o dashboard

```
streamlit run dashboard.py
```

\---

## ⚙️ Configuração

Arquivo principal:

```
config/config.yml
```

\---

## 🧱 Arquitetura (resumo)

* Runtime: `smartcrypto.runtime.orchestrator`
* Execução: `smartcrypto.execution`
* Domínio: `smartcrypto.domain`
* Research: `smartcrypto.research`
* Estado: `smartcrypto.state`

\---

## ⚠️ Compatibilidade (legado)

Arquivos mantidos por compatibilidade:

* `config.yml` → usar `config/config.yml`
* `smartcrypto.infra.binance` → usar `smartcrypto.infra.binance\_adapter`
* `smartcrypto.state.store` → usar módulos em `state/`

🚫 Não usar esses caminhos em código novo.

\---

## 📊 Shadow Mode

Executar:

```
python scripts/run\_shadow\_mode.py --config config/config.yml --force
```

\---

## 📄 Documentação

* `docs/ARCHITECTURE.md`
* `docs/ROLLOUT.md`
* `docs/SHADOW\_MODE.md`
* `docs/LEGACY\_COMPATIBILITY.md`

