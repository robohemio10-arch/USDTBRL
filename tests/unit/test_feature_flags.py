from pathlib import Path

from smartcrypto.runtime.feature_flags import load_feature_flags


def test_load_feature_flags_supports_flat_payload(tmp_path: Path) -> None:
    path = tmp_path / "feature_flags.yaml"
    path.write_text("shadow_mode: true\nruntime_v2: false\n", encoding="utf-8")

    payload = load_feature_flags(path)

    assert payload == {"shadow_mode": True, "runtime_v2": False}


def test_load_feature_flags_supports_nested_payload(tmp_path: Path) -> None:
    path = tmp_path / "feature_flags.yaml"
    path.write_text(
        "research:\n  shadow_mode_enabled: true\nruntime:\n  scheduler_enabled: false\n",
        encoding="utf-8",
    )

    payload = load_feature_flags(path)

    assert payload == {
        "research.shadow_mode_enabled": True,
        "runtime.scheduler_enabled": False,
    }
