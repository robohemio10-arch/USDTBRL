from __future__ import annotations

from pathlib import Path


def project_root_from_config_path(config_path: str | Path) -> Path:
    path = Path(config_path).resolve()
    if path.parent.name == "config":
        return path.parent.parent
    return path.parent
