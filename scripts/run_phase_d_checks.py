from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


COMMANDS = [
    [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "validate_config.py"),
        "--config",
        "config/config.yml",
    ],
    [sys.executable, str(PROJECT_ROOT / "scripts" / "migrate_db.py"), "--config", "config/config.yml"],
    [sys.executable, str(PROJECT_ROOT / "scripts" / "healthcheck.py"), "--config", "config/config.yml"],
    [sys.executable, str(PROJECT_ROOT / "scripts" / "smoke_runtime.py"), "--config", "config/config.yml"],
    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"],
]


def main() -> int:
    for cmd in COMMANDS:
        print("\n>>>", " ".join(cmd))
        completed = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
