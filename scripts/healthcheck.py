# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from smartcrypto.common.health import health_exit_code, health_report
from smartcrypto.config import load_config
from smartcrypto.state.store import StateStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/config.yml")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = load_config(args.config)
    store = StateStore(str(cfg["storage"]["db_path"]))
    report = health_report(cfg, store, interval=str(cfg.get("market", {}).get("timeframe", "15m")))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.strict:
        return health_exit_code(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
