"""Загрузка OHLCV: Binance public API (без ключей). Приведён к эталону Colab.

ВАЖНО: используем data-api.binance.vision как основной endpoint, потому что
fapi.binance.com блокируется (HTTP 451) на серверах US/EU (Railway, AWS, Colab).
"""
from __future__ import annotations

import time
from typing import Optional

import pandas as pd
import requests

# ─── Endpoints ─────────────────────────────────────────────────────
# Зеркало Binance — не блокируется, работает из любой точки
BINANCE_MIRROR = "https://data-api.binance.vision/api/v3/klines"
# Основной futures API — блокируется на серверах US/EU
BINANCE_FAPI = "https://fapi.binance.com/fapi/v1/klines"


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

    Всегда идёт через зеркало data-api.binance.vision — оно не блокируется.
    Параметр futures оставлен для совместимости, но не влияет на URL.
    """
    params = {
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": min(limit, 1500),
    }
    if start_time:
        params["startTime"] = int(start_time)
    if end_time:
        params["endTime"] = int(end_time)

    # Сначала пробуем зеркало, потом fapi как fallback
    urls = [BINANCE_MIRROR, BINANCE_FAPI]

    for url in urls:
        for attempt in range(2):
            try:
                r = requests.get(url, params=params, timeout=20)
                if r.status_code == 429:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                if r.status_code == 451:
                    # Геоблок — пробуем следующий URL
                    break
                if r.status_code != 200:
                    print(f"⚠️ {symbol} {interval}: HTTP {r.status_code}")
                    break
                raw = r.json()
                if not raw or not isinstance(raw, list):
                    break
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
                        "taker_buy_base "",
                        "taker_buy_volumequote",
                        "ignore",
                    ],
                )
                df["open"]_time"] = pd.to_datetime(df["]
open_time"], unit="ms", utc=True)
                           for col in ("open", "high", "low", "close", "volume"):
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
                return df[["open_time", "open", "high", "low", "close", except Exception as e:
                print(f"⚠️ {symbol} {url.split('/')[2]}: {e}")
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
