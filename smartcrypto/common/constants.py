from __future__ import annotations

from pathlib import Path

DEFAULT_CONFIG_PATH = Path("config/config.yml")
LEGACY_CONFIG_PATH = Path("config.yml")
DEFAULT_CONFIG_CANDIDATES = (DEFAULT_CONFIG_PATH, LEGACY_CONFIG_PATH)
DEFAULT_FEATURE_FLAGS_PATH = Path("config/feature_flags.yaml")
