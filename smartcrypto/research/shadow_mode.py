from __future__ import annotations

from typing import Any

import pandas as pd

from smartcrypto.research.baseline_model import LinearBaselineModel, min_training_rows
from smartcrypto.research.datasets import anchored_walkforward_splits, build_training_dataset, dataset_name
from smartcrypto.research.entry_filter import baseline_entry_decision, compare_entry_filters, heuristic_entry_decision
from smartcrypto.research.evaluation import (
    compare_entry_filters_by_segment,
    compare_execution_quality_by_segment,
    compare_position_manager_by_segment,
    compare_shadow_method_metrics,
    evaluate_shadow_predictions,
)
from smartcrypto.research.execution_quality import (
    ExecutionQualityModel,
    baseline_execution_decision,
    compare_execution_quality,
    heuristic_execution_decision,
)
from smartcrypto.research.features import BASE_FEATURE_NAMES, build_feature_frame, feature_snapshot
from smartcrypto.research.ml_store import MLStore
from smartcrypto.research.position_manager import (
    PositionManagerModel,
    baseline_position_decision,
    compare_position_manager,
    heuristic_position_decision,
)


def shadow_mode_enabled(feature_flags: dict[str, bool]) -> bool:
    return bool(
        feature_flags.get("research.shadow_mode_enabled")
        or feature_flags.get("shadow_mode")
        or feature_flags.get("shadow_mode_enabled")
    )


def predict_next_return(feature_row: pd.Series) -> float:
    return float(heuristic_entry_decision(feature_row, {}).predicted_net_return)


def _ml_store_from_cfg(cfg: dict[str, Any]) -> MLStore:
    storage = cfg.get("storage", {})
    db_path = str(storage.get("ml_store_path", "data/ml_store.sqlite"))
    return MLStore(db_path)


