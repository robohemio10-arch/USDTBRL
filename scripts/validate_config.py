# ruff: noqa: E402

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from smartcrypto.config import load_config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/config.yml")
    args = parser.parse_args()
    cfg = load_config(args.config)
    print("Configuração válida.")
    print(f"Símbolo: {cfg['market']['symbol']}")
    print(f"Modo: {cfg['execution']['mode']}")
    print(f"Ramps: {len(cfg['strategy']['ramps'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
