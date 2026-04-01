# Pre-live Patch Notes

## Applied fixes

### P0
- Segregated paper and live profiles:
  - `config/config.yml` -> paper-only
  - `config/live.yml` -> explicit live profile
- Reset operational databases:
  - fresh `data/usdtbrl_live.sqlite`
  - fresh `data/usdtbrl_paper.sqlite`
  - historical live DB preserved in `data/backup/usdtbrl_live_contaminated_prepatch.sqlite`
- Added operational DB identity guard:
  - `db_role`
  - `db_profile_id`
  - `db_symbol`
- Made fill persistence transactional.
- Recovery of dispatch locks now reapplies economic state for recovered `FILLED`.
- Reconcile is now fail-closed for material position divergence.

### P1
- Preflight adapter probe is now fail-closed.
- Trade audit rows now store:
  - `bot_order_id`
  - `client_order_id`
  - `exchange_order_id`
  - `run_id`
  - `source`
- Runtime status exposes compatibility aliases:
  - `ramps_done`
  - `realized_profit_brl`

## Validation
- `pytest -q` -> green
