from indicators import calculate_atr
import pandas as pd


def calculate_tp_sl(
    df: pd.DataFrame,
    direction: str = "long",
    atr_multiplier_sl: float = 1.5,
    atr_multiplier_tp: float = 3.0,
) -> dict | None:
    """
    Рассчитать TP и SL на основе ATR.
    
    df: свечи (5м, 15м, 1ч, 4ч или 1D — в зависимости от типа сделки)
    direction: только "long" для нашего случая
    atr_multiplier_sl: множитель ATR для стопа
    atr_multiplier_tp: множитель ATR для тейка
    
    Возвращает dict с entry, tp, sl, rr или None, если RR вне диапазона.
    """
    if len(df) < 20:
        return None

    atr_series = calculate_atr(df, 14)
    if atr_series is None or atr_series.isna().all():
        return None

    atr = atr_series.iloc[-1]
    entry = df["close"].iloc[-1]

    if atr <= 0 or entry <= 0:
        return None

    # Для Long: стоп ниже входа, тейк выше входа
    sl = entry - atr * atr_multiplier_sl
    tp = entry + atr * atr_multiplier_tp

    # Проверяем, что стоп не ушёл в минус
    if sl <= 0:
        return None

    risk = entry - sl
    reward = tp - entry

    if risk <= 0:
        return None

    rr_ratio = reward / risk

    return {
        "entry": round(entry, 6),
        "tp": round(tp, 6),
        "sl": round(sl, 6),
        "rr": round(rr_ratio, 2),
        "atr": round(atr, 6),
    }


def is_rr_valid(rr: float, min_rr: float = 1.5, max_rr: float = 3.0) -> bool:
    """Проверить, что RR в допустимом диапазоне."""
    return min_rr <= rr <= max_rr


def adjust_tp_for_rr(
    entry: float,
    sl: float,
    rr_target: float = 2.0,
) -> float:
    """
    Скорректировать TP так, чтобы RR был равен rr_target.
    Используется, если ИИ предложил TP, но RR вышел за диапазон.
    """
    risk = entry - sl
    if risk <= 0:
        return entry
    return entry + risk * rr_target