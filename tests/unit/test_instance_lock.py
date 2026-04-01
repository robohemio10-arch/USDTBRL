from pathlib import Path

import pytest

from smartcrypto.runtime.instance_lock import (
    InstanceLockError,
    acquire_instance_lock,
    instance_lock_path,
    release_instance_lock,
)


def test_instance_lock_blocks_second_acquire(tmp_path: Path) -> None:
    cfg = {
        "__config_path": str(tmp_path / "config" / "paper_7d.yml"),
        "__run_id": "run-test-001",
        "runtime": {"single_instance_enabled": True, "instance_lock_path": str(tmp_path / "runtime.lock.json")},
        "execution": {"mode": "paper"},
    }
    payload = acquire_instance_lock(cfg)
    try:
        assert payload["run_id"] == "run-test-001"
        with pytest.raises(InstanceLockError):
            acquire_instance_lock(cfg)
    finally:
        release_instance_lock(cfg)
    assert not instance_lock_path(cfg).exists()


def test_instance_lock_clears_stale_file_when_pid_is_dead(tmp_path: Path) -> None:
    cfg = {
        "__config_path": str(tmp_path / "config" / "paper.yml"),
        "__run_id": "run-test-stale",
        "runtime": {"single_instance_enabled": True, "instance_lock_path": str(tmp_path / "runtime.lock.json")},
        "execution": {"mode": "paper"},
    }
    path = instance_lock_path(cfg)
    path.write_text(
        '{"config_path": "", "created_at": "2026-03-26T22:34:45.848167+00:00", "hostname": "NotebookLenovo", "mode": "", "pid": 999999, "run_id": "run-old"}',
        encoding="utf-8",
    )
    payload = acquire_instance_lock(cfg)
    try:
        assert payload["run_id"] == "run-test-stale"
        assert payload["pid"] != 999999
    finally:
        release_instance_lock(cfg)
    assert not path.exists()
