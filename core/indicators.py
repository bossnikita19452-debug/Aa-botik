"""Индикаторы для Golden Scanner: RSI, EMA, BB, ATR, ADX. Приведены к эталону Colab."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length).mean()


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    """
    RSI с SMA-сглаживанием (как в Colab-бэктесте).
    """
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(length).mean()
    loss = (-delta.clip(upper=0)).rolling(length).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    """
    ATR с SMA-сглаживанием (как в Colab-бэктесте).
    """
    tr = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(length).mean()


def bollinger(
    close: pd.Series, period: int = 20, std_mult: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    up = mid + std_mult * std
    low = mid - std_mult * std
    return mid, low, up


def adx(
    high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14
) -> pd.Series:
    up = high.diff()
    down = -low.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr_ = tr.ewm(alpha=1 / length, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=high.index).ewm(
        alpha=1 / length, adjust=False
    ).mean() / (atr_ + 1e-12)
    minus_di = 100 * pd.Series(minus_dm, index=high.index).ewm(
        alpha=1 / length, adjust=False
    ).mean() / (atr_ + 1e-12)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-12)
    return dx.ewm(alpha=1 / length, adjust=False).mean()


def add_common_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Базовый набор для 15m сканеров."""
    df = df.copy()
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"]
    df["ema20"] = ema(c, 20)
    df["ema50"] = ema(c, 50)
    df["ema200"] = ema(c, 200)
    df["rsi14"] = rsi(c, 14)
    df["atr14"] = atr(h, l, c, 14)
    df["atr_sma30"] = sma(df["atr14"], 30)
    df["vol_sma20"] = sma(v, 20)
    mid, blow, bup = bollinger(c, 20, 2.0)
    df["bb_mid"] = mid
    df["bb_low"] = blow
    df["bb_up"] = bup
    df["high_40"] = h.rolling(40).max().shift(1)
    df["low_40"] = l.rolling(40).min().shift(1)
    return df
