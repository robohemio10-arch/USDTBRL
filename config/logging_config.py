from __future__ import annotations

from typing import Any


def build_logging_config(log_dir: str = "data/logs", console: bool = True) -> dict[str, Any]:
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "level": "INFO",
            },
            "file": {
                "class": "logging.FileHandler",
                "formatter": "standard",
                "filename": f"{log_dir.rstrip('/')}/app.log",
                "encoding": "utf-8",
                "level": "INFO",
            },
        },
        "root": {
            "handlers": ["console", "file"] if console else ["file"],
            "level": "INFO",
        },
    }
