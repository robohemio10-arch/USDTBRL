from __future__ import annotations

from pathlib import Path

from smartcrypto.runtime.paper_profile import (
    OFFICIAL_PAPER_PROFILE_ID,
    OFFICIAL_PAPER_PROFILE_VERSION,
    OFFICIAL_PAPER_PROTOCOL_VERSION,
    build_paper_profile_metadata,
    is_official_paper_profile,
    validate_paper_profile,
)


def test_build_paper_profile_metadata() -> None:
    metadata = build_paper_profile_metadata(
        {
            "execution": {"mode": "paper"},
            "runtime": {
                "experiment_profile": OFFICIAL_PAPER_PROFILE_ID,
                "experiment_profile_version": OFFICIAL_PAPER_PROFILE_VERSION,
                "protocol_version": OFFICIAL_PAPER_PROTOCOL_VERSION,
                "profile_frozen": True,
                "single_instance_enabled": True,
                "instance_lock_path": "data/runtime/paper.lock.json",
            },
        }
    )
    assert metadata["profile_id"] == OFFICIAL_PAPER_PROFILE_ID
    assert metadata["official"] is True
    assert metadata["protocol_version"] == OFFICIAL_PAPER_PROTOCOL_VERSION


def test_validate_paper_profile_accepts_official_profile(tmp_path: Path) -> None:
    config_path = tmp_path / "paper_7d.yml"
    config_path.write_text("runtime: {}\n", encoding="utf-8")
    result = validate_paper_profile(
        {
            "execution": {"mode": "paper", "allow_live": False},
            "runtime": {
                "experiment_profile": OFFICIAL_PAPER_PROFILE_ID,
                "experiment_profile_version": OFFICIAL_PAPER_PROFILE_VERSION,
                "protocol_version": OFFICIAL_PAPER_PROTOCOL_VERSION,
                "profile_frozen": True,
                "single_instance_enabled": True,
                "instance_lock_path": "data/runtime/paper.lock.json",
            },
            "__feature_flags": {
                "research.paper_decision_enabled": True,
                "research.shadow_mode_enabled": True,
                "research.live_partial_enabled": False,
            },
        },
        config_path=config_path,
    )
    assert result["recognized"] is True
    assert result["errors"] == []


def test_is_official_paper_profile_false_for_other_profile() -> None:
    assert is_official_paper_profile({"runtime": {"experiment_profile": "manual"}}) is False
