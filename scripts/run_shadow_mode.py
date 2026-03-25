# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from smartcrypto.common.constants import DEFAULT_CONFIG_PATH
from smartcrypto.config import load_config
from smartcrypto.infra.binance_adapter import ExchangeAdapter
from smartcrypto.research.shadow_mode import run_shadow_mode, run_shadow_mode_on_dataframe
from smartcrypto.runtime.feature_flags import load_feature_flags
from smartcrypto.state.store import StateStore


def cache_file_for(cfg: dict) -> Path:
    symbol = str(cfg["market"]["symbol"]).replace("/", "")
    timeframe = str(cfg["market"]["timeframe"])
    return Path("data/dashboard_cache") / f"market_{symbol}_{timeframe}.json"


def load_market_cache(cfg: dict) -> pd.DataFrame:
    cache_file = cache_file_for(cfg)
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    rows = payload.get("rows", [])
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    cfg = load_config(args.config)
    cfg = json.loads(json.dumps(cfg))
    cfg.setdefault("execution", {})
    cfg["execution"]["mode"] = "dry_run"

    config_dir = Path(args.config).resolve().parent
    feature_flags = load_feature_flags(config_dir / "feature_flags.yaml")
    if args.force:
        feature_flags["research.shadow_mode_enabled"] = True

    store = StateStore(str(cfg["storage"]["db_path"]))
    try:
        exchange = ExchangeAdapter(cfg)
        result = run_shadow_mode(cfg, exchange, store, feature_flags=feature_flags)
    except Exception:
        data = load_market_cache(cfg)
        result = run_shadow_mode_on_dataframe(cfg, data, feature_flags=feature_flags)
        if result.get("enabled"):
            store.add_research_run(
                "shadow_mode",
                "research.shadow_mode",
                {
                    "bars": int(cfg["market"].get("research_lookback_bars", len(data))),
                    "timeframe": cfg["market"]["timeframe"],
                    "source": "dashboard_cache",
                },
                result,
            )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
