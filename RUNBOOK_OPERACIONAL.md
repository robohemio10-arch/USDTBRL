# Runbook Operacional

## Perfis suportados

- Paper padrão: `config/config.yml`
- Live: `config/live_100usdt.yml`

## Comandos

### Migrar banco paper
```bash
python scripts/migrate_db.py --config config/config.yml
```

### Migrar banco live
```bash
python scripts/migrate_db.py --config config/live_100usdt.yml
```

### Healthcheck paper
```bash
python scripts/healthcheck.py --config config/config.yml --strict
```

### Healthcheck live
```bash
python scripts/healthcheck.py --config config/live_100usdt.yml --strict
```

### Executar paper
```bash
python bot.py --config config/config.yml
```

### Executar live
```bash
python bot.py --config config/live_100usdt.yml
```

### Executar live via PowerShell
```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_live_100usdt.ps1
```

## Guard-rails

- Banco com identidade divergente bloqueia bootstrap.
- Reconcile live pausa o runtime em divergência material.
- Recovery de dispatch lock reaplica estado econômico do fill.
- Trades carregam identidade operacional (`bot_order_id`, `client_order_id`, `exchange_order_id`, `run_id`, `source`).
- Caches do dashboard e do healthcheck são segregados por perfil operacional.

## Observação operacional

Se paper e live coexistirem no mesmo host, mantenha o mesmo `dashboard.cache_dir` apenas com esta versão do código ou superior, porque os arquivos de cache passaram a ser separados por perfil.
