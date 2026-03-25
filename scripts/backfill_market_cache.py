from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from smartcrypto.config import load_config  # noqa: E402


def cache_symbol_token(symbol: str) -> str:
    return str(symbol or "USDTBRL").replace("/", "").replace("-", "").upper()


def dashboard_cache_dir(cfg: dict[str, Any]) -> Path:
    raw = str(
        cfg.get("dashboard", {}).get("cache_dir", "data/dashboard_cache") or "data/dashboard_cache"
    )
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def market_cache_file(cfg: dict[str, Any], interval: str) -> Path:
    symbol = cache_symbol_token(str(cfg.get("market", {}).get("symbol", "USDT/BRL")))
    return dashboard_cache_dir(cfg) / f"market_{symbol}_{interval}.json"


def fetch_public_ohlcv(cfg: dict[str, Any], interval: str, days: int = 30) -> pd.DataFrame:
    base_url = str(cfg.get("exchange", {}).get("base_url", "https://api.binance.com")).rstrip("/")
    symbol = cache_symbol_token(str(cfg.get("market", {}).get("symbol", "USDT/BRL")))
    end_ts = pd.Timestamp.utcnow()
    start_ts = end_ts - pd.Timedelta(days=int(days))
    rows: list[dict[str, Any]] = []
    start_ms = int(start_ts.timestamp() * 1000)
    end_ms = int(end_ts.timestamp() * 1000)
    session = requests.Session()
    while start_ms < end_ms:
        resp = session.get(
            f"{base_url}/api/v3/klines",
            params={
                "symbol": symbol,
                "interval": interval,
                "limit": 1000,
                "startTime": start_ms,
                "endTime": end_ms,
            },
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
        if not payload:
            break
        last_open = None
        for row in payload:
            last_open = int(row[0])
            rows.append(
                {
                    "ts": pd.to_datetime(int(row[0]), unit="ms", utc=True).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                }
            )
        if last_open is None:
            break
        next_start = last_open + 1
        if next_start <= start_ms:
            break
        start_ms = next_start
        if len(payload) < 1000:
            break
    return pd.DataFrame(rows)


def write_cache(cfg: dict[str, Any], interval: str, df: pd.DataFrame) -> Path:
    path = market_cache_file(cfg, interval)
    payload = {
        "saved_at": pd.Timestamp.utcnow().isoformat(),
        "symbol": str(cfg.get("market", {}).get("symbol", "")),
        "interval": interval,
        "rows": df.to_dict(orient="records"),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/config.yml")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    cfg = load_config(str(Path(args.config)))
    start = pd.Timestamp.utcnow() - pd.Timedelta(days=int(args.days))
    end = pd.Timestamp.utcnow()
    print(f"Baixando candles de {start} até {end}")

    written = []
    for interval in ["1m", "5m", "15m", "1h", "12h", "1d"]:
        df = fetch_public_ohlcv(cfg, interval, days=args.days)
        path = write_cache(cfg, interval, df)
        written.append(path)
        print(f"[ok] {interval}: {len(df)} candles -> {path}")

    print(f"Total de arquivos escritos: {len(written)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
