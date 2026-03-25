from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from smartcrypto.common.constants import DEFAULT_CONFIG_PATH
from smartcrypto.common.utils import project_root_from_config_path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def project_root_from_cfg(cfg: dict[str, Any]) -> Path:
    cfg_path = str(cfg.get("__config_path", str(DEFAULT_CONFIG_PATH)) or str(DEFAULT_CONFIG_PATH))
    return project_root_from_config_path(cfg_path)


def log_dir_from_cfg(cfg: dict[str, Any]) -> Path:
    raw = str(cfg.get("logging", {}).get("dir", "data/logs") or "data/logs")
    path = Path(raw)
    if not path.is_absolute():
        path = project_root_from_cfg(cfg) / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_file_from_cfg(cfg: dict[str, Any], name: str = "bot.jsonl") -> Path:
    return log_dir_from_cfg(cfg) / name


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


class BotLogger:
    def __init__(self, cfg: dict[str, Any], name: str = "bot") -> None:
        self.cfg = cfg
        self.name = name
        self.path = log_file_from_cfg(cfg, f"{name}.jsonl")
        self.console = bool(cfg.get("logging", {}).get("console", True))

    def event(self, level: str, event: str, **fields: Any) -> None:
        payload = {
            "ts": utc_now(),
            "logger": self.name,
            "level": str(level).upper(),
            "event": str(event),
            "fields": fields,
        }
        append_jsonl(self.path, payload)
        if self.console:
            print(f"[{payload['level']}] {event} {fields}".strip())

    def info(self, event: str, **fields: Any) -> None:
        self.event("INFO", event, **fields)

    def warning(self, event: str, **fields: Any) -> None:
        self.event("WARNING", event, **fields)

    def error(self, event: str, **fields: Any) -> None:
        self.event("ERROR", event, **fields)


def read_recent_logs(
    cfg: dict[str, Any], name: str = "bot", limit: int = 200
) -> list[dict[str, Any]]:
    path = log_file_from_cfg(cfg, f"{name}.jsonl")
    if not path.exists():
        return []
    rows = path.read_text(encoding="utf-8").splitlines()[-max(1, int(limit)) :]
    result: list[dict[str, Any]] = []
    for line in rows:
        try:
            result.append(json.loads(line))
        except Exception:
            continue
    return result
