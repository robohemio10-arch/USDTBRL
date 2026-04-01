from __future__ import annotations

from typing import Any


def fallback_price_brl(cfg: dict[str, Any]) -> float:
    simulation_cfg = cfg.get("simulation", {}) or {}
    try:
        return float(simulation_cfg.get("mock_price_brl", 5.2) or 5.2)
    except Exception:
        return 5.2
