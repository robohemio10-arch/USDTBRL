from __future__ import annotations

import json
from typing import Any

from smartcrypto.infra.database import SQLiteDatabase


class BotEventStore:
    def __init__(self, database: SQLiteDatabase, clock) -> None:
        self.database = database
        self.clock = clock

    def add(self, level: str, event: str, details: dict[str, Any] | None = None) -> None:
        with self.database.connect() as conn:
            conn.execute(
                "insert into bot_events(ts, level, event, details_json) values (?, ?, ?, ?)",
                (self.clock(), level, event, json.dumps(details or {})),
            )
