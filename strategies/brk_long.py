"""BRK_LONG — пробой вверх (фаза UPTREND). Приведён к эталону Colab.

Добавлен фильтр MAX_ENTRY_GAP = 1.0%:
если open следующей свечи ушёл от уровня ретеста больше чем на 1% — сделку пропускаем.
Это отсекает сделки с плохой точкой входа (проверено на Colab: WR 60.7% → 63.9%).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


LOCK_BARS = 8
MAX_ENTRY_GAP = 0.01  # 1.0%


@dataclass
class Signal:
    strategy: str
    side: str  # LONG
    symbol: str
    entry: float
    stop: float
    take: float
    breakout_level: float
    atr: float
    reason: str = ""


def check_breakout_signal(df: pd.DataFrame, cfg: dict) -> Optional[dict]:
    """
    Условия пробоя (на закрытой свече -2):
    1. EMA20 > EMA50
    2. close > High(40).shift(1)
    3. volume > 2.5 * SMA(volume, 20)
    4. RSI 55..70

    Возвращает level = high_40 (уровень пробоя), bar_index абсолютный.
    """
    if df is None or len(df) < 50:
        return None

    i = -2
    row = df.iloc[i]

    if pd.isna(row.get("ema20")) or pd.isna(row.get("high_40")):
        return None
    if not (row["ema20"] > row["ema50"]):
        return None
    if not (row["close"] > row["high_40"]):
        return None

    vol_sma = row.get("vol_sma20")
    if vol_sma is None or vol_sma <= 0:
        return None
    if row["volume"] < cfg.get("volume_mult", 2.5) * vol_sma:
        return None

    rsi = row.get("rsi14")
    if rsi is None or not (cfg.get("rsi_long_min", 55) <= rsi <= cfg.get("rsi_long_max", 70)):
        return None

    return {
        "level": float(row["high_40"]),
        "bar_index": len(df) - 2,
    }


def check_retest_entry(
    df: pd.DataFrame,
    breakout_level: float,
    breakout_bar: int,
    cfg: dict,
) -> Optional[Signal]:
    """
    Ретест в течение retest_bars свечей после пробоя:
    low <= level * 1.001 и close > level → вход на open следующей.

    Фильтр MAX_ENTRY_GAP: если (entry - level) / level > 1% — пропускаем.
    """
    retest_bars = cfg.get("retest_bars", 8)
    start = breakout_bar + 1
    end = min(breakout_bar + 1 + retest_bars, len(df) - 1)
    if start >= len(df) - 1:
        return None

    for j in range(start, end):
        row = df.iloc[j]
        level = breakout_level

        if row["low"] <= level * 1.001 and row["close"] > level:
            if j + 1 >= len(df):
                return None

            entry_row = df.iloc[j + 1]
            entry = float(entry_row["open"])

            # ─── ФИЛЬТР: entry не должен быть слишком далеко от level
            if level > 0:
                gap = (entry - level) / level
                if gap > MAX_ENTRY_GAP:
                    return None
            # ──────────────────────────────────────────────────

            atr = float(entry_row["atr14"]) if pd.notna(entry_row.get("atr14")) else entry * 0.01

            base_sl = level * (1 - 0.005)
            sl_dist = entry - base_sl
            min_sl = cfg.get("sl_atr_min", 0.3) * atr
            max_sl = cfg.get("sl_atr_max", 1.5) * atr
            sl_dist = max(min_sl, min(max_sl, sl_dist))
            if sl_dist <= 0:
                return None

            sl = entry - sl_dist
            tp = entry + cfg.get("rr", 1.5) * sl_dist

            return Signal(
                strategy="BRK_LONG",
                side="LONG",
                symbol="",
                entry=entry,
                stop=sl,
                take=tp,
                breakout_level=level,
                atr=atr,
                reason="breakout_retest",
            )
    return None


def scan_brk_long(df: pd.DataFrame, symbol: str, cfg: dict) -> Optional[Signal]:
    """
    Полный скан: ищем недавний пробой + ретест.
    bar_index — абсолютный в df.
    """
    if df is None or len(df) < 55:
        return None

    for offset in range(2, 12):
        if len(df) < offset + 45:
            continue

        sub = df.iloc[: len(df) - offset + 1].copy()
        if len(sub) < 45:
            continue

        sub["high_40"] = sub["high"].rolling(40).max().shift(1)
        br = check_breakout_signal(sub, cfg)
        if not br:
            continue

        abs_bar = len(sub) - 2

        sig = check_retest_entry(df, br["level"], abs_bar, cfg)
        if sig:
            sig.symbol = symbol
            return sig

    return None
