from pathlib import Path

from smartcrypto.infra.database import SQLiteDatabase
from smartcrypto.runtime.ai_observability import recent_ai_observations, record_ai_observation


def test_record_ai_observation_persists_real_baseline_and_run_id(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.sqlite"
    database = SQLiteDatabase(str(db_path))
    cfg = {
        "__run_id": "run-test-001",
        "execution": {"mode": "paper"},
        "market": {"symbol": "USDT/BRL", "timeframe": "1m"},
        "__operational_manifest": {"run_id": "run-test-001"},
    }

    record_ai_observation(
        cfg,
        database,
        cycle_id="cycle-1",
        baseline_decision={
            "is_real": True,
            "entry_gate": True,
            "position_action": "wait",
        },
        ai_decision={
            "stage": "shadow",
            "effective_entry_gate": False,
            "position_action": "wait",
        },
        context={"source": "unit-test"},
    )

    rows = recent_ai_observations(database, limit=5)
    assert len(rows) == 1
    row = rows.iloc[0]
    assert row["run_id"] == "run-test-001"
    assert int(row["baseline_is_real"]) == 1
    assert int(row["baseline_entry_gate"]) == 1
    assert int(row["ai_effective_entry_gate"]) == 0
    assert int(row["divergence"]) == 1
    assert int(row["veto"]) == 1
    assert row["baseline_position_action"] == "wait"
    assert row["ai_position_action"] == "wait"