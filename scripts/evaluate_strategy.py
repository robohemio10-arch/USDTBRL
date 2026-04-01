# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from smartcrypto.common.constants import DEFAULT_CONFIG_PATH
from smartcrypto.config import load_config
from smartcrypto.research.quant_validation import run_quant_validation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--no-persist", action="store_true")
    args = parser.parse_args()

    cfg = load_config(args.config)
    report = run_quant_validation(cfg, persist=not args.no_persist)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
