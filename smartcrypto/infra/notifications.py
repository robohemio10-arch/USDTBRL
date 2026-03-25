from __future__ import annotations

from typing import Any, cast

import requests

from smartcrypto.common.env import resolve_env


class NtfyClient:
    def __init__(self, cfg: dict[str, Any] | None = None) -> None:
        cfg = cfg or {}
        topic_env = str(cfg.get("topic_env", "NTFY_TOPIC") or "NTFY_TOPIC")
        server_env = str(cfg.get("server_env", "NTFY_SERVER") or "NTFY_SERVER")
        token_env = str(cfg.get("token_env", "NTFY_TOKEN") or "NTFY_TOKEN")
        username_env = str(cfg.get("username_env", "NTFY_USERNAME") or "NTFY_USERNAME")
        password_env = str(cfg.get("password_env", "NTFY_PASSWORD") or "NTFY_PASSWORD")
        self.enabled = bool(cfg.get("enabled", False))
        self.server = str(resolve_env(server_env, "https://ntfy.sh") or "https://ntfy.sh").rstrip(
            "/"
        )
        self.topic = str(resolve_env(topic_env, "") or "")
        self.token = str(resolve_env(token_env, "") or "")
        self.username = str(resolve_env(username_env, "") or "")
        self.password = str(resolve_env(password_env, "") or "")
        self.timeout = float(cfg.get("timeout_seconds", 10) or 10)
        self.default_tags = ",".join(
            str(x) for x in (cfg.get("default_tags") or []) if str(x).strip()
        )

    def is_ready(self) -> bool:
        return self.enabled and bool(self.topic)

    def publish(
        self,
        *,
        title: str,
        message: str,
        priority: str = "default",
        tags: str = "",
        click: str = "",
    ) -> dict[str, Any]:
        if not self.is_ready():
            raise RuntimeError("NTFY não está habilitado ou o tópico não foi configurado.")
        headers = {
            "Title": title,
            "Priority": priority,
        }
        final_tags = ",".join(x for x in [self.default_tags, tags] if x)
        if final_tags:
            headers["Tags"] = final_tags
        if click:
            headers["Click"] = click
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        auth = (self.username, self.password) if self.username and self.password else None
        resp = requests.post(
            f"{self.server}/{self.topic}",
            data=message.encode("utf-8"),
            headers=headers,
            timeout=self.timeout,
            auth=auth,
        )
        try:
            payload = resp.json()
        except Exception:
            payload = {"status_code": resp.status_code, "text": resp.text[:500]}
        if resp.status_code >= 400:
            raise RuntimeError(f"NTFY HTTP {resp.status_code}: {payload}")
        return cast(dict[str, Any], payload)
