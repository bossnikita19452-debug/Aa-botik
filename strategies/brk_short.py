"""BRK_SHORT — пробой вниз (фаза DOWNTREND). Зеркало BRK_LONG.

Фильтры:
- MAX_ENTRY_GAP = 1.0% — entry не дальше 1% от уровня ретеста.
- ATR_FILTER = 1.5× — не входим, если ATR(14) > 1.5 × SMA(ATR, 30).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


LOCK_BARS = 8
MAX_ENTRY_GAP = 0.01       # 1.0%
ATR_FILTER_MULT = 1.5      # ATR(14) > 1.5 × SMA(ATR,30) → пропускаем


@dataclass
class Signal:
    strategy: str
    side: str  # SHORT
    symbol: str
    entry: float
    stop: float
    take: float
    breakout_level: float
    atr: float
    reason: str = ""


def check_breakout_signal(df: pd.DataFrame, cfg: dict) -> Optional[dict]:
    """
    Условия пробоя вниз (на закрытой свече -2):
    1. EMA20 < EMA50
    2. close < Low(40).shift(1)
    3. volume > 2.5 * SMA(volume, 20)
    4. RSI 30..45

    Возвращает level = low_40, bar_index абсолютный.
    """
    if df is None or len(df) < 50:
        return None

    i = -2
    row = df.iloc[i]

    if pd.isna(row.get("ema20")) or pd.isna(row.get("low_40")):
        return None
    if not (row["ema20"] < row["ema50"]):
        return None
    if not (row["close"] < row["low_40"]):
        return None

    vol_sma = row.get("vol_sma20")
    if vol_sma is None or vol_sma <= 0:
        return None
    if row["volume"] < cfg.get("volume_mult", 2.5) * vol_sma:
        return None

    rsi = row.get("rsi14")
    if rsi is None or not (cfg.get("rsi_short_min", 30) <= rsi <= cfg.get("rsi_short_max", 45)):
        return None

    # ─── ФИЛЬТР ВОЛАТИЛЬНОСТИ ──────────────────────────────
    atr_val = row.get("atr14")
    atr_sma = row.get("atr_sma30")
    if atr_val is not None and atr_sma is not None:
        if np.isfinite(atr_val) and np.isfinite(atr_sma) and atr_sma > 0:
            if atr_val > ATR_FILTER_MULT * atr_sma:
                return None
    # ──────────────────────────────────────────────────────

    return {
        "level": float(row["low_40"]),
        "bar_index": len(df) - 2,
    }


def check_retest_entry(
    df: pd.DataFrame,
    breakout_level: float,
    breakout_bar: int,
    cfg: dict,
) -> Optional[Signal]:
    """
    Ретест в течение retest_bars свечей после пробоя вниз:
    high >= level * 0.999 и close < level → вход на open следующей.

    Фильтр MAX_ENTRY_GAP: для шорта |entry - level| / level > 1% — пропускаем.
    """
    retest_bars = cfg.get("retest_bars", 8)
    start = breakout_bar + 1
    end = min(breakout_bar + 1 + retest_bars, len(df) - 1)
    if start >= len(df) - 1:
        return None

    for j in range(start, end):
        row = df.iloc[j]
        level = breakout_level

        if row["high"] >= level * 0.999 and row["close"] < level:
            if j + 1 >= len(df):
                return None

            entry_row = df.iloc[j + 1]
            entry = float(entry_row["open"])

            if level > 0:
                gap = abs(entry - level) / level
                if gap > MAX_ENTRY_GAP:
                    return None

            atr = float(entry_row["atr14"]) if pd.notna(entry_row.get("atr14")) else entry * 0.01

            base_sl = level * (1 + 0.005)
            sl_dist = base_sl - entry
            min_sl = cfg.get("sl_atr_min", 0.3) * atr
            max_sl = cfg.get("sl_atr_max", 1.5) * atr
            sl_dist = max(min_sl, min(max_sl, sl_dist))
            if sl_dist <= 0:
                return None

            sl = entry + sl_dist
            tp = entry - cfg.get("rr", 1.5) * sl_dist

            return Signal(
                strategy="BRK_SHORT",
                side="SHORT",
                symbol="",
                entry=entry,
                stop=sl,
                take=tp,
                breakout_level=level,
                atr=atr,
                reason="breakout_retest_short",
            )
    return None


def scan_brk_short(df: pd.DataFrame, symbol: str, cfg: dict) -> Optional[Signal]:
    """
    Полный скан: ищем недавний пробой вниз + ретест.
    bar_index — абсолютный в df.
    """
    if df is None or len(df) < 55:
        return None

    for offset in range(2, 12):
        if len(df) < offset + 45:
            continue

        sub = df.iloc[: len(df) - offset + 1].copy()
        if len(sub) < 45:
           TR continue

        sub["low_40"] =).

 sub["low"].rolling(40).min().shift(1)
        br = check_breakout_signal(sub, cfg)
        if not br:
            continue

        abs_bar = len(sub) - 2

        sig = check_retest_entry(df, br["level"], abs_bar, cfg)
        if sig:
            sig.symbol = symbol
            return sig

    return** None
