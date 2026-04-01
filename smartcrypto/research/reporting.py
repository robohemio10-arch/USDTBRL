from __future__ import annotations

import json
from typing import Any

from smartcrypto.research.ml_store import MLStore


def _parse_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        return json.loads(str(value))
    except Exception:
        return {}


def generate_rollout_report(store: MLStore) -> dict[str, Any]:
    shadows = store.read_df("shadow_predictions", limit=100)
    rollout = store.read_df("rollout_events", limit=100)
    models = store.read_df("model_registry", limit=100)
    evaluation_reports = store.read_df("evaluation_reports", limit=20)
    evaluation_trades = store.read_df("evaluation_trades", limit=500)
    latest_shadow = _parse_payload(shadows.iloc[0]["payload_json"]) if not shadows.empty else {}
    latest_event = _parse_payload(rollout.iloc[0]["payload_json"]) if not rollout.empty else {}
    latest_validation = _parse_payload(evaluation_reports.iloc[0]["payload_json"]) if not evaluation_reports.empty else {}
    validation = dict(latest_shadow.get("validation", {})) if isinstance(latest_shadow, dict) else {}
    return {
        "shadow_runs": int(len(shadows)),
        "rollout_events": int(len(rollout)),
        "registered_models": int(len(models)),
        "evaluation_trade_rows": int(len(evaluation_trades)),
        "evaluation_reports": int(len(evaluation_reports)),
        "latest_shadow": latest_shadow,
        "latest_event": latest_event,
        "latest_quant_validation": latest_validation,
        "methodologies": shadows["methodology"].value_counts().to_dict() if not shadows.empty and "methodology" in shadows.columns else {},
        "rollout_stages": rollout["stage"].value_counts().to_dict() if not rollout.empty and "stage" in rollout.columns else {},
        "evaluation_methods": evaluation_trades["method"].value_counts().to_dict() if not evaluation_trades.empty and "method" in evaluation_trades.columns else {},
        "entry_filter_segments": validation.get("entry_filter_segment_comparison", {}),
        "execution_quality_segments": validation.get("execution_quality_segment_comparison", {}),
        "position_manager_segments": validation.get("position_manager_segment_comparison", {}),
        "calibration": {
            "entry_filter": latest_shadow.get("entry_filter", {}).get("baseline", {}).get("calibration_metrics", {}),
            "execution_quality": latest_shadow.get("execution_quality", {}).get("baseline", {}).get("calibration_metrics", {}),
            "position_manager": latest_shadow.get("position_manager", {}).get("baseline", {}).get("calibration_metrics", {}),
        },
    }
