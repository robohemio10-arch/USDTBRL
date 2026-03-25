from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import pandas as pd

from smartcrypto.common.logging_utils import read_recent_logs
from smartcrypto.runtime.cache import market_cache_file, runtime_status_cache_file


def _parse_ts(value: Any) -> datetime | None:
    if value in (None, "", 0):
        return None
    try:
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)

        parsed = pd.to_datetime(value, errors="coerce", utc=True)
        if pd.isna(parsed):
            return None

        if isinstance(parsed, pd.Timestamp):
            return cast(datetime, parsed.to_pydatetime())

        return None
    except Exception:
        return None


def _age_seconds(value: Any) -> float | None:
    parsed = _parse_ts(value)
    if parsed is None:
        return None
    now = datetime.now(timezone.utc)
    return max(0.0, (now - parsed).total_seconds())



def health_report(cfg: dict[str, Any], store, *, interval: str | None = None) -> dict[str, Any]:
    status = "ok"
    issues: list[dict[str, Any]] = []

    paused = bool(store.get_flag("paused", False))
    live_reconcile_required = bool(store.get_flag("live_reconcile_required", False))
    consecutive_error_count = int(store.get_flag("consecutive_error_count", 0) or 0)
    active_locks = store.list_active_dispatch_locks(limit=20)

    snapshots = store.read_df("snapshots", 1)
    last_snapshot_at = None if snapshots.empty else snapshots.iloc[0].get("ts")
    snapshot_age = _age_seconds(last_snapshot_at)

    runtime_cache = runtime_status_cache_file(cfg)
    runtime_cache_age = _age_seconds(
        runtime_cache.stat().st_mtime if runtime_cache.exists() else None
    )

    market_cache = market_cache_file(cfg, interval=interval)
    market_cache_age = _age_seconds(market_cache.stat().st_mtime if market_cache.exists() else None)

    stale_runtime_minutes = int(cfg.get("health", {}).get("stale_runtime_minutes", 20) or 20)
    stale_market_cache_minutes = int(
        cfg.get("health", {}).get("stale_market_cache_minutes", 240) or 240
    )

    if paused:
        status = "warning"
        issues.append({"code": "paused", "message": "Bot está pausado."})
    if live_reconcile_required:
        status = "warning"
        issues.append({"code": "reconcile_required", "message": "Reconciliação live pendente."})
    if consecutive_error_count > 0:
        status = "warning"
        issues.append(
            {
                "code": "consecutive_errors",
                "message": f"{consecutive_error_count} erro(s) consecutivo(s).",
            }
        )
    if active_locks:
        status = "warning"
        issues.append(
            {
                "code": "dispatch_locks",
                "message": f"{len(active_locks)} lock(s) de despacho ativos.",
            }
        )
    if snapshot_age is None:
        status = "warning"
        issues.append({"code": "no_snapshot", "message": "Nenhum snapshot local encontrado."})
    elif snapshot_age > stale_runtime_minutes * 60:
        status = "warning"
        issues.append(
            {"code": "stale_snapshot", "message": f"Último snapshot com {int(snapshot_age)}s."}
        )
    if runtime_cache_age is None:
        status = "warning"
        issues.append({"code": "no_runtime_cache", "message": "Cache de runtime ausente."})
    elif runtime_cache_age > stale_runtime_minutes * 60:
        status = "warning"
        issues.append(
            {
                "code": "stale_runtime_cache",
                "message": f"Cache de runtime com {int(runtime_cache_age)}s.",
            }
        )
    if market_cache_age is None:
        status = "warning"
        issues.append({"code": "no_market_cache", "message": "Cache de mercado ausente."})
    elif market_cache_age > stale_market_cache_minutes * 60:
        status = "warning"
        issues.append(
            {
                "code": "stale_market_cache",
                "message": f"Cache de mercado com {int(market_cache_age)}s.",
            }
        )

    recent_logs = read_recent_logs(cfg, "bot", limit=100)
    error_logs = [row for row in recent_logs if str(row.get("level", "")).upper() == "ERROR"]

    return {
        "status": status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "mode": str(cfg.get("execution", {}).get("mode", "dry_run")),
        "issues": issues,
        "paused": paused,
        "live_reconcile_required": live_reconcile_required,
        "consecutive_error_count": consecutive_error_count,
        "active_dispatch_locks": len(active_locks),
        "last_snapshot_at": str(last_snapshot_at or ""),
        "snapshot_age_seconds": snapshot_age,
        "runtime_cache_file": str(runtime_cache),
        "runtime_cache_age_seconds": runtime_cache_age,
        "market_cache_file": str(market_cache),
        "market_cache_age_seconds": market_cache_age,
        "recent_error_logs": error_logs[-10:],
    }


def health_exit_code(report: dict[str, Any]) -> int:
    return 0 if str(report.get("status", "ok")).lower() == "ok" else 1
