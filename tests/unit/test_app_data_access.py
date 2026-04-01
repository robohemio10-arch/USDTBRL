from pathlib import Path

import sqlite3

from smartcrypto.app import data_access


def test_query_df_reads_from_sqlite_in_readonly_mode(tmp_path) -> None:
    db_path = tmp_path / "dashboard.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("create table trades (id integer primary key, price_brl real)")
        conn.execute("insert into trades (price_brl) values (5.25)")
        conn.commit()

    cfg = {"storage": {"db_path": str(db_path)}}
    df = data_access.query_df(cfg, "select * from trades")

    assert list(df.columns) == ["id", "price_brl"]
    assert float(df.iloc[0]["price_brl"]) == 5.25


def test_db_path_from_cfg_resolves_relative_path_from_project_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(data_access, "root_dir", lambda: tmp_path)
    cfg = {"storage": {"db_path": "data/live.sqlite"}}

    assert data_access.db_path_from_cfg(cfg) == tmp_path / "data" / "live.sqlite"
