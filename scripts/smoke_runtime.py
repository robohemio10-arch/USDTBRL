# ruff: noqa: E402

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from smartcrypto.config import load_config
from smartcrypto.runtime.bot_runtime import status_payload
from smartcrypto.state.store import StateStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/config.yml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    store = StateStore(str(cfg["storage"]["db_path"]))
    payload = status_payload(
        store, float(cfg.get("simulation", {}).get("mock_price_brl", 5.2) or 5.2), cfg
    )
    dashboard_import_ok = False
    dashboard_import_skipped = False
    try:
        importlib.import_module("smartcrypto.app.dashboard_app")
        dashboard_import_ok = True
    except ModuleNotFoundError as exc:
        if "streamlit" in str(exc):
            dashboard_import_skipped = True
        else:
            raise
    result = {
        "config_loaded": True,
        "status_payload_ok": True,
        "dashboard_import_ok": dashboard_import_ok,
        "dashboard_import_skipped": dashboard_import_skipped,
        "paused": payload.get("paused"),
        "health_status": payload.get("health", {}).get("status"),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
