from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone


def new_bot_order_id(side: str, reason: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    return f"{side.upper()}-{reason}-{stamp}-{uuid.uuid4().hex[:8]}"


def client_order_id_prefix(bot_order_id: str) -> str:
    digest = hashlib.sha1(bot_order_id.encode("utf-8")).hexdigest()[:18]
    return f"SC{digest}".upper()
