import pandas as pd
import pandas_ta_classic as ta


def calculate_ema(df: pd.DataFrame, length: int) -> pd.Series:
    """EMA с указанным периодом."""
    return ta.ema(df["close"], length=length)


def calculate_rsi(df: pd.DataFrame, length: int = 14) -> pd.Series:
    """RSI с указанным периодом."""
    return ta.rsi(df["close"], length=length)


def calculate_macd(df: pd.DataFrame):
    """MACD: линия, сигнальная, гистограмма."""
    macd = ta.macd(df["close"])
    # pandas_ta_classic возвращает DataFrame с колонками:
    # MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9
    macd_line = macd.iloc[:, 0]
    signal_line = macd.iloc[:, 1]
    histogram = macd.iloc[:, 2]
    return macd_line, signal_line, histogram


def calculate_atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    """ATR (Average True Range) — мера волатильности."""
    return ta.atr(df["high"], df["low"], df["close"], length=length)