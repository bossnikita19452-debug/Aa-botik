"""Определение фазы рынка BTC (1d): UPTREND / DOWNTREND / RANGE."""
from __future__ import annotations

from enum import Enum

import pandas as pd

from core.indicators import adx, ema


class MarketPhase(str, Enum):
    UPTREND = "UPTREND"
    DOWNTREND = "DOWNTREND"
    RANGE = "RANGE"


def detect_btc_phase(
    df_1d: pd.DataFrame,
    ema_fast: int = 50,
    ema_slow: int = 200,
    adx_period: int = 14,
    adx_min: float = 20.0,
) -> MarketPhase:
    """
    UPTREND: close > EMA50 и ADX > adx_min
    DOWNTREND: close < EMA50 и ADX > adx_min
    RANGE: всё остальное
    """
    if df_1d is None or len(df_1d) < max(ema_slow, adx_period) + 5:
        return MarketPhase.RANGE

    df = df_1d.copy()
    c = df["close"]
    df["ema50"] = ema(c, ema_fast)
    df["ema200"] = ema(c, ema_slow)
    df["adx"] = adx(df["high"], df["low"], c, adx_period)

    row = df.iloc[-1]
    close = float(row["close"])
    e50 = float(row["ema50"])
    adx_v = float(row["adx"]) if pd.notna(row["adx"]) else 0.0

    if close > e50 and adx_v > adx_min:
        return MarketPhase.UPTREND
    if close < e50 and adx_v > adx_min:
        return MarketPhase.DOWNTREND
    return MarketPhase.RANGE


def active_strategies(phase: MarketPhase) -> list[str]:
    """Какие сканеры активны в текущей фазе."""
    if phase == MarketPhase.UPTREND:
        return ["BRK_LONG"]
    if phase == MarketPhase.DOWNTREND:
        return ["BRK_SHORT"]
    return ["MR_LONG", "MR_SHORT"]
