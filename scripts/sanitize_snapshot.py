from __future__ import annotations

import argparse
import shutil
from pathlib import Path

DEFAULT_PATTERNS = (
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "*.egg-info",
)


def remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--purge-data-caches", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    removed: list[str] = []

    for pattern in DEFAULT_PATTERNS:
        for candidate in root.rglob(pattern):
            remove_path(candidate)
            removed.append(str(candidate.relative_to(root)))

    if args.purge_data_caches:
        for relative in ("data/logs", "data/dashboard_cache"):
            candidate = root / relative
            if candidate.exists():
                remove_path(candidate)
                removed.append(relative)

    for item in removed:
        print(item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
