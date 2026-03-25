from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Any, cast
from urllib.parse import urlencode

import pandas as pd
import requests

from smartcrypto.common.env import load_dotenv_file


@dataclass
class LimitAttemptConfig:
    wait_seconds: int
    attempts: int


class ExchangeAdapter:
    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        self._load_dotenv()
        exchange_cfg = cfg.get("exchange", {}) or {}
        self.base_url = str(exchange_cfg.get("base_url", "https://api.binance.com")).rstrip("/")
        self.api_key = self._resolve_credential(
            explicit_value=str(exchange_cfg.get("api_key", "") or ""),
            env_name=str(exchange_cfg.get("api_key_env", "BINANCE_API_KEY") or "BINANCE_API_KEY"),
        )
        self.api_secret = self._resolve_credential(
            explicit_value=str(exchange_cfg.get("api_secret", "") or ""),
            env_name=str(
                exchange_cfg.get("api_secret_env", "BINANCE_API_SECRET") or "BINANCE_API_SECRET"
            ),
        )
        self.timeout = float(exchange_cfg.get("timeout_seconds", 20) or 20)
        self.recv_window = int(exchange_cfg.get("recv_window", 5000) or 5000)
        self.request_retries = max(1, int(exchange_cfg.get("request_retries", 3) or 3))
        self.request_backoff_seconds = max(
            0.0, float(exchange_cfg.get("request_backoff_seconds", 1.0) or 1.0)
        )
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({"X-MBX-APIKEY": self.api_key})
        self.symbol = self.normalize_symbol(str(cfg["market"]["symbol"]))
        self._symbol_info_cache: dict[str, Any] | None = None
        self._validate_basic_config()

    @staticmethod
    def _load_dotenv() -> None:
        load_dotenv_file()

    @staticmethod
    def _resolve_credential(*, explicit_value: str, env_name: str) -> str:
        if explicit_value:
            return explicit_value
        return str(os.getenv(env_name, "") or "")

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        return symbol.replace("/", "").replace("-", "").replace("_", "").upper()

    def _validate_basic_config(self) -> None:
        if str(self.cfg.get("execution", {}).get("mode", "dry_run")).lower() == "live":
            if not self.api_key or not self.api_secret:
                raise ValueError(
                    "Modo live exige BINANCE_API_KEY e BINANCE_API_SECRET válidas no .env."
                )

    def _request_json(
        self, *, method: str, path: str, params: dict[str, Any] | None, signed: bool
    ) -> Any:
        url = f"{self.base_url}{path}"
        for attempt in range(1, self.request_retries + 1):
            try:
                payload = dict(params or {})
                if signed:
                    payload["timestamp"] = int(time.time() * 1000)
                    payload["recvWindow"] = self.recv_window
                    query = urlencode(payload, doseq=True)
                    signature = hmac.new(
                        self.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256
                    ).hexdigest()
                    payload["signature"] = signature
                resp = self.session.request(
                    method=method.upper(), url=url, params=payload, timeout=self.timeout
                )
                retry_http = resp.status_code in {418, 429, 500, 502, 503, 504}
                try:
                    data = resp.json()
                except Exception:
                    data = {"raw": resp.text}
                if resp.status_code >= 400:
                    if retry_http and attempt < self.request_retries:
                        time.sleep(self.request_backoff_seconds * attempt)
                        continue
                    raise RuntimeError(f"Binance HTTP {resp.status_code}: {data}")
                if (
                    isinstance(data, dict)
                    and data.get("code", 0) not in (0, None)
                    and "msg" in data
                ):
                    raise RuntimeError(f"Binance API error: {data}")
                return data
            except requests.RequestException:
                if attempt >= self.request_retries:
                    raise
                time.sleep(self.request_backoff_seconds * attempt)
        raise RuntimeError("Falha de request à Binance.")

    def _public_request(self, method: str, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._request_json(method=method, path=path, params=params, signed=False)

    def _signed_request(self, method: str, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self.api_key or not self.api_secret:
            raise ValueError("API key/secret ausentes para requisição assinada.")
        return self._request_json(method=method, path=path, params=params, signed=True)

    def get_symbol_info(self) -> dict[str, Any]:
        if self._symbol_info_cache is None:
            payload = self._public_request("GET", "/api/v3/exchangeInfo", {"symbol": self.symbol})
            symbols = payload.get("symbols") or []
            if not symbols:
                raise RuntimeError(f"Símbolo não encontrado na Binance Spot: {self.symbol}")
            self._symbol_info_cache = symbols[0]
        return self._symbol_info_cache

    def get_filters(self) -> dict[str, dict[str, Any]]:
        return {row["filterType"]: row for row in self.get_symbol_info().get("filters", [])}

    def base_asset_symbol(self) -> str:
        return str(self.get_symbol_info().get("baseAsset") or "USDT")

    def quote_asset_symbol(self) -> str:
        return str(self.get_symbol_info().get("quoteAsset") or "BRL")

    def get_last_price(self) -> float:
        payload = self._public_request("GET", "/api/v3/ticker/price", {"symbol": self.symbol})
        return float(payload["price"])

    def fetch_ohlcv(self, timeframe: str, limit: int) -> pd.DataFrame:
        payload = self._public_request(
            "GET",
            "/api/v3/klines",
            {"symbol": self.symbol, "interval": timeframe, "limit": int(limit)},
        )
        rows = []
        for row in payload:
            rows.append(
                {
                    "open_time": pd.to_datetime(int(row[0]), unit="ms", utc=True),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                    "close_time": pd.to_datetime(int(row[6]), unit="ms", utc=True),
                }
            )
        return pd.DataFrame(rows)

    @staticmethod
    def _to_decimal(value: float | str) -> Decimal:
        return Decimal(str(value))

    def _round_down(self, value: float, step: float) -> float:
        if step <= 0:
            return float(value)
        decimal_value = self._to_decimal(value)
        decimal_step = self._to_decimal(step)
        quantized = (decimal_value / decimal_step).to_integral_value(
            rounding=ROUND_DOWN
        ) * decimal_step
        return float(quantized)

    @staticmethod
    def _format_decimal(value: float) -> str:
        text = format(Decimal(str(value)).normalize(), "f")
        return text.rstrip("0").rstrip(".") if "." in text else text

    def _price_step(self) -> float:
        return float((self.get_filters().get("PRICE_FILTER") or {}).get("tickSize") or 0.0001)

    def _qty_step(self, *, for_market: bool = False) -> float:
        filters = self.get_filters()
        market_lot = filters.get("MARKET_LOT_SIZE") if for_market else None
        lot = market_lot or filters.get("LOT_SIZE") or {}
        return float(lot.get("stepSize") or 0.000001)

    def _min_qty(self, *, for_market: bool = False) -> float:
        filters = self.get_filters()
        market_lot = filters.get("MARKET_LOT_SIZE") if for_market else None
        lot = market_lot or filters.get("LOT_SIZE") or {}
        return float(lot.get("minQty") or 0.0)

    def _min_notional(self) -> float:
        filters = self.get_filters()
        notional = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL") or {}
        return float(notional.get("minNotional") or 0.0)

    def _quote_precision_step(self) -> float:
        return self._price_step()

    def _prepare_quote_order_qty(self, quote_brl: float) -> str:
        rounded = self._round_down(quote_brl, self._quote_precision_step())
        minimum = self._min_notional()
        if rounded <= 0 or (minimum > 0 and rounded < minimum):
            raise RuntimeError(f"Valor em BRL abaixo do mínimo do símbolo: {quote_brl} < {minimum}")
        return self._format_decimal(rounded)

    def _prepare_price(self, price_brl: float) -> str:
        rounded = self._round_down(price_brl, self._price_step())
        if rounded <= 0:
            raise RuntimeError(f"Preço inválido para a Binance: {price_brl}")
        return self._format_decimal(rounded)

    def _prepare_quantity(self, qty_usdt: float, *, for_market: bool = False) -> str:
        rounded = self._round_down(qty_usdt, self._qty_step(for_market=for_market))
        min_qty = self._min_qty(for_market=for_market)
        if rounded <= 0 or rounded < min_qty:
            raise RuntimeError(f"Quantidade insuficiente para a Binance: {qty_usdt}")
        return self._format_decimal(rounded)

    def _check_min_notional(self, brl_value: float) -> None:
        minimum = self._min_notional()
        if minimum > 0 and float(brl_value) < minimum:
            raise RuntimeError(f"Notional abaixo do mínimo da Binance: {brl_value} < {minimum}")

    def _validate_limit_notional_after_rounding(
        self, *, price: str | float, quantity: str | float
    ) -> None:
        minimum = self._to_decimal(self._min_notional())
        if minimum <= 0:
            return
        final_notional = self._to_decimal(price) * self._to_decimal(quantity)
        if final_notional < minimum:
            raise RuntimeError(
                "Filter failure: NOTIONAL "
                f"(final_notional={self._format_decimal(float(final_notional))}, "
                f"min_notional={self._format_decimal(float(minimum))})"
            )

    def _prepare_limit_order_params(
        self, *, price_brl: float, qty_usdt: float, for_market: bool = False
    ) -> tuple[str, str]:
        prepared_price = self._prepare_price(price_brl)
        prepared_quantity = self._prepare_quantity(qty_usdt, for_market=for_market)
        self._validate_limit_notional_after_rounding(
            price=prepared_price, quantity=prepared_quantity
        )
        return prepared_price, prepared_quantity

    def _new_order(
        self,
        *,
        side: str,
        order_type: str,
        quantity: str | None = None,
        quote_order_qty: str | None = None,
        price: str | None = None,
        time_in_force: str | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "symbol": self.symbol,
            "side": side.upper(),
            "type": order_type.upper(),
            "newOrderRespType": "FULL",
        }
        if quantity is not None:
            params["quantity"] = quantity
        if quote_order_qty is not None:
            params["quoteOrderQty"] = quote_order_qty
        if client_order_id:
            params["newClientOrderId"] = client_order_id
        if order_type.lower() == "limit":
            if price is None:
                raise ValueError("Ordem LIMIT exige preço.")
            params["price"] = price
            params["timeInForce"] = time_in_force or str(
                self.cfg.get("execution", {}).get("limit_time_in_force", "GTC")
            )
        return cast(dict[str, Any], self._signed_request("POST", "/api/v3/order", params))

    def _submit_order_with_recovery(self, **kwargs: Any) -> dict[str, Any]:
        client_order_id = str(kwargs.get("client_order_id") or "")
        try:
            return self._new_order(**kwargs)
        except requests.RequestException:
            if not client_order_id:
                raise
            time.sleep(min(1.0, max(0.2, self.request_backoff_seconds)))
            recovered = self.get_order(client_order_id=client_order_id, raise_if_missing=False)
            if recovered:
                return recovered
            raise

    def get_order(
        self,
        order_id: int | None = None,
        client_order_id: str | None = None,
        *,
        raise_if_missing: bool = True,
    ) -> dict[str, Any] | None:
        params: dict[str, Any] = {"symbol": self.symbol}
        if order_id is not None:
            params["orderId"] = int(order_id)
        elif client_order_id:
            params["origClientOrderId"] = str(client_order_id)
        else:
            raise ValueError("get_order exige order_id ou client_order_id.")
        try:
            return cast(dict[str, Any], self._signed_request("GET", "/api/v3/order", params))
        except RuntimeError:
            if raise_if_missing:
                raise
            return None

    def cancel_order(self, order_id: int | str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._signed_request(
                "DELETE", "/api/v3/order", {"symbol": self.symbol, "orderId": int(order_id)}
            ),
        )

    def _normalize_order_snapshot(self, row: dict[str, Any] | None) -> dict[str, Any]:
        if not row:
            return {
                "order_id": None,
                "client_order_id": "",
                "side": "",
                "order_type": "",
                "time_in_force": "",
                "status": "",
                "price_brl": 0.0,
                "qty_usdt": 0.0,
                "executed_qty_usdt": 0.0,
                "quote_brl": 0.0,
                "updated_at": "",
            }
        ts_value = (
            row.get("updateTime")
            or row.get("transactTime")
            or row.get("workingTime")
            or row.get("time")
            or 0
        )
        updated_at = ""
        try:
            if ts_value:
                updated_at = pd.to_datetime(int(ts_value), unit="ms", utc=True).isoformat()
        except Exception:
            updated_at = str(row.get("updated_at") or "")
        return {
            "order_id": int(row.get("orderId") or row.get("order_id") or 0) or None,
            "client_order_id": str(
                row.get("clientOrderId")
                or row.get("client_order_id")
                or row.get("origClientOrderId")
                or ""
            ),
            "side": str(row.get("side", "")).lower(),
            "order_type": str(row.get("type") or row.get("order_type") or "").lower(),
            "time_in_force": str(row.get("timeInForce") or row.get("time_in_force") or "").upper(),
            "status": str(row.get("status", "")).upper(),
            "price_brl": float(row.get("price") or row.get("price_brl") or 0.0),
            "qty_usdt": float(
                row.get("origQty") or row.get("qty_usdt") or row.get("executedQty") or 0.0
            ),
            "executed_qty_usdt": float(
                row.get("executedQty") or row.get("executed_qty_usdt") or 0.0
            ),
            "quote_brl": float(row.get("cummulativeQuoteQty") or row.get("quote_brl") or 0.0),
            "updated_at": updated_at,
        }

    def get_open_orders(self) -> list[dict[str, Any]]:
        orders = self._signed_request("GET", "/api/v3/openOrders", {"symbol": self.symbol})
        parsed = []
        for row in orders:
            item = self._normalize_order_snapshot(row)
            item["status"] = str(item.get("status", "")).lower()
            item["updated_at"] = pd.to_datetime(item.get("updated_at"), errors="coerce", utc=True)
            parsed.append(item)
        return parsed

    def get_account_balances(self) -> dict[str, dict[str, float]]:
        payload = self._signed_request("GET", "/api/v3/account", {})
        balances = {}
        for row in payload.get("balances", []) or []:
            asset = str(row.get("asset") or "")
            balances[asset] = {
                "free": float(row.get("free") or 0.0),
                "locked": float(row.get("locked") or 0.0),
                "total": float(row.get("free") or 0.0) + float(row.get("locked") or 0.0),
            }
        return balances

    def _combine_results(self, current: dict[str, Any], fill: dict[str, Any]) -> dict[str, Any]:
        total_qty = float(current.get("qty_usdt", 0.0)) + float(fill.get("qty_usdt", 0.0))
        total_quote = float(current.get("quote_brl", 0.0)) + float(fill.get("quote_brl", 0.0))
        avg_price = total_quote / total_qty if total_qty > 0 else 0.0
        return {"qty_usdt": total_qty, "quote_brl": total_quote, "price_brl": avg_price}

    def _extract_fill_result(self, order: dict[str, Any]) -> dict[str, Any]:
        qty = float(order.get("executedQty") or order.get("executed_qty_usdt") or 0.0)
        quote = float(order.get("cummulativeQuoteQty") or order.get("quote_brl") or 0.0)
        price = (
            quote / qty if qty > 0 else float(order.get("price") or order.get("price_brl") or 0.0)
        )
        return {"qty_usdt": qty, "quote_brl": quote, "price_brl": price}

    def _limit_attempt_config(self) -> LimitAttemptConfig:
        execution_cfg = self.cfg.get("execution", {}) or {}
        return LimitAttemptConfig(
            wait_seconds=max(1, int(execution_cfg.get("reprice_wait_seconds", 10) or 10)),
            attempts=max(1, int(execution_cfg.get("reprice_attempts", 6) or 6)),
        )

    def _wait_for_limit_result(self, order_id: int, timeout_seconds: int) -> dict[str, Any]:
        deadline = time.time() + max(1, int(timeout_seconds))
        latest = self.get_order(order_id=order_id) or {}
        while time.time() < deadline:
            status = str(latest.get("status", "")).upper()
            if status in {"FILLED", "CANCELED", "EXPIRED", "REJECTED"}:
                return latest
            time.sleep(1.0)
            latest = self.get_order(order_id=order_id) or {}
        return latest

    def _run_limit_cycle(
        self, *, side: str, quantity: str, price: str, timeout_seconds: int, client_order_id: str
    ) -> dict[str, Any]:
        order = self._submit_order_with_recovery(
            side=side,
            order_type="limit",
            quantity=quantity,
            price=price,
            time_in_force=str(self.cfg.get("execution", {}).get("limit_time_in_force", "GTC")),
            client_order_id=client_order_id,
        )
        submitted = self._normalize_order_snapshot(order)
        order_id = int(order.get("orderId") or order.get("order_id") or 0)
        latest = self._wait_for_limit_result(order_id, timeout_seconds)
        if str(latest.get("status", "")).upper() not in {
            "FILLED",
            "CANCELED",
            "EXPIRED",
            "REJECTED",
        }:
            try:
                self.cancel_order(order_id)
            except Exception:
                pass
            latest = self.get_order(order_id=order_id) or {}
        return {
            "submitted_raw": order,
            "latest_raw": latest,
            "submitted": submitted,
            "latest": self._normalize_order_snapshot(latest),
        }

    def _execute_entry_limit(
        self,
        *,
        brl_value: float,
        initial_price_brl: float,
        fallback_market: bool,
        client_order_id_prefix: str,
    ) -> dict[str, Any]:
        cfg = self._limit_attempt_config()
        remaining_quote = float(brl_value)
        combined: dict[str, Any] = {"qty_usdt": 0.0, "quote_brl": 0.0, "price_brl": 0.0}
        attempt_price = float(initial_price_brl)
        attempts_report = []
        for attempt_no in range(1, cfg.attempts + 1):
            if remaining_quote <= 0.01:
                break
            self._check_min_notional(remaining_quote)
            price, quantity = self._prepare_limit_order_params(
                price_brl=attempt_price,
                qty_usdt=remaining_quote / max(attempt_price, 1e-9),
            )
            cycle = self._run_limit_cycle(
                side="BUY",
                quantity=quantity,
                price=price,
                timeout_seconds=cfg.wait_seconds,
                client_order_id=f"{client_order_id_prefix}-L{attempt_no}",
            )
            order = cycle["latest_raw"]
            fill = self._extract_fill_result(order)
            if fill["qty_usdt"] > 0:
                combined = self._combine_results(combined, fill)
                remaining_quote = max(0.0, brl_value - combined["quote_brl"])
            attempts_report.append(
                {
                    "attempt_no": attempt_no,
                    "submitted": cycle["submitted"],
                    "latest": cycle["latest"],
                    "remaining_quote_brl": remaining_quote,
                    "fallback_market": False,
                }
            )
            if str(order.get("status", "")).upper() == "FILLED":
                combined["execution_report"] = {
                    "requested_order_type": "limit",
                    "final_state": "filled",
                    "fallback_used": False,
                    "attempts": attempts_report,
                }
                return combined
            attempt_price = self.get_last_price()
        if combined["qty_usdt"] > 0 and not fallback_market:
            combined["execution_report"] = {
                "requested_order_type": "limit",
                "final_state": "partial",
                "fallback_used": False,
                "attempts": attempts_report,
            }
            return combined
        if not fallback_market:
            raise RuntimeError("Compra LIMIT não executada e fallback desativado.")
        quote_order_qty = self._prepare_quote_order_qty(remaining_quote)
        market_result = self._submit_order_with_recovery(
            side="BUY",
            order_type="market",
            quote_order_qty=quote_order_qty,
            client_order_id=f"{client_order_id_prefix}-M1",
        )
        market_fill = self._extract_fill_result(market_result)
        combined = self._combine_results(combined, market_fill)
        snapshot = self._normalize_order_snapshot(market_result)
        attempts_report.append(
            {
                "attempt_no": len(attempts_report) + 1,
                "submitted": snapshot,
                "latest": snapshot,
                "remaining_quote_brl": 0.0,
                "fallback_market": True,
            }
        )
        combined["execution_report"] = {
            "requested_order_type": "limit",
            "final_state": snapshot.get("status") or "FILLED",
            "fallback_used": True,
            "attempts": attempts_report,
        }
        return combined

    def _execute_exit_limit(
        self,
        *,
        qty_usdt: float,
        initial_price_brl: float,
        fallback_market: bool,
        client_order_id_prefix: str,
    ) -> dict[str, Any]:
        cfg = self._limit_attempt_config()
        remaining_qty = float(qty_usdt)
        combined: dict[str, Any] = {"qty_usdt": 0.0, "quote_brl": 0.0, "price_brl": 0.0}
        attempt_price = float(initial_price_brl)
        attempts_report = []
        for attempt_no in range(1, cfg.attempts + 1):
            if remaining_qty <= 0:
                break
            price, quantity = self._prepare_limit_order_params(
                price_brl=attempt_price,
                qty_usdt=remaining_qty,
            )
            cycle = self._run_limit_cycle(
                side="SELL",
                quantity=quantity,
                price=price,
                timeout_seconds=cfg.wait_seconds,
                client_order_id=f"{client_order_id_prefix}-L{attempt_no}",
            )
            order = cycle["latest_raw"]
            fill = self._extract_fill_result(order)
            if fill["qty_usdt"] > 0:
                combined = self._combine_results(combined, fill)
                remaining_qty = max(0.0, qty_usdt - combined["qty_usdt"])
            attempts_report.append(
                {
                    "attempt_no": attempt_no,
                    "submitted": cycle["submitted"],
                    "latest": cycle["latest"],
                    "remaining_qty_usdt": remaining_qty,
                    "fallback_market": False,
                }
            )
            if str(order.get("status", "")).upper() == "FILLED":
                combined["execution_report"] = {
                    "requested_order_type": "limit",
                    "final_state": "filled",
                    "fallback_used": False,
                    "attempts": attempts_report,
                }
                return combined
            attempt_price = self.get_last_price()
        if combined["qty_usdt"] > 0 and not fallback_market:
            combined["execution_report"] = {
                "requested_order_type": "limit",
                "final_state": "partial",
                "fallback_used": False,
                "attempts": attempts_report,
            }
            return combined
        if not fallback_market:
            raise RuntimeError("Venda LIMIT não executada e fallback desativado.")
        fallback_qty = self._prepare_quantity(remaining_qty, for_market=True)
        fallback_result = self._submit_order_with_recovery(
            side="SELL",
            order_type="market",
            quantity=fallback_qty,
            client_order_id=f"{client_order_id_prefix}-M1",
        )
        market_fill = self._extract_fill_result(fallback_result)
        combined = self._combine_results(combined, market_fill)
        snapshot = self._normalize_order_snapshot(fallback_result)
        attempts_report.append(
            {
                "attempt_no": len(attempts_report) + 1,
                "submitted": snapshot,
                "latest": snapshot,
                "remaining_qty_usdt": 0.0,
                "fallback_market": True,
            }
        )
        combined["execution_report"] = {
            "requested_order_type": "limit",
            "final_state": snapshot.get("status") or "FILLED",
            "fallback_used": True,
            "attempts": attempts_report,
        }
        return combined

    def execute_entry(
        self,
        *,
        brl_value: float,
        price_brl: float,
        order_type: str,
        fallback_market: bool,
        client_order_id_prefix: str,
    ) -> dict[str, Any]:
        self._check_min_notional(brl_value)
        target_price = float(price_brl or self.get_last_price())
        if order_type.lower() == "market":
            result = self._submit_order_with_recovery(
                side="BUY",
                order_type="market",
                quote_order_qty=self._prepare_quote_order_qty(brl_value),
                client_order_id=f"{client_order_id_prefix}-M1",
            )
            fill = self._extract_fill_result(result)
            snapshot = self._normalize_order_snapshot(result)
            fill["execution_report"] = {
                "requested_order_type": "market",
                "final_state": snapshot.get("status") or "FILLED",
                "fallback_used": False,
                "attempts": [
                    {
                        "attempt_no": 1,
                        "submitted": snapshot,
                        "latest": snapshot,
                        "remaining_quote_brl": 0.0,
                        "fallback_market": False,
                    }
                ],
            }
            return fill
        return self._execute_entry_limit(
            brl_value=float(brl_value),
            initial_price_brl=target_price,
            fallback_market=fallback_market,
            client_order_id_prefix=client_order_id_prefix,
        )

    def execute_exit(
        self,
        *,
        qty_usdt: float,
        price_brl: float | None,
        order_type: str,
        fallback_market: bool,
        client_order_id_prefix: str,
    ) -> dict[str, Any]:
        if order_type.lower() == "market":
            result = self._submit_order_with_recovery(
                side="SELL",
                order_type="market",
                quantity=self._prepare_quantity(qty_usdt, for_market=True),
                client_order_id=f"{client_order_id_prefix}-M1",
            )
            fill = self._extract_fill_result(result)
            snapshot = self._normalize_order_snapshot(result)
            fill["execution_report"] = {
                "requested_order_type": "market",
                "execution_policy": "direct_market_exit",
                "final_state": snapshot.get("status") or "FILLED",
                "fallback_used": False,
                "attempts": [
                    {
                        "attempt_no": 1,
                        "submitted": snapshot,
                        "latest": snapshot,
                        "remaining_qty_usdt": max(0.0, float(qty_usdt) - fill["qty_usdt"]),
                        "fallback_market": False,
                    }
                ],
            }
            return fill
        fill = self._execute_exit_limit(
            qty_usdt=float(qty_usdt),
            initial_price_brl=float(price_brl or self.get_last_price()),
            fallback_market=fallback_market,
            client_order_id_prefix=client_order_id_prefix,
        )
        report = dict(cast(dict[str, Any], fill.get("execution_report") or {}))
        report["execution_policy"] = "resting_limit_exit"
        fill["execution_report"] = report
        return fill
