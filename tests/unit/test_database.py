from pathlib import Path

from smartcrypto.infra.database import SQLiteDatabase


def test_sqlite_database_can_create_and_query_table(tmp_path: Path) -> None:
    db = SQLiteDatabase(str(tmp_path / "unit.sqlite"))

    with db.connect() as conn:
        conn.execute("create table sample(id integer primary key, value text)")
        conn.execute("insert into sample(value) values (?)", ("ok",))

    assert db.table_exists("sample")
    frame = db.read_sql("select * from sample")
    assert frame.to_dict(orient="records") == [{"id": 1, "value": "ok"}]