def _baseline_shadow_rows(
    cfg: dict[str, Any], ohlcv: pd.DataFrame
) -> tuple[
    list[dict[str, float]],
    dict[str, Any],
    LinearBaselineModel | None,
    ExecutionQualityModel | None,
    PositionManagerModel | None,
    pd.DataFrame,
]:
    data = build_training_dataset(str(cfg.get("market", {}).get("symbol", "UNKNOWN")), ohlcv, cfg)
    purge_gap = int(cfg.get("research", {}).get("walk_forward_purge_gap", 1) or 1)
    split_rows = anchored_walkforward_splits(
        data,
        folds=max(2, int(cfg.get("research", {}).get("shadow_folds", 3) or 3)),
        train_ratio=0.65,
        min_train_rows=40,
        min_test_rows=10,
        purge_gap=purge_gap,
    )
    rows: list[dict[str, float]] = []
    baseline_only_rows: list[dict[str, float]] = []
    heuristic_only_rows: list[dict[str, float]] = []
    comparison_rows: list[dict[str, Any]] = []
    execution_rows: list[dict[str, Any]] = []
    position_rows: list[dict[str, Any]] = []
    fold_metrics: list[dict[str, Any]] = []
    latest_model: LinearBaselineModel | None = None
    latest_exec_model: ExecutionQualityModel | None = None
    latest_position_model: PositionManagerModel | None = None
    minimum = min_training_rows(len(BASE_FEATURE_NAMES))
    for split in split_rows:
        train = split["train"]
        test = split["test"]
        if len(train) < minimum or test.empty:
            continue
        entry_model = LinearBaselineModel(feature_names=list(BASE_FEATURE_NAMES)).fit(train, target_column="target_net_return_h")
        exec_model = ExecutionQualityModel(feature_names=list(BASE_FEATURE_NAMES)).fit(train)
        position_model = PositionManagerModel(feature_names=list(BASE_FEATURE_NAMES)).fit(train)
        latest_model = entry_model
        latest_exec_model = exec_model
        latest_position_model = position_model
        preds = entry_model.predict_frame(test)
        for idx, row in test.reset_index(drop=True).iterrows():
            prediction = preds.iloc[idx]
            baseline_decision = baseline_entry_decision(entry_model, row, cfg)
            heuristic_decision = heuristic_entry_decision(row, cfg)
            baseline_exec = baseline_execution_decision(exec_model, row, cfg)
            heuristic_exec = heuristic_execution_decision(row, cfg)
            baseline_position = baseline_position_decision(row, cfg, model=position_model, execution_model=exec_model)
            heuristic_position = heuristic_position_decision(row, cfg)
            realized = float(row.get("target_net_return_h", 0.0))
            target_positive = float(row.get("target_positive_net_h", 0.0))
            regime_bucket = row.get("regime_bucket", "unknown")
            hour_bucket = int(row.get("hour_bucket", -1) or -1)
            rows.append(
                {
                    "predicted_return": float(prediction["predicted_net_return"]),
                    "realized_return": realized,
                    "score": float(prediction["score"]),
                    "predicted_positive_net_prob": float(prediction["predicted_positive_net_prob"]),
                    "target_positive_net": target_positive,
                    "fold": int(split["fold"]),
                }
            )
            baseline_only_rows.append(
                {
                    "predicted_return": baseline_decision.predicted_net_return,
                    "realized_return": realized,
                    "score": baseline_decision.score,
                    "predicted_positive_net_prob": baseline_decision.predicted_positive_net_prob,
                    "target_positive_net": target_positive,
                }
            )
            heuristic_only_rows.append(
                {
                    "predicted_return": heuristic_decision.predicted_net_return,
                    "realized_return": realized,
                    "score": heuristic_decision.score,
                    "predicted_positive_net_prob": heuristic_decision.predicted_positive_net_prob,
                    "target_positive_net": target_positive,
                }
            )
            comparison_rows.append(
                {
                    "realized_net_return": realized,
                    "target_positive_net": target_positive,
                    "baseline_predicted_net_return": baseline_decision.predicted_net_return,
                    "baseline_predicted_positive_net_prob": baseline_decision.predicted_positive_net_prob,
                    "baseline_gate": baseline_decision.gate,
                    "heuristic_predicted_net_return": heuristic_decision.predicted_net_return,
                    "heuristic_predicted_positive_net_prob": heuristic_decision.predicted_positive_net_prob,
                    "heuristic_gate": heuristic_decision.gate,
                    "regime_bucket": regime_bucket,
                    "hour_bucket": hour_bucket,
                }
            )
            execution_rows.append(
                {
                    "realized_execution_cost_bps": float(row.get("target_execution_cost_bps_h", 0.0)),
                    "realized_fill_success": float(row.get("target_fill_success_h", 0.0)),
                    "baseline_expected_cost_bps": baseline_exec.expected_cost_bps,
                    "baseline_fill_probability": baseline_exec.fill_probability,
                    "baseline_score": baseline_exec.score,
                    "baseline_gate": baseline_exec.gate,
                    "heuristic_expected_cost_bps": heuristic_exec.expected_cost_bps,
                    "heuristic_fill_probability": heuristic_exec.fill_probability,
                    "heuristic_score": heuristic_exec.score,
                    "heuristic_gate": heuristic_exec.gate,
                    "regime_bucket": regime_bucket,
                    "hour_bucket": hour_bucket,
                }
            )
            position_rows.append(
                {
                    "realized_net_return": realized,
                    "baseline_action": baseline_position.action,
                    "baseline_confidence": baseline_position.confidence,
                    "baseline_expected_drawdown": baseline_position.expected_drawdown,
                    "heuristic_action": heuristic_position.action,
                    "heuristic_confidence": heuristic_position.confidence,
                    "heuristic_expected_drawdown": heuristic_position.expected_drawdown,
                    "regime_bucket": regime_bucket,
                    "hour_bucket": hour_bucket,
                }
            )
        fold_metrics.append(
            {
                "fold": int(split["fold"]),
                "train_rows": int(len(train)),
                "test_rows": int(len(test)),
                "purge_gap": int(split.get("purge_gap", purge_gap)),
            }
        )
    metadata = {
        "folds": fold_metrics,
        "purge_gap": purge_gap,
        "method_comparison": compare_shadow_method_metrics(baseline_only_rows, heuristic_only_rows),
        "entry_filter_comparison": compare_entry_filters(comparison_rows),
        "execution_quality_comparison": compare_execution_quality(execution_rows),
        "position_manager_comparison": compare_position_manager(position_rows),
        "entry_filter_segment_comparison": compare_entry_filters_by_segment(comparison_rows),
        "execution_quality_segment_comparison": compare_execution_quality_by_segment(execution_rows),
        "position_manager_segment_comparison": compare_position_manager_by_segment(position_rows),
    }
    return rows, metadata, latest_model, latest_exec_model, latest_position_model, data


