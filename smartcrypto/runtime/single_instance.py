from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from smartcrypto.runtime.audit import record_runtime_event
from smartcrypto.runtime.instance_lock import (
    InstanceLockError,
    acquire_instance_lock,
    instance_lock_path,
    read_instance_lock,
    release_instance_lock,
)


class DuplicateInstanceBlockedError(InstanceLockError):
    pass


def acquire_single_instance(
    cfg: dict[str, Any],
    *,
    database: Any | None = None,
) -> dict[str, Any]:
    try:
        payload = acquire_instance_lock(cfg)
    except InstanceLockError as exc:
        details = {
            "lock_path": str(instance_lock_path(cfg)),
            "existing_lock": read_instance_lock(instance_lock_path(cfg)),
            "error": str(exc),
        }
        if database is not None:
            record_runtime_event(
                cfg,
                database,
                event="duplicate_instance_blocked",
                level="ERROR",
                details=details,
            )
        raise DuplicateInstanceBlockedError(str(exc)) from exc
    return payload


def release_single_instance(
    cfg: dict[str, Any],
    *,
    database: Any | None = None,
    record_event: bool = True,
) -> None:
    release_instance_lock(cfg)
    if record_event and database is not None:
        record_runtime_event(
            cfg,
            database,
            event="instance_lock_released",
            level="INFO",
            details={"lock_path": str(instance_lock_path(cfg))},
        )


@contextmanager
def runtime_single_instance(
    cfg: dict[str, Any],
    *,
    database: Any | None = None,
) -> Iterator[dict[str, Any]]:
    payload = acquire_single_instance(cfg, database=database)
    try:
        yield payload
    finally:
        release_single_instance(cfg, database=database)
