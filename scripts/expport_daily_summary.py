from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from smartcrypto.common.constants import DEFAULT_CONFIG_PATH
from smartcrypto.common.utils import project_root_from_config_path, runtime_retention_days
from smartcrypto.config import load_config
from smartcrypto.infra.database import SQLiteDatabase
from smartcrypto.runtime.ai_observability import summarize_ai_observability
from smartcrypto.runtime.audit import recent_critical_events, summarize_runtime_session
from smartcrypto.runtime.cache import read_runtime_manifest_cache
from smartcrypto.state.store import StateStore


def export_dir_for_cfg(cfg: dict[str, Any]) -> Path:
    runtime = dict(cfg.get("runtime", {}) or {})
    raw = str(runtime.get("export_dir", "data/exports/paper") or "data/exports/paper")
    path = Path(raw)
    if not path.is_absolute():
        path = project_root_from_config_path(str(cfg.get("__config_path", DEFAULT_CONFIG_PATH))) / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _latest_snapshot(store: StateStore) -> dict[str, Any]:
    df = store.read_df("snapshots", limit=1)
    if df.empty:
        return {}
    return {str(key): value for key, value in df.iloc[0].to_dict().items()}


def _relevant_incidents(database: SQLiteDatabase, run_id: str) -> list[dict[str, Any]]:
    return recent_critical_events(database, run_id=run_id, limit=20)


def build_daily_summary(cfg: dict[str, Any]) -> dict[str, Any]:
    database = SQLiteDatabase(str(cfg["storage"]["db_path"]))
    store = StateStore(str(cfg["storage"]["db_path"]), database=database)
    manifest = dict(cfg.get("__operational_manifest", {}) or read_runtime_manifest_cache(cfg) or {})
    run_id = str(manifest.get("run_id", "") or cfg.get("__run_id", "") or "")
    session = summarize_runtime_session(
        database,
        run_id=run_id,
        boot_timestamp=str(manifest.get("boot_timestamp", "") or ""),
    )
    ai_summary = summarize_ai_observability(database, limit=5000)
    latest_snapshot = _latest_snapshot(store)
    incidents = _relevant_incidents(database, run_id)
    summary = {
        "run_id": run_id,
        "mode": str(cfg.get("execution", {}).get("mode", "") or ""),
        "symbol": str(cfg.get("market", {}).get("symbol", "") or ""),
        "timeframe": str(cfg.get("market", {}).get("timeframe", "") or ""),
        "uptime_seconds": int(session.get("uptime_seconds", 0) or 0),
        "cycles": int(session.get("cycle_count", 0) or 0),
        "error_cycles": int(session.get("error_cycle_count", 0) or 0),
        "critical_events": int(session.get("critical_event_count", 0) or 0),
        "ai_decisions": int(ai_summary.get("total", 0) or 0),
        "baseline_ai_divergences": int(ai_summary.get("divergence_count", 0) or 0),
        "ai_vetoes": int(ai_summary.get("veto_count", 0) or 0),
        "ai_overrides": int(ai_summary.get("override_count", 0) or 0),
        "real_baseline_count": int(ai_summary.get("real_baseline_count", 0) or 0),
        "pnl": {
            "equity_brl": latest_snapshot.get("equity_brl"),
            "realized_pnl_brl": latest_snapshot.get("realized_pnl_brl"),
            "unrealized_pnl_brl": latest_snapshot.get("unrealized_pnl_brl"),
            "drawdown_pct": latest_snapshot.get("drawdown_pct"),
        },
        "incidents": incidents,
        "manifest": manifest,
        "session": session,
    }
    return summary


def prune_old_exports(export_dir: Path, retention_days: int) -> list[str]:
    deleted: list[str] = []
    threshold = pd.Timestamp.utcnow() - pd.Timedelta(days=max(1, int(retention_days)))
    for path in export_dir.glob("daily_summary_*.json"):
        try:
            modified = pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC")
        except Exception:
            continue
        if modified < threshold:
            path.unlink(missing_ok=True)
            deleted.append(path.name)
    return deleted


def export_daily_summary(cfg: dict[str, Any], output_path: str | Path | None = None) -> tuple[Path, dict[str, Any]]:
    summary = build_daily_summary(cfg)
    export_dir = export_dir_for_cfg(cfg)
    retention_days = runtime_retention_days(cfg)
    prune_old_exports(export_dir, retention_days)
    if output_path is None:
        stamp = pd.Timestamp.utcnow().strftime("%Y%m%d")
        output = export_dir / f"daily_summary_{stamp}_{summary['run_id'] or 'unknown'}.json"
    else:
        output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return output, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)

    config_path = Path(args.config).resolve()
    cfg = load_config(str(config_path))
    cfg["__config_path"] = str(config_path)
    output, summary = export_daily_summary(cfg, args.output or None)
    print(json.dumps({"output": str(output), "run_id": summary.get("run_id", "")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())