from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from smartcrypto.config import load_config


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/config.yml")
    parser.add_argument("--output-dir", default="data/backups")
    args = parser.parse_args()

    cfg = load_config(args.config)
    db_path = Path(str(cfg["storage"]["db_path"]))
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    if not db_path.exists():
        raise FileNotFoundError(f"Banco não encontrado: {db_path}")

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    destination = output_dir / f"{db_path.stem}_{stamp}{db_path.suffix}"
    shutil.copy2(db_path, destination)
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
