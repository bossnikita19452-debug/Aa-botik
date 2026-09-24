"""MR_SHORT — mean reversion шорт (фаза RANGE)."""
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
    atr: float
    reason: str = ""


def scan_mr_short(df: pd.DataFrame, symbol: str, cfg: dict) -> Optional[Signal]:
    """
    close > BB_up, RSI > 70, close < EMA200, ATR < 1.5 * SMA(ATR,30)
    SL = entry * (1 + 0.01), TP = BB_mid
    """
    if df is None or len(df) < 50:
        return None

    sig_row = df.iloc[-2]
    entry_row = df.iloc[-1]

    for col in ("bb_up", "bb_mid", "rsi14", "ema200", "atr14", "atr_sma30"):
        if col not in sig_row or pd.isna(sig_row[col]):
            return None

    if not (sig_row["close"] > sig_row["bb_up"]):
        return None
    if not (sig_row["rsi14"] > cfg.get("rsi_short_min", 70)):
        return None
    if not (sig_row["close"] < sig_row["ema200"]):
        return None
    atr_sma = sig_row["atr_sma30"]
    if atr_sma is None or atr_sma <= 0:
        return None
    if not (sig_row["atr14"] < cfg.get("atr_mult_max", 1.5) * atr_sma):
        return None

    entry = float(entry_row["open"])
    sl_pct = cfg.get("sl_pct", 1.0) / 100.0
    sl = entry * (1 + sl_pct)
    tp = float(sig_row["bb_mid"])
    if tp >= entry:
        return None
    atr = float(sig_row["atr14"])

    return Signal(
        strategy="MR_SHORT",
        side="SHORT",
        symbol=symbol,
        entry=entry,
        stop=sl,
        take=tp,
        atr=atr,
        reason="bb_rsi_overbought",
    )
