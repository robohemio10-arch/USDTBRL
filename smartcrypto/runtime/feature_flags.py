from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def _flatten_flags(payload: dict[str, Any], prefix: str = "") -> dict[str, bool]:
    flattened: dict[str, bool] = {}
    for key, value in payload.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flattened.update(_flatten_flags(value, name))
        else:
            flattened[name] = bool(value)
    return flattened


def load_feature_flags(path: str | Path) -> dict[str, bool]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        return {}
    return _flatten_flags(payload)
