from __future__ import annotations

import importlib.metadata
import json
import sqlite3
from pathlib import Path
from typing import Any

from smartcrypto.common.utils import (
    runtime_build_id,
    runtime_config_hash,
    runtime_environment,
    runtime_git_commit,
    runtime_protocol_version,
    runtime_retention_days,
    runtime_run_id,
    runtime_session_label,
)
from smartcrypto.runtime.cache import read_runtime_manifest_cache, write_runtime_manifest_cache
from smartcrypto.runtime.paper_profile import build_paper_profile_metadata


def _package_version() -> str:
    for dist_name in ("usdtbrl", "smartcrypto"):
        try:
            return importlib.metadata.version(dist_name)
        except Exception:
            continue
    return ""


def build_runtime_manifest(
    cfg: dict[str, Any],
    *,
    resolved_config_path: str | Path | None = None,
    feature_flags: dict[str, bool] | None = None,
    preflight: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_path = Path(str(resolved_config_path or cfg.get("__config_path", "") or "config/config.yml")).resolve()
    flags = dict(feature_flags or cfg.get("__feature_flags", {}) or {})
    profile = build_paper_profile_metadata(cfg, config_path=resolved_path)
    return {
        "config_path": str(resolved_path),
        "mode": str(cfg.get("execution", {}).get("mode", "") or ""),
        "environment": runtime_environment(cfg),
        "symbol": str(cfg.get("market", {}).get("symbol", "") or ""),
        "timeframe": str(cfg.get("market", {}).get("timeframe", "") or ""),
        "db_path": str(cfg.get("storage", {}).get("db_path", "") or ""),
        "feature_flags": flags,
        "feature_flags_present": bool(flags),
        "build_id": runtime_build_id(cfg),
        "run_id": runtime_run_id(cfg),
        "boot_timestamp": str(cfg.get("__boot_timestamp") or ""),
        "version": _package_version(),
        "config_hash": runtime_config_hash(cfg),
        "git_commit": runtime_git_commit(resolved_path.parent.parent),
        "preflight_status": str((preflight or cfg.get("__preflight", {}) or {}).get("status", "unknown")),
        "protocol_version": runtime_protocol_version(cfg),
        "experiment_profile": str(profile.get("profile_id", "") or ""),
        "profile_version": str(profile.get("profile_version", "") or ""),
        "session_label": runtime_session_label(cfg),
        "profile_frozen": bool(profile.get("frozen", False)),
        "retention_days": runtime_retention_days(cfg),
    }



def _with_connection(database_or_path: Any):
    if hasattr(database_or_path, "connect"):
        return database_or_path.connect(), False
    conn = sqlite3.connect(str(database_or_path))
    conn.row_factory = sqlite3.Row

    class _Wrapper:
        def __enter__(self_non):
            return conn

        def __exit__(self_non, exc_type, exc, tb):
            conn.commit()
            conn.close()
            return False

    return _Wrapper(), True


def _ensure_manifest_columns(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        create table if not exists runtime_manifest (
            id integer primary key autoincrement,
            created_at text not null,
            config_path text not null,
            mode text not null,
            environment text,
            symbol text,
            timeframe text,
            db_path text not null,
            feature_flags_json text not null,
            feature_flags_present integer not null default 0,
            build_id text,
            run_id text,
            boot_timestamp text,
            version text,
            config_hash text,
            git_commit text,
            preflight_status text,
            protocol_version text,
            experiment_profile text,
            profile_version text,
            session_label text,
            profile_frozen integer not null default 0,
            retention_days integer,
            manifest_json text not null
        )
        """
    )
    columns = {
        row[1]
        for row in conn.execute("pragma table_info(runtime_manifest)").fetchall()
    }
    if "run_id" not in columns:
        conn.execute("alter table runtime_manifest add column run_id text")


def persist_runtime_manifest(
    cfg: dict[str, Any],
    manifest: dict[str, Any],
    *,
    database: Any | None = None,
) -> None:
    cfg["__operational_manifest"] = dict(manifest or {})
    cfg["__runtime_manifest"] = dict(manifest or {})
    write_runtime_manifest_cache(cfg, manifest)
    db_path = str(cfg.get("storage", {}).get("db_path", "") or "")
    target = database or db_path
    if not target:
        return
    ctx, _ = _with_connection(target)
    with ctx as conn:
        _ensure_manifest_columns(conn)
        conn.execute(
            """
            insert into runtime_manifest(
                created_at, config_path, mode, environment, symbol, timeframe, db_path,
                feature_flags_json, feature_flags_present, build_id, run_id, boot_timestamp,
                version, config_hash, git_commit, preflight_status, protocol_version,
                experiment_profile, profile_version, session_label, profile_frozen, retention_days, manifest_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(manifest.get("boot_timestamp") or cfg.get("__boot_timestamp") or ""),
                str(manifest.get("config_path") or ""),
                str(manifest.get("mode") or ""),
                str(manifest.get("environment") or ""),
                str(manifest.get("symbol") or ""),
                str(manifest.get("timeframe") or ""),
                str(manifest.get("db_path") or ""),
                json.dumps(manifest.get("feature_flags", {}), ensure_ascii=False, sort_keys=True),
                1 if bool(manifest.get("feature_flags_present")) else 0,
                str(manifest.get("build_id") or ""),
                str(manifest.get("run_id") or ""),
                str(manifest.get("boot_timestamp") or ""),
                str(manifest.get("version") or ""),
                str(manifest.get("config_hash") or ""),
                str(manifest.get("git_commit") or ""),
                str(manifest.get("preflight_status") or ""),
                str(manifest.get("protocol_version") or ""),
                str(manifest.get("experiment_profile") or ""),
                str(manifest.get("profile_version") or ""),
                str(manifest.get("session_label") or ""),
                1 if bool(manifest.get("profile_frozen")) else 0,
                manifest.get("retention_days"),
                json.dumps(manifest, ensure_ascii=False, sort_keys=True),
            ),
        )


def load_runtime_manifest(cfg: dict[str, Any], *, database: Any | None = None) -> dict[str, Any]:
    manifest = cfg.get("__operational_manifest", {})
    if isinstance(manifest, dict) and manifest:
        return dict(manifest)
    cached = read_runtime_manifest_cache(cfg)
    if cached:
        return cached
    db_path = str(cfg.get("storage", {}).get("db_path", "") or "")
    target = database or db_path
    if not target:
        return {}
    ctx, _ = _with_connection(target)
    with ctx as conn:
        try:
            row = conn.execute(
                "select manifest_json from runtime_manifest order by id desc limit 1"
            ).fetchone()
        except Exception:
            return {}
        if row is None:
            return {}
        try:
            payload = json.loads(row["manifest_json"])
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}
