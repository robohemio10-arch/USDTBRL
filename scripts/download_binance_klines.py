
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import requests

BASE_URL = "https://api.binance.com"
KLINES_PATH = "/api/v3/klines"
MAX_LIMIT = 1000
REQUEST_TIMEOUT = 30

INTERVAL_MS = {
    "1s": 1_000,
    "1m": 60_000,
    "3m": 3 * 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "30m": 30 * 60_000,
    "1h": 60 * 60_000,
    "2h": 2 * 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "6h": 6 * 60 * 60_000,
    "8h": 8 * 60 * 60_000,
    "12h": 12 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
    "3d": 3 * 24 * 60 * 60_000,
    "1w": 7 * 24 * 60 * 60_000,
    "1M": 30 * 24 * 60 * 60_000,
}

CSV_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_asset_volume",
    "number_of_trades",
    "taker_buy_base_asset_volume",
    "taker_buy_quote_asset_volume",
]

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download historical Binance spot klines and save them to CSV."
    )
    parser.add_argument("--symbol", default="USDTBRL", help="Binance symbol, e.g. USDTBRL")
    parser.add_argument("--interval", default="1m", choices=sorted(INTERVAL_MS), help="Kline interval")
    parser.add_argument("--years", type=float, default=3.0, help="How many years to go back from now")
    parser.add_argument("--output", default="usdtbrl_1m_3y.csv", help="Output CSV path")
    parser.add_argument("--sleep-seconds", type=float, default=0.05, help="Delay between requests")
    parser.add_argument("--retries", type=int, default=5, help="Retries per request")
    return parser.parse_args()

def utc_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)

def fmt_ts(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()

def request_klines(session: requests.Session, *, symbol: str, interval: str, start_time: int, end_time: int, limit: int, retries: int) -> list[list]:
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_time,
        "endTime": end_time,
        "limit": limit,
    }
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = session.get(f"{BASE_URL}{KLINES_PATH}", params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                raise RuntimeError(f"Unexpected response payload: {data!r}")
            return data
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt == retries:
                break
            time.sleep(min(2 ** attempt, 10))
    raise RuntimeError(f"Failed request after {retries} retries: {last_error}")

def iter_klines(symbol: str, interval: str, years: float, sleep_seconds: float, retries: int) -> Iterable[list]:
    interval_ms = INTERVAL_MS[interval]
    end_dt = datetime.now(tz=timezone.utc)
    start_dt = end_dt - timedelta(days=365.25 * years)
    start_time = utc_ms(start_dt)
    end_time = utc_ms(end_dt)

    total_bars_est = math.ceil((end_time - start_time) / interval_ms)
    print(
        f"Downloading {symbol} {interval} from {start_dt.isoformat()} to {end_dt.isoformat()} "
        f"(~{total_bars_est:,} candles)...",
        file=sys.stderr,
    )

    session = requests.Session()
    fetched = 0
    current_start = start_time

    while current_start < end_time:
        batch = request_klines(
            session,
            symbol=symbol,
            interval=interval,
            start_time=current_start,
            end_time=end_time,
            limit=MAX_LIMIT,
            retries=retries,
        )
        if not batch:
            break

        for row in batch:
            yield row

        fetched += len(batch)
        last_open_time = int(batch[-1][0])
        current_start = last_open_time + interval_ms

        print(
            f"Fetched {fetched:,} candles through {fmt_ts(last_open_time)}",
            file=sys.stderr,
        )

        if len(batch) < MAX_LIMIT:
            break

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

def write_csv(rows: Iterable[list], output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    seen_open_times: set[int] = set()

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)

        for row in rows:
            open_time = int(row[0])
            if open_time in seen_open_times:
                continue
            seen_open_times.add(open_time)

            writer.writerow(
                [
                    fmt_ts(open_time),
                    row[1],
                    row[2],
                    row[3],
                    row[4],
                    row[5],
                    fmt_ts(int(row[6])),
                    row[7],
                    row[8],
                    row[9],
                    row[10],
                ]
            )
            count += 1

    return count

def main() -> int:
    args = parse_args()
    output_path = Path(args.output).expanduser().resolve()
    rows = iter_klines(
        symbol=args.symbol.upper(),
        interval=args.interval,
        years=args.years,
        sleep_seconds=args.sleep_seconds,
        retries=args.retries,
    )
    count = write_csv(rows, output_path)
    print(f"Saved {count:,} candles to {output_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
