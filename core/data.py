"""Загрузка OHLCV: Binance public API (без ключей)."""
from __future__ import annotations

import time
from typing import Optional

import pandas as pd
import requests

# Публичный endpoint (не требует API-ключа)
BINANCE_FAPI_KLINES = "https://fapi.binance.com/fapi/v1/klines"
BINANCE_DATA_API = "https://data-api.binance.vision/api/v3/klines"  # spot fallback


def fetch_klines(
    symbol: str,
    interval: str = "15m",
    limit: int = 500,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    futures: bool = True,
) -> Optional[pd.DataFrame]:
    """
    Загрузка свечей.
    symbol: BTCUSDT
    interval: 15m, 1h, 1d, ...
    """
    url = BINANCE_FAPI_KLINES if futures else BINANCE_DATA_API
    params = {"symbol": symbol.upper(), "interval": interval, "limit": min(limit, 1500)}
    if start_time:
        params["startTime"] = int(start_time)
    if end_time:
        params["endTime"] = int(end_time)

    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=20)
            if r.status_code == 429:
                time.sleep(1.5 * (attempt + 1))
                continue
            if r.status_code != 200:
                print(f"⚠️ {symbol} {interval}: HTTP {r.status_code}")
                return None
            raw = r.json()
            if not raw or not isinstance(raw, list):
                return None
            df = pd.DataFrame(
                raw,
                columns=[
                    "open_time",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "close_time",
                    "quote_volume",
                    "trades",
                    "taker_buy_base",
                    "taker_buy_quote",
                    "ignore",
                ],
            )
            df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
            for col in ("open", "high", "low", "close", "volume"):
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
            return df[["open_time", "open", "high", "low", "close", "volume"]]
        except Exception as e:
            print(f"⚠️ {symbol}: {e}")
            time.sleep(0.5 * (attempt + 1))
    return None


def fetch_klines_paginated(
    symbol: str,
    interval: str = "15m",
    total_bars: int = 2000,
    futures: bool = True,
) -> Optional[pd.DataFrame]:
    """Пагинация назад по startTime (до total_bars свечей)."""
    frames = []
    end_time = None
    fetched = 0
    while fetched < total_bars:
        limit = min(1000, total_bars - fetched)
        df = fetch_klines(symbol, interval, limit=limit, end_time=end_time, futures=futures)
        if df is None or df.empty:
            break
        frames.append(df)
        fetched += len(df)
        end_time = int(df["open_time"].iloc[0].timestamp() * 1000) - 1
        if len(df) < limit:
            break
        time.sleep(0.15)
    if not frames:
        return None
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(subset=["open_time"]).sort_values("open_time").reset_index(drop=True)
    return out.tail(total_bars).reset_index(drop=True)
