from __future__ import annotations

from pathlib import Path
from typing import Any

OFFICIAL_PAPER_PROFILE_ID = "paper_7d"
OFFICIAL_PAPER_PROFILE_VERSION = "2026.03.26"
OFFICIAL_PAPER_PROTOCOL_VERSION = "paper-v1"
OFFICIAL_PAPER_CONFIG_NAME = "paper_7d.yml"
OFFICIAL_PAPER_FLAGS_NAME = "feature_flags_paper_7d.yaml"


def is_official_paper_profile(
    cfg: dict[str, Any] | None = None,
    *,
    config_path: str | Path | None = None,
) -> bool:
    runtime = dict((cfg or {}).get("runtime", {}) or {})
    profile = str(runtime.get("experiment_profile", "") or "").strip().lower()
    protocol = str(runtime.get("protocol_version", "") or "").strip().lower()
    return profile == OFFICIAL_PAPER_PROFILE_ID or protocol == OFFICIAL_PAPER_PROTOCOL_VERSION


def build_paper_profile_metadata(
    cfg: dict[str, Any] | None = None,
    *,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    runtime = dict((cfg or {}).get("runtime", {}) or {})
    official = is_official_paper_profile(cfg, config_path=config_path)
    return {
        "official": bool(official),
        "profile_id": str(runtime.get("experiment_profile", "") or (OFFICIAL_PAPER_PROFILE_ID if official else "")),
        "profile_version": str(
            runtime.get("experiment_profile_version", "")
            or runtime.get("profile_version", "")
            or (OFFICIAL_PAPER_PROFILE_VERSION if official else "")
        ),
        "protocol_version": str(runtime.get("protocol_version", "") or (OFFICIAL_PAPER_PROTOCOL_VERSION if official else "")),
        "frozen": bool(runtime.get("profile_frozen", official)),
        "session_label": str(runtime.get("session_label", "") or runtime.get("experiment_profile", "") or ""),
        "config_name": Path(config_path).name if config_path else "",
    }


def validate_paper_profile(
    cfg: dict[str, Any],
    *,
    config_path: str | Path | None = None,
    feature_flags: dict[str, bool] | None = None,
) -> dict[str, Any]:
    metadata = build_paper_profile_metadata(cfg, config_path=config_path)
    errors: list[str] = []
    warnings: list[str] = []
    flags = dict(feature_flags or cfg.get("__feature_flags", {}) or {})

    if not metadata["official"]:
        return {
            **metadata,
            "recognized": False,
            "errors": errors,
            "warnings": warnings,
        }

    execution = dict(cfg.get("execution", {}) or {})
    runtime = dict(cfg.get("runtime", {}) or {})

    if str(execution.get("mode", "") or "").strip().lower() != "paper":
        errors.append("Perfil oficial paper_7d exige execution.mode=paper.")
    if bool(execution.get("allow_live", False)):
        errors.append("Perfil oficial paper_7d bloqueia execution.allow_live=true.")
    if not bool(runtime.get("single_instance_enabled", False)):
        errors.append("Perfil oficial paper_7d exige runtime.single_instance_enabled=true.")
    if str(metadata["profile_id"]) != OFFICIAL_PAPER_PROFILE_ID:
        errors.append("Perfil oficial paper_7d exige runtime.experiment_profile=paper_7d.")
    if str(metadata["protocol_version"]) != OFFICIAL_PAPER_PROTOCOL_VERSION:
        errors.append("Perfil oficial paper_7d exige runtime.protocol_version=paper-v1.")
    if not bool(metadata["frozen"]):
        errors.append("Perfil oficial paper_7d exige runtime.profile_frozen=true.")
    if not str(runtime.get("instance_lock_path", "") or "").strip():
        errors.append("Perfil oficial paper_7d exige runtime.instance_lock_path configurado.")

    if flags:
        if not bool(flags.get("research.shadow_mode_enabled", False)):
            errors.append("Perfil oficial paper_7d exige research.shadow_mode_enabled=true.")
        if not bool(flags.get("research.paper_decision_enabled", False)):
            errors.append("Perfil oficial paper_7d exige research.paper_decision_enabled=true.")
        if bool(flags.get("research.live_partial_enabled", False)):
            errors.append("Perfil oficial paper_7d exige research.live_partial_enabled=false.")
    else:
        warnings.append("Feature flags do perfil oficial paper_7d ainda não foram carregadas.")

    return {
        **metadata,
        "recognized": True,
        "errors": errors,
        "warnings": warnings,
    }
