from __future__ import annotations

import json
import os
import socket
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from smartcrypto.common.utils import project_root_from_config_path, runtime_run_id
from smartcrypto.state.store import utc_now


class InstanceLockError(RuntimeError):
    pass


def single_instance_enabled(cfg: dict[str, Any]) -> bool:
    runtime = dict(cfg.get("runtime", {}) or {})
    if "single_instance_enabled" not in runtime:
        return bool(cfg.get("__config_path") or cfg.get("__operational_manifest") or cfg.get("__run_id"))
    value = runtime.get("single_instance_enabled")
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def instance_lock_path(cfg: dict[str, Any]) -> Path:
    runtime = dict(cfg.get("runtime", {}) or {})
    raw = str(runtime.get("instance_lock_path", "data/runtime/instance.lock.json") or "data/runtime/instance.lock.json")
    path = Path(raw)
    if not path.is_absolute():
        config_path = str(cfg.get("__config_path", "config/config.yml") or "config/config.yml")
        path = project_root_from_config_path(config_path) / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def read_instance_lock(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}




def _pid_is_running(pid: Any) -> bool:
    try:
        value = int(pid)
    except Exception:
        return False
    if value <= 0:
        return False
    try:
        os.kill(value, 0)
    except OSError:
        return False
    except Exception:
        return True
    return True


def _clear_stale_instance_lock(path: Path, payload: dict[str, Any]) -> bool:
    pid = payload.get("pid")
    if _pid_is_running(pid):
        return False
    try:
        path.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def acquire_instance_lock(cfg: dict[str, Any]) -> dict[str, Any]:
    if not single_instance_enabled(cfg):
        return {}
    path = instance_lock_path(cfg)
    payload = {
        "run_id": runtime_run_id(cfg),
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "mode": str(cfg.get("execution", {}).get("mode", "") or ""),
        "config_path": str(cfg.get("__config_path", "") or ""),
        "created_at": utc_now(),
    }
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(path), flags)
    except FileExistsError as exc:
        existing = read_instance_lock(path)
        if _clear_stale_instance_lock(path, existing):
            try:
                fd = os.open(str(path), flags)
            except FileExistsError:
                existing = read_instance_lock(path)
            else:
                exc = None
        if exc is not None:
            raise InstanceLockError(
                f"Outra instância já está ativa em {path}: {json.dumps(existing, ensure_ascii=False, sort_keys=True)}"
            ) from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        raise
    cfg["__instance_lock_path"] = str(path)
    cfg["__instance_lock"] = dict(payload)
    return payload


def release_instance_lock(cfg: dict[str, Any]) -> None:
    if not single_instance_enabled(cfg):
        return
    path = Path(str(cfg.get("__instance_lock_path") or instance_lock_path(cfg)))
    if not path.exists():
        return
    try:
        existing = read_instance_lock(path)
        if existing:
            if str(existing.get("run_id") or "") not in {"", str(runtime_run_id(cfg))}:
                return
            if existing.get("pid") not in {None, os.getpid()}:
                return
        path.unlink(missing_ok=True)
    except Exception:
        pass


@contextmanager
def runtime_instance_lock(cfg: dict[str, Any]) -> Iterator[dict[str, Any]]:
    payload = acquire_instance_lock(cfg)
    try:
        yield payload
    finally:
        release_instance_lock(cfg)
