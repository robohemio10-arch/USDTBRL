from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml

from smartcrypto.common.constants import DEFAULT_CONFIG_PATH, LEGACY_CONFIG_PATH
from smartcrypto.config import load_config, resolve_config_path, save_config


def root_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _candidate_path(relative_path: Path) -> Path:
    return root_dir() / relative_path


def _config_path_from_argv() -> Path | None:
    argv = list(sys.argv[1:])
    for index, token in enumerate(argv):
        if token == "--config" and index + 1 < len(argv):
            return Path(argv[index + 1]).expanduser()
        if token.startswith("--config="):
            return Path(token.split("=", 1)[1]).expanduser()
    return None


def config_path() -> Path:
    env_value = os.getenv("SMARTCRYPTO_CONFIG_PATH", "").strip()
    argv_value = _config_path_from_argv()
    if argv_value is not None:
        return resolve_config_path(argv_value)
    if env_value:
        return resolve_config_path(Path(env_value))
    primary = _candidate_path(DEFAULT_CONFIG_PATH)
    legacy = _candidate_path(LEGACY_CONFIG_PATH)
    return resolve_config_path(primary if primary.exists() else legacy)


def load_cfg() -> dict[str, Any]:
    return load_config(config_path())


def save_cfg(cfg: dict[str, Any]) -> None:
    save_config(config_path(), cfg)


def _read_yaml_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def config_consistency_status() -> dict[str, Any]:
    primary = _candidate_path(DEFAULT_CONFIG_PATH)
    legacy = _candidate_path(LEGACY_CONFIG_PATH)
    primary_raw = primary.read_text(encoding="utf-8") if primary.exists() else ""
    legacy_raw = legacy.read_text(encoding="utf-8") if legacy.exists() else ""
    primary_data = _read_yaml_if_exists(primary)
    legacy_data = _read_yaml_if_exists(legacy)
    primary_mode = str(primary_data.get("execution", {}).get("mode", "") or "")
    legacy_mode = str(legacy_data.get("execution", {}).get("mode", "") or "")
    same_content = bool(primary.exists() and legacy.exists() and primary_raw == legacy_raw)
    mode_mismatch = bool(primary_mode and legacy_mode and primary_mode != legacy_mode)
    both_exist = primary.exists() and legacy.exists()
    return {
        "canonical_path": config_path(),
        "primary_path": primary,
        "legacy_path": legacy,
        "both_exist": both_exist,
        "same_content": same_content,
        "mode_mismatch": mode_mismatch,
        "primary_mode": primary_mode,
        "legacy_mode": legacy_mode,
    }
