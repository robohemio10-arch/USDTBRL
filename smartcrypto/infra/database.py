from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pandas as pd


class SQLiteDatabase:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def read_sql(self, query: str, params: tuple[object, ...] = ()) -> pd.DataFrame:
        with self.connect() as conn:
            return pd.read_sql_query(query, conn, params=params)

    def table_exists(self, name: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "select 1 from sqlite_master where type='table' and name=?",
                (name,),
            ).fetchone()
        return row is not None
