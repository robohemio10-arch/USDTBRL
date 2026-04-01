# Runbook Operacional

## Perfis suportados

- Paper padrão: `config/config.yml`
- Paper 7d: `config/paper_7d.yml`
- Live: `config/live.yml`

## Comandos

### Migrar banco paper
```bash
python scripts/migrate_db.py --config config/config.yml
```

### Migrar banco live
```bash
python scripts/migrate_db.py --config config/live.yml
```

### Healthcheck paper
```bash
python scripts/healthcheck.py --config config/config.yml --strict
```

### Healthcheck live
```bash
python scripts/healthcheck.py --config config/live.yml --strict
```

### Executar paper
```bash
python bot.py --config config/config.yml
```

### Executar live
```bash
python bot.py --config config/live.yml
```

## Guard-rails

- Banco com identidade divergente bloqueia bootstrap.
- Reconcile live pausa o runtime em divergência material.
- Recovery de dispatch lock reaplica estado econômico do fill.
- Trades agora carregam identidade operacional (`bot_order_id`, `client_order_id`, `exchange_order_id`, `run_id`, `source`).