def _heuristic_shadow_rows(cfg: dict[str, Any], ohlcv: pd.DataFrame) -> tuple[list[dict[str, float]], dict[str, Any], pd.DataFrame]:
    data = build_training_dataset(str(cfg.get("market", {}).get("symbol", "UNKNOWN")), ohlcv, cfg)
    rows: list[dict[str, float]] = []
    gates: list[dict[str, Any]] = []
    execution_rows: list[dict[str, Any]] = []
    position_rows: list[dict[str, Any]] = []
    for _, row in data.iterrows():
        decision = heuristic_entry_decision(row, cfg)
        realized = float(row.get("target_net_return_h", 0.0))
        target_positive = float(row.get("target_positive_net_h", 0.0))
        regime_bucket = row.get("regime_bucket", "unknown")
        hour_bucket = int(row.get("hour_bucket", -1) or -1)
        rows.append(
            {
                "predicted_return": float(decision.predicted_net_return),
                "realized_return": realized,
                "score": float(decision.score),
                "predicted_positive_net_prob": float(decision.predicted_positive_net_prob),
                "target_positive_net": target_positive,
                "fold": 0,
            }
        )
        exec_decision = heuristic_execution_decision(row, cfg)
        execution_rows.append(
            {
                "realized_execution_cost_bps": float(row.get("target_execution_cost_bps_h", 0.0)),
                "realized_fill_success": float(row.get("target_fill_success_h", 0.0)),
                "baseline_expected_cost_bps": float(exec_decision.expected_cost_bps),
                "baseline_fill_probability": float(exec_decision.fill_probability),
                "baseline_score": float(exec_decision.score),
                "baseline_gate": bool(exec_decision.gate),
                "heuristic_expected_cost_bps": float(exec_decision.expected_cost_bps),
                "heuristic_fill_probability": float(exec_decision.fill_probability),
                "heuristic_score": float(exec_decision.score),
                "heuristic_gate": bool(exec_decision.gate),
                "regime_bucket": regime_bucket,
                "hour_bucket": hour_bucket,
            }
        )
        position = heuristic_position_decision(row, cfg)
        position_rows.append(
            {
                "realized_net_return": float(realized),
                "baseline_action": position.action,
                "baseline_confidence": position.confidence,
                "baseline_expected_drawdown": position.expected_drawdown,
                "heuristic_action": position.action,
                "heuristic_confidence": position.confidence,
                "heuristic_expected_drawdown": position.expected_drawdown,
                "regime_bucket": regime_bucket,
                "hour_bucket": hour_bucket,
            }
        )
        gates.append(
            {
                "realized_net_return": float(realized),
                "target_positive_net": target_positive,
                "baseline_predicted_net_return": float(decision.predicted_net_return),
                "baseline_predicted_positive_net_prob": float(decision.predicted_positive_net_prob),
                "baseline_gate": bool(decision.gate),
                "heuristic_predicted_net_return": float(decision.predicted_net_return),
                "heuristic_predicted_positive_net_prob": float(decision.predicted_positive_net_prob),
                "heuristic_gate": bool(decision.gate),
                "regime_bucket": regime_bucket,
                "hour_bucket": hour_bucket,
            }
        )
    return rows, {
        "entry_filter_comparison": compare_entry_filters(gates),
        "execution_quality_comparison": compare_execution_quality(execution_rows),
        "position_manager_comparison": compare_position_manager(position_rows),
        "entry_filter_segment_comparison": compare_entry_filters_by_segment(gates),
        "execution_quality_segment_comparison": compare_execution_quality_by_segment(execution_rows),
        "position_manager_segment_comparison": compare_position_manager_by_segment(position_rows),
        "method_comparison": {"winner": 0.0},
    }, data


