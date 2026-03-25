from __future__ import annotations

import os
from pathlib import Path

from smartcrypto.common.utils import project_root_from_config_path


def dotenv_path_from_cfg(cfg_path: str | Path) -> Path:
    return project_root_from_config_path(cfg_path) / ".env"


def load_dotenv_file(path: str | Path | None = None) -> Path | None:
    dotenv_path = Path(path) if path else Path.cwd() / ".env"
    if not dotenv_path.exists():
        return None
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
    return dotenv_path


def resolve_env(name: str, default: str = "", *, dotenv_path: str | Path | None = None) -> str:
    load_dotenv_file(dotenv_path)
    return str(os.getenv(name, default) or default)


def load_dotenv_map(path: str | Path) -> dict[str, str]:
    env_path = Path(path)
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def save_dotenv_map(path: str | Path, payload: dict[str, str]) -> None:
    env_path = Path(path)
    desired_order = [
        "BINANCE_API_KEY",
        "BINANCE_API_SECRET",
        "NTFY_SERVER",
        "NTFY_TOPIC",
        "NTFY_TOKEN",
        "NTFY_USERNAME",
        "NTFY_PASSWORD",
    ]
    keys = [key for key in desired_order if key in payload] + [
        key for key in payload.keys() if key not in desired_order
    ]
    lines: list[str] = []
    for key in keys:
        value = str(payload.get(key, "") or "")
        safe_value = value.replace("\\", "\\\\").replace('"', '\"')
        lines.append(f'{key}="{safe_value}"')
        os.environ[key] = value
    env_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def update_dotenv_values(path: str | Path, updates: dict[str, str]) -> None:
    values = load_dotenv_map(path)
    for key, value in updates.items():
        values[str(key)] = str(value or "")
    save_dotenv_map(path, values)
