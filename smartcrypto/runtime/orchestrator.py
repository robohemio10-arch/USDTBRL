from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from smartcrypto.common.constants import DEFAULT_CONFIG_PATH, LEGACY_CONFIG_PATH
from smartcrypto.common.logging_utils import BotLogger
from smartcrypto.common.utils import runtime_run_id
from smartcrypto.config import load_config, resolve_config_path as resolve_runtime_config_path
from smartcrypto.infra.binance_adapter import ExchangeAdapter
from smartcrypto.infra.database import SQLiteDatabase
from smartcrypto.runtime.audit import ensure_runtime_audit_tables, record_runtime_event
from smartcrypto.runtime.feature_flags import load_feature_flags
from smartcrypto.runtime.preflight import assert_preflight_ok, perform_preflight
from smartcrypto.runtime.runtime_manifest import build_runtime_manifest, persist_runtime_manifest
from smartcrypto.state.bot_events import BotEventStore
from smartcrypto.state.dispatch_locks import DispatchLockStore
from smartcrypto.state.order_events import OrderEventStore
from smartcrypto.state.order_projections import OrderProjectionStore
from smartcrypto.state.portfolio import Portfolio
from smartcrypto.state.position_manager import PositionManager
from smartcrypto.state.reconciliation_audit import ReconciliationAuditStore
from smartcrypto.state.snapshots import SnapshotStore
from smartcrypto.state.store import StateStore, utc_now


@dataclass(frozen=True)
class RuntimeContext:
    config: dict[str, Any]
    database: SQLiteDatabase
    store: StateStore
    position_manager: PositionManager
    portfolio: Portfolio
    order_projections: OrderProjectionStore
    order_events: OrderEventStore
    snapshots: SnapshotStore
    bot_events: BotEventStore
    dispatch_locks: DispatchLockStore
    reconciliation_audit: ReconciliationAuditStore
    exchange: ExchangeAdapter
    feature_flags: dict[str, bool]


@dataclass(frozen=True)
class RuntimeServices:
    context: RuntimeContext
    logger: BotLogger
    config_path: str


def resolve_config_path(path: str | Path | None = None) -> Path:
    return resolve_runtime_config_path(path or DEFAULT_CONFIG_PATH)


def _requested_runtime_config_path(config_path: str | Path | None = None) -> Path:
    if config_path is None:
        return resolve_config_path(DEFAULT_CONFIG_PATH).resolve()
    return resolve_config_path(config_path).resolve()


def _feature_flags_path_for_config(resolved_config_path: Path) -> Path:
    config_dir = resolved_config_path.parent
    stem = resolved_config_path.stem
    if stem and stem != "config":
        candidate = config_dir / f"feature_flags_{stem}.yaml"
        if candidate.exists():
            return candidate
    return config_dir / "feature_flags.yaml"


def bootstrap_feature_flags(config_dir: str | Path = "config") -> dict[str, bool]:
    target = Path(config_dir)
    if target.is_file():
        flags_path = _feature_flags_path_for_config(target.resolve())
    else:
        flags_path = target / "feature_flags.yaml"
    if not flags_path.exists():
        return {}
    return load_feature_flags(flags_path)


def _project_root_from_config_path(config_path: str | Path) -> Path:
    candidate = Path(config_path).resolve()
    if candidate.parent.name == "config":
        return candidate.parent.parent
    return candidate.parent


def _canonical_runtime_config_path(config_path: str | Path | None = None) -> Path:
    requested_path = _requested_runtime_config_path(config_path)
    if config_path is not None:
        requested = Path(config_path)
        if requested.name == LEGACY_CONFIG_PATH.name and requested.parent in {Path("."), Path("")}:
            canonical_path = (_project_root_from_config_path(requested_path) / DEFAULT_CONFIG_PATH).resolve()
            if canonical_path.exists():
                return canonical_path
        return requested_path
    canonical_path = (_project_root_from_config_path(requested_path) / DEFAULT_CONFIG_PATH).resolve()
    if canonical_path.exists():
        return canonical_path
    return requested_path


def _load_raw_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    import yaml

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def _raw_execution_mode(path: Path) -> str | None:
    execution = dict(_load_raw_config(path).get("execution", {}) or {})
    value = execution.get("mode")
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _operational_ambiguity_exists(resolved_config_path: Path) -> bool:
    project_root = _project_root_from_config_path(resolved_config_path)
    selected_path = resolved_config_path.resolve()
    legacy_path = (project_root / LEGACY_CONFIG_PATH).resolve()
    if not selected_path.exists() or not legacy_path.exists() or selected_path == legacy_path:
        return False
    selected_mode = _raw_execution_mode(selected_path)
    legacy_mode = _raw_execution_mode(legacy_path)
    return bool(selected_mode and legacy_mode and selected_mode != legacy_mode)


def _ensure_no_operational_ambiguity(resolved_config_path: Path) -> None:
    if _operational_ambiguity_exists(resolved_config_path):
        project_root = _project_root_from_config_path(resolved_config_path)
        selected_path = resolved_config_path.resolve()
        legacy_path = (project_root / LEGACY_CONFIG_PATH).resolve()
        raise ValueError(
            "Ambiguidade operacional detectada entre config selecionada e config raiz: "
            f"{selected_path} ({_raw_execution_mode(selected_path)}) != "
            f"{legacy_path} ({_raw_execution_mode(legacy_path)})."
        )