def _latest_entry_filter(cfg: dict[str, Any], ohlcv: pd.DataFrame, model: LinearBaselineModel | None, methodology: str) -> dict[str, Any]:
    latest_features = feature_snapshot(ohlcv)
    heuristic = heuristic_entry_decision(latest_features, cfg)
    if model is not None and methodology.startswith("linear_baseline"):
        baseline = baseline_entry_decision(model, latest_features, cfg)
        chosen = baseline
    else:
        baseline = None
        chosen = heuristic
    payload = {"selected": chosen.as_dict(), "heuristic": heuristic.as_dict(), "feature_snapshot": latest_features}
    if baseline is not None:
        payload["baseline"] = baseline.as_dict() | {"calibration_metrics": dict(model.calibration_metrics_ or {})}
        payload["baseline_vs_heuristic_gate_delta"] = int(baseline.gate) - int(heuristic.gate)
    return payload


def _latest_position_manager(
    cfg: dict[str, Any],
    ohlcv: pd.DataFrame,
    position_model: PositionManagerModel | None,
    execution_model: ExecutionQualityModel | None,
    methodology: str,
) -> dict[str, Any]:
    latest_features = feature_snapshot(ohlcv)
    heuristic = heuristic_position_decision(latest_features, cfg)
    if position_model is not None and methodology.startswith("linear_baseline"):
        baseline = baseline_position_decision(latest_features, cfg, model=position_model, execution_model=execution_model)
        chosen = baseline
    else:
        baseline = None
        chosen = heuristic
    payload = {"selected": chosen.as_dict(), "heuristic": heuristic.as_dict(), "feature_snapshot": latest_features}
    if baseline is not None:
        payload["baseline"] = baseline.as_dict() | {"calibration_metrics": position_model.as_dict().get("recovery_model", {}).get("calibration_metrics", {})}
        payload["baseline_vs_heuristic_action_delta"] = 0 if baseline.action == heuristic.action else 1
    return payload


def _latest_execution_quality(cfg: dict[str, Any], ohlcv: pd.DataFrame, model: ExecutionQualityModel | None, methodology: str) -> dict[str, Any]:
    latest_features = feature_snapshot(ohlcv)
    heuristic = heuristic_execution_decision(latest_features, cfg)
    if model is not None and methodology.startswith("linear_baseline"):
        baseline = baseline_execution_decision(model, latest_features, cfg)
        chosen = baseline
    else:
        baseline = None
        chosen = heuristic
    payload = {"selected": chosen.as_dict(), "heuristic": heuristic.as_dict(), "feature_snapshot": latest_features}
    if baseline is not None:
        payload["baseline"] = baseline.as_dict() | {"calibration_metrics": model.as_dict().get("calibration_metrics", {})}
        payload["baseline_vs_heuristic_gate_delta"] = int(baseline.gate) - int(heuristic.gate)
    return payload


def run_shadow_mode_on_dataframe(
    cfg: dict[str, Any],
    ohlcv: pd.DataFrame,
    *,
    feature_flags: dict[str, bool] | None = None,
) -> dict[str, Any]:
    flags = feature_flags or {}
    enabled = shadow_mode_enabled(flags)
    if not enabled:
        return {"enabled": False, "rows": 0, "predictions": [], "metrics": evaluate_shadow_predictions([])}

    latest_model: LinearBaselineModel | None = None
    latest_exec_model: ExecutionQualityModel | None = None
    latest_position_model: PositionManagerModel | None = None
    training_data = pd.DataFrame()
    if len(ohlcv) >= min_training_rows(len(BASE_FEATURE_NAMES)) + 20:
        rows, metadata, latest_model, latest_exec_model, latest_position_model, training_data = _baseline_shadow_rows(cfg, ohlcv)
        methodology = "linear_baseline_walkforward_shadow" if rows else "feature_heuristic_shadow_mode"
    else:
        rows, metadata, training_data = _heuristic_shadow_rows(cfg, ohlcv)
        methodology = "feature_heuristic_shadow_mode"
    if not rows:
        rows, metadata, training_data = _heuristic_shadow_rows(cfg, ohlcv)
        methodology = "feature_heuristic_shadow_mode"

    metrics = evaluate_shadow_predictions(rows)
    latest_features = feature_snapshot(ohlcv)
    entry_filter = _latest_entry_filter(cfg, ohlcv, latest_model, methodology)
    execution_quality = _latest_execution_quality(cfg, ohlcv, latest_exec_model, methodology)
    position_manager = _latest_position_manager(cfg, ohlcv, latest_position_model, latest_exec_model, methodology)
    entry_filter["execution_adjusted_gate"] = bool(entry_filter.get("selected", {}).get("gate", False) and execution_quality.get("selected", {}).get("gate", False))
    empirical_execution = dict(training_data.attrs.get("empirical_execution", {})) if isinstance(training_data, pd.DataFrame) else {}
    return {
        "enabled": True,
        "rows": int(len(rows)),
        "lookback_bars": int(cfg.get("market", {}).get("research_lookback_bars", len(ohlcv)) or len(ohlcv)),
        "predictions": rows[-25:],
        "metrics": metrics,
        "methodology": methodology,
        "latest_feature_snapshot": latest_features,
        "entry_filter": entry_filter,
        "execution_quality": execution_quality,
        "position_manager": position_manager,
        "validation": metadata,
        "empirical_execution": empirical_execution,
    }


