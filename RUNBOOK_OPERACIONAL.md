# Runbook operacional — SmartCrypto USDT/BRL

## Subida padrão
1. `python scripts/validate_config.py --config config/config.yml`
2. `python scripts/migrate_db.py --config config/config.yml`
3. `python scripts/backfill_market_cache.py --config config/config.yml`
4. `python scripts/healthcheck.py --config config/config.yml`
5. `python bot.py --config config/config.yml --status`
6. `python -m streamlit run dashboard.py`

## Antes de entrar em live
- conferir `.env` com chaves válidas
- confirmar `execution.mode: live`
- validar healthcheck sem warnings críticos
- verificar `paused = false`
- verificar `live_reconcile_required = false`
- verificar `active_dispatch_locks = 0`

## Se o bot pausar sozinho
1. Rode `python bot.py --config config/config.yml --status`
2. Rode `python scripts/healthcheck.py --config config/config.yml --strict`
3. Verifique:
   - `consecutive_error_count`
   - `live_reconcile_required`
   - `active_dispatch_locks`
4. Consulte `data/logs/bot.jsonl`
5. Se houve mismatch, reconcilie posição/ordens antes de voltar a live

## Se houver lock de ordem em voo
- não force nova ordem antes de verificar a exchange
- rode o bot em `--status`
- se necessário, suba em live para recuperar via `clientOrderId`
- confirme depois que `active_dispatch_locks` voltou para zero

## Se o dashboard abrir mas o mercado estiver velho
- execute `python scripts/backfill_market_cache.py --config config/config.yml`
- recarregue a tela
- verifique a pasta `data/dashboard_cache`

## Rotina diária
- healthcheck
- conferir eventos críticos
- conferir NTFY
- conferir lucro do dia e ciclos fechados
- revisar logs do `bot.jsonl`

## Recuperação após restart
- o bot faz `startup_reconcile`
- se detectar mismatch, pausa
- trate o mismatch primeiro, depois despause

## Saída segura
- pare o bot com Ctrl+C
- aguarde o último ciclo de log
- não desligue a máquina durante ordem em voo
