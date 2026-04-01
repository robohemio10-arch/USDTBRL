from pathlib import Path

import pytest

from smartcrypto.infra.database import SQLiteDatabase
from smartcrypto.state.store import StateStore


def test_operational_identity_blocks_mismatch(tmp_path: Path) -> None:
    db_path = tmp_path / "runtime.sqlite"
    database = SQLiteDatabase(str(db_path))
    store = StateStore(str(db_path), database=database)
    store.ensure_operational_identity(db_role="paper", profile_id="paper_default", symbol="USDTBRL")
    with pytest.raises(ValueError, match="Identidade operacional do banco divergente"):
        store.ensure_operational_identity(db_role="live", profile_id="live", symbol="USDTBRL")
