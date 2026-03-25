from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULE_PATH = ROOT / "smartcrypto" / "app" / "dashboard_app.py"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if not MODULE_PATH.exists():
    raise RuntimeError("Dashboard não encontrado em smartcrypto/app/dashboard_app.py")

runpy.run_path(str(MODULE_PATH), run_name="__main__")
