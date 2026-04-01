from __future__ import annotations

import json
from pathlib import Path

from smartcrypto.config import load_config
from smartcrypto.runtime.preflight import perform_preflight


def main() -> int:
    config_path = Path("config/paper_7d.yml").resolve()
    cfg = load_config(str(config_path))
    cfg["__config_path"] = str(config_path)
    cfg.setdefault("__boot_timestamp", "bootstrap")
    cfg.setdefault("__run_id", "paper-preflight")
    report = perform_preflight(cfg, resolved_config_path=config_path, config_is_canonical=True)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
