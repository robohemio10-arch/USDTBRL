from __future__ import annotations

import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any


def project_root_from_config_path(config_path: str | Path) -> Path:
    path = Path(config_path).resolve()
    if path.parent.name == "config":
        return path.parent.parent
    return path.parent


def runtime_safe_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def runtime_config_hash(payload: dict[str, Any]) -> str:
    normalized = {
        key: value
        for key, value in dict(payload or {}).items()
        if not str(key).startswith("__")
    }
    raw = runtime_safe_json(normalized).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def runtime_git_commit(project_root: str | Path) -> str:
    root = Path(project_root).resolve()
    git_dir = root / ".git"
    if not git_dir.exists():
        return ""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def runtime_build_id(cfg: dict[str, Any] | None = None) -> str:
    cfg = dict(cfg or {})
    runtime = dict(cfg.get("runtime", {}) or {})
    execution = dict(cfg.get("execution", {}) or {})
    value = (
        runtime.get("build_id")
        or execution.get("build_id")
        or os.getenv("SMARTCRYPTO_BUILD_ID")
        or os.getenv("BUILD_ID")
        or "runtime-bootstrap"
    )
    return str(value)


def runtime_environment(cfg: dict[str, Any] | None = None) -> str:
    cfg = dict(cfg or {})
    runtime = dict(cfg.get("runtime", {}) or {})
    execution = dict(cfg.get("execution", {}) or {})
    value = (
        runtime.get("environment")
        or execution.get("environment")
        or os.getenv("SMARTCRYPTO_ENV")
        or os.getenv("ENVIRONMENT")
        or "local"
    )
    return str(value)


def runtime_run_id(cfg: dict[str, Any] | None = None) -> str:
    cfg = dict(cfg or {})
    runtime = dict(cfg.get("runtime", {}) or {})
    execution = dict(cfg.get("execution", {}) or {})
    value = (
        cfg.get("__run_id")
        or runtime.get("run_id")
        or execution.get("run_id")
        or os.getenv("SMARTCRYPTO_RUN_ID")
        or f"run-{uuid.uuid4().hex[:12]}"
    )
    return str(value)


def runtime_protocol_version(cfg: dict[str, Any] | None = None) -> str:
    cfg = dict(cfg or {})
    runtime = dict(cfg.get("runtime", {}) or {})
    return str(runtime.get("protocol_version", "") or os.getenv("SMARTCRYPTO_PROTOCOL_VERSION") or "")


def runtime_session_label(cfg: dict[str, Any] | None = None) -> str:
    cfg = dict(cfg or {})
    runtime = dict(cfg.get("runtime", {}) or {})
    value = runtime.get("session_label") or runtime.get("experiment_profile") or runtime_run_id(cfg)
    return str(value)


def runtime_retention_days(cfg: dict[str, Any] | None = None, default: int = 14) -> int:
    cfg = dict(cfg or {})
    runtime = dict(cfg.get("runtime", {}) or {})
    try:
        return max(1, int(runtime.get("retention_days", default) or default))
    except Exception:
        return max(1, int(default))
