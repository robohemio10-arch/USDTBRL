from __future__ import annotations

import json
from pathlib import Path

import pytest

from smartcrypto.runtime.instance_lock import (
    InstanceLockError,
    acquire_instance_lock,
    instance_lock_path,
    release_instance_lock,
)


def build_cfg(tmp_path: Path, run_id: str, config_name: str) -> dict[str, object]:
    return {
        "__config_path": str(tmp_path / "config" / config_name),
        "__run_id": run_id,
        "runtime": {
            "single_instance_enabled": True,
            "instance_lock_path": str(tmp_path / "runtime.lock.json"),
        },
        "execution": {"mode": "paper"},
    }


def write_lock_file(path: Path, *, pid: int, run_id: str = "run-old") -> None:
    path.write_text(
        json.dumps(
            {
                "config_path": "",
                "created_at": "2026-03-26T22:34:45.848167+00:00",
                "hostname": "NotebookLenovo",
                "mode": "",
                "pid": pid,
                "run_id": run_id,
            }
        ),
        encoding="utf-8",
    )


def test_instance_lock_blocks_second_acquire(tmp_path: Path) -> None:
    cfg = build_cfg(tmp_path, "run-test-001", "paper_7d.yml")
    path = instance_lock_path(cfg)

    payload = acquire_instance_lock(cfg)

    try:
        assert payload["run_id"] == "run-test-001"
        with pytest.raises(InstanceLockError):
            acquire_instance_lock(cfg)
    finally:
        release_instance_lock(cfg)

    assert not path.exists()


def test_instance_lock_clears_stale_file_when_pid_is_dead(tmp_path: Path) -> None:
    cfg = build_cfg(tmp_path, "run-test-stale", "paper.yml")
    path = instance_lock_path(cfg)

    write_lock_file(path, pid=999999)

    payload = acquire_instance_lock(cfg)

    try:
        assert payload["run_id"] == "run-test-stale"
        assert payload["pid"] != 999999
    finally:
        release_instance_lock(cfg)

    assert not path.exists()
