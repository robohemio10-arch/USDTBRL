# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from smartcrypto.common.constants import DEFAULT_CONFIG_PATH
from smartcrypto.config import load_config
from smartcrypto.research.ml_store import MLStore
from smartcrypto.research.rollout import build_live_partial_decision
from smartcrypto.research.shadow_mode import run_shadow_mode_on_dataframe
from smartcrypto.runtime.feature_flags import load_feature_flags


def _load_cache(cfg: dict) -> pd.DataFrame:
    symbol = str(cfg["market"]["symbol"]).replace("/", "")
    timeframe = str(cfg["market"]["timeframe"])
    path = Path("data/dashboard_cache") / f"market_{symbol}_{timeframe}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return pd.DataFrame(payload.get("rows", []))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    args = parser.parse_args()

    cfg = load_config(args.config)
    feature_flags = load_feature_flags(Path(args.config).resolve().parent / "feature_flags.yaml")
    frame = _load_cache(cfg)
    shadow = run_shadow_mode_on_dataframe(cfg, frame, feature_flags=feature_flags)
    decision = build_live_partial_decision(cfg, shadow, feature_flags)
    store = MLStore(str(cfg.get("storage", {}).get("ml_store_path", "data/ml_store.sqlite")))
    store.add_rollout_event(str(cfg["market"]["symbol"]), str(cfg["market"]["timeframe"]), "live_partial", decision.as_dict())
    print(json.dumps(decision.as_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