def _operational_config_allowed(resolved_config_path: Path) -> bool:
    path = resolved_config_path.resolve()
    return path.exists() and (path.parent.name == "config")


def bootstrap_runtime_context(config_path: str | Path | None = None) -> RuntimeContext:
    resolved_config_path = _canonical_runtime_config_path(config_path)
    config = load_config(str(resolved_config_path))
    config["__config_path"] = str(resolved_config_path.resolve())
    config["__boot_timestamp"] = utc_now()
    config["__run_id"] = runtime_run_id(config)

    feature_flags = bootstrap_feature_flags(resolved_config_path)
    config["__feature_flags"] = dict(feature_flags or {})

    preflight = perform_preflight(
        config,
        resolved_config_path=resolved_config_path,
        config_is_canonical=_operational_config_allowed(resolved_config_path),
        ambiguity_detected=_operational_ambiguity_exists(resolved_config_path),
    )
    manifest = build_runtime_manifest(
        config,
        resolved_config_path=resolved_config_path,
        feature_flags=feature_flags,
        preflight=preflight,
    )
    config["__operational_manifest"] = dict(manifest)

    db_path = str(config["storage"]["db_path"])
    database = SQLiteDatabase(db_path)
    ensure_runtime_audit_tables(database)
    persist_runtime_manifest(config, manifest, database=database)

    try:
        _ensure_no_operational_ambiguity(resolved_config_path)
        assert_preflight_ok(preflight)
    except Exception:
        try:
            record_runtime_event(
                config,
                database,
                event="preflight_failed",
                level="ERROR",
                details={
                    "errors": preflight.get("errors", []),
                    "warnings": preflight.get("warnings", []),
                    "run_id": config.get("__run_id", ""),
                },
            )
        except Exception:
            pass
        raise

    record_runtime_event(
        config,
        database,
        event="runtime_bootstrap_ok",
        level="INFO",
        details={
            "config_path": str(resolved_config_path.resolve()),
            "run_id": config.get("__run_id", ""),
        },
    )

    store = StateStore(db_path, database=database)
    runtime = dict(config.get("runtime", {}) or {})
    store.ensure_operational_identity(
        db_role="live" if str(config.get("execution", {}).get("mode", "")).lower() == "live" else "paper",
        profile_id=str(runtime.get("experiment_profile") or runtime.get("environment") or resolved_config_path.stem),
        symbol=str(config.get("market", {}).get("symbol", "")).replace("/", "").upper(),
    )
    store.set_flag("runtime_run_id", str(config.get("__run_id", "") or ""))
    position_manager = PositionManager(store)
    portfolio = Portfolio(store, position_manager=position_manager)
    exchange = ExchangeAdapter(config)
    return RuntimeContext(
        config=config,
        database=database,
        store=store,
        position_manager=position_manager,
        portfolio=portfolio,
        order_projections=store.order_projections,
        order_events=store.order_events,
        snapshots=store.snapshots,
        bot_events=store.bot_events,
        dispatch_locks=store.dispatch_locks,
        reconciliation_audit=store.reconciliation_audit,
        exchange=exchange,
        feature_flags=feature_flags,
    )


def bootstrap_runtime_services(config_path: str | Path | None = None) -> RuntimeServices:
    resolved_config_path = _canonical_runtime_config_path(config_path)
    context = bootstrap_runtime_context(resolved_config_path)
    logger = BotLogger(context.config)
    logger.info(
        "runtime_bootstrap_manifest",
        mode=context.config.get("__operational_manifest", {}).get("mode", ""),
        config_path=context.config.get("__operational_manifest", {}).get("config_path", ""),
        db_path=context.config.get("__operational_manifest", {}).get("db_path", ""),
        build_id=context.config.get("__operational_manifest", {}).get("build_id", ""),
        run_id=context.config.get("__operational_manifest", {}).get("run_id", ""),
        preflight_status=context.config.get("__operational_manifest", {}).get("preflight_status", ""),
    )
    return RuntimeServices(
        context=context,
        logger=logger,
        config_path=str(resolved_config_path),
    )


def run_startup_reconcile(
    context: RuntimeContext,
    logger: Any,
    *,
    build_id: str,
    recover_dispatch_locks_fn: Callable[[dict[str, Any], StateStore, ExchangeAdapter], None],
    reconcile_live_exchange_state_fn: Callable[..., Any],
) -> None:
    cfg = context.config
    store = context.store
    exchange = context.exchange
    try:
        recover_dispatch_locks_fn(cfg, store, exchange)
        record_runtime_event(cfg, context.database, event="recovery_event", level="INFO", details={"build_id": build_id})
        reconcile_live_exchange_state_fn(cfg, store, exchange, last_price=exchange.get_last_price())
        store.add_event("INFO", "live_startup_reconciled", {"build_id": build_id})
        record_runtime_event(cfg, context.database, event="startup_reconcile_ok", level="INFO", details={"build_id": build_id})
        logger.info("live_startup_reconciled", build_id=build_id)
    except Exception as exc:
        store.add_event("ERROR", "live_startup_reconcile_failed", {"error": str(exc)})
        record_runtime_event(
            cfg,
            context.database,
            event="reconcile_mismatch",
            level="ERROR",
            details={"error": str(exc), "build_id": build_id},
        )
        logger.error("live_startup_reconcile_failed", error=str(exc))
