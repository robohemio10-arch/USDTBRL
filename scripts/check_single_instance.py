from __future__ import annotations

import argparse
import json
from pathlib import Path

from smartcrypto.common.constants import DEFAULT_CONFIG_PATH
from smartcrypto.config import load_config
from smartcrypto.infra.database import SQLiteDatabase
from smartcrypto.runtime.single_instance import acquire_single_instance, release_single_instance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args(argv)

    config_path = Path(args.config).resolve()
    cfg = load_config(str(config_path))
    cfg["__config_path"] = str(config_path)
    cfg.setdefault("__run_id", "single-instance-check")
    database = SQLiteDatabase(str(cfg["storage"]["db_path"]))
    payload = acquire_single_instance(cfg, database=database)
    release_single_instance(cfg, database=database)
    print(json.dumps({"status": "ok", "lock": payload}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