def run_shadow_mode(
    cfg: dict[str, Any],
    exchange: Any,
    store: Any | None = None,
    *,
    feature_flags: dict[str, bool] | None = None,
) -> dict[str, Any]:
    bars = int(cfg["market"].get("research_lookback_bars", 800))
    data = exchange.fetch_ohlcv(cfg["market"]["timeframe"], bars)
    result = run_shadow_mode_on_dataframe(cfg, data, feature_flags=feature_flags)
    if result.get("enabled"):
        if store is not None:
            store.add_research_run(
                "shadow_mode",
                "research.shadow_mode",
                {"bars": bars, "timeframe": cfg["market"]["timeframe"]},
                result,
            )
        ml_store = _ml_store_from_cfg(cfg)
        symbol = str(cfg.get("market", {}).get("symbol", "UNKNOWN"))
        timeframe = str(cfg.get("market", {}).get("timeframe", "1m"))
        ml_store.add_feature_snapshot(symbol, timeframe, dataset_name(symbol), result.get("latest_feature_snapshot", {}))
        ml_store.add_shadow_prediction(
            symbol,
            timeframe,
            str(result.get("methodology", "unknown")),
            {
                "metrics": result.get("metrics", {}),
                "entry_filter": result.get("entry_filter", {}),
                "execution_quality": result.get("execution_quality", {}),
                "position_manager": result.get("position_manager", {}),
                "validation": result.get("validation", {}),
                "rows": int(result.get("rows", 0)),
                "empirical_execution": result.get("empirical_execution", {}),
            },
        )
        if str(result.get("methodology", "")).startswith("linear_baseline"):
            training_data = build_training_dataset(symbol, data, cfg)
            model = LinearBaselineModel(feature_names=list(BASE_FEATURE_NAMES)).fit(training_data.iloc[:-1].copy(), target_column="target_net_return_h")
            exec_model = ExecutionQualityModel(feature_names=list(BASE_FEATURE_NAMES)).fit(training_data.iloc[:-1].copy())
            position_model = PositionManagerModel(feature_names=list(BASE_FEATURE_NAMES)).fit(training_data.iloc[:-1].copy())
            ml_store.register_model(
                "entry_filter_baseline",
                "v3",
                metrics={**result.get("metrics", {}), "comparison": result.get("validation", {}).get("entry_filter_comparison", {})},
                params={"feature_names": list(BASE_FEATURE_NAMES), "lookback_bars": bars, "timeframe": timeframe},
                artifact=model.as_dict(),
            )
            ml_store.register_model(
                "execution_quality_baseline",
                "v2",
                metrics={"comparison": result.get("validation", {}).get("execution_quality_comparison", {}), "empirical_execution": result.get("empirical_execution", {})},
                params={"feature_names": list(BASE_FEATURE_NAMES), "lookback_bars": bars, "timeframe": timeframe},
                artifact=exec_model.as_dict(),
            )
            ml_store.register_model(
                "position_manager_baseline",
                "v2",
                metrics={"comparison": result.get("validation", {}).get("position_manager_comparison", {})},
                params={"feature_names": list(BASE_FEATURE_NAMES), "lookback_bars": bars, "timeframe": timeframe},
                artifact=position_model.as_dict(),
            )
    return result
