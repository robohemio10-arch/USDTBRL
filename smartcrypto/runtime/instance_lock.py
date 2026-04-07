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
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _pid_is_running(pid: Any) -> bool:
    try:
        value = int(pid)
    except Exception:
        return False

    if value <= 0:
        return False

    if value == os.getpid():
        return True

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        open_process = kernel32.OpenProcess
        open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        open_process.restype = wintypes.HANDLE

        get_exit_code_process = kernel32.GetExitCodeProcess
        get_exit_code_process.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        get_exit_code_process.restype = wintypes.BOOL

        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL

        handle = open_process(process_query_limited_information, False, value)
        if not handle:
            return False

        try:
            exit_code = wintypes.DWORD()
            if not get_exit_code_process(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == still_active
        finally:
            close_handle(handle)

    try:
        os.kill(value, 0)
    except OSError:
        return False
    except Exception:
        return True
    return True


def _clear_stale_instance_lock(path: Path, payload: dict[str, Any]) -> bool:
    if not isinstance(payload, dict) or not payload:
        return False

    pid = payload.get("pid")
    try:
        normalized_pid = int(pid)
    except Exception:
        return False

    if normalized_pid == os.getpid():
        return False

    if _pid_is_running(normalized_pid):
        return False

    try:
        path.unlink(missing_ok=True)
    except Exception:
        return False
    return True


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
            run_id = str(existing.get("run_id") or "")
            if run_id not in {"", str(runtime_run_id(cfg))}:
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
