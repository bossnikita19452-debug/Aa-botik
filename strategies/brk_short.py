"""BRK_SHORT — пробой вниз (фаза DOWNTREND). Зеркало BRK_LONG."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class Signal:
    strategy: str
    side: str
    symbol: str
    entry: float
    stop: float
    take: float
    breakout_level: float
    atr: float
    reason: str = ""


def check_breakout_signal(df: pd.DataFrame, cfg: dict) -> Optional[dict]:
    if df is None or len(df) < 50:
        return None
    row = df.iloc[-2]
    if pd.isna(row.get("ema20")) or pd.isna(row.get("low_40")):
        return None
    if not (row["ema20"] < row["ema50"]):
        return None
    if not (row["close"] < row["low_40"]):
        return None
    vol_sma = row.get("vol_sma20")
    if vol_sma is None or vol_sma <= 0 or row["volume"] < cfg.get("volume_mult", 2.5) * vol_sma:
        return None
    rsi = row.get("rsi14")
    if rsi is None or not (cfg.get("rsi_short_min", 30) <= rsi <= cfg.get("rsi_short_max", 45)):
        return None
    return {"level": float(row["close"]), "bar_index": len(df) - 2}


def check_retest_entry(
    df: pd.DataFrame, breakout_level: float, breakout_bar: int, cfg: dict
) -> Optional[Signal]:
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
                reason="breakout_retest",
            )
    return None


def scan_brk_short(df: pd.DataFrame, symbol: str, cfg: dict) -> Optional[Signal]:
    if df is None or len(df) < 55:
        return None
    for offset in range(2, 12):
        if len(df) < offset + 45:
            continue
        sub = df.iloc[: len(df) - offset + 1].copy()
        sub["low_40"] = sub["low"].rolling(40).min().shift(1)
        br = check_breakout_signal(sub, cfg)
        if not br:
            continue
        sig = check_retest_entry(df, br["level"], br["bar_index"], cfg)
        if sig:
            sig.symbol = symbol
            return sig
    return None
