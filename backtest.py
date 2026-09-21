"""
Автономный бэктест стратегии Climax + L_Long + Bull_Impulse.
Не требует Telegram, БД, бота. Просто запусти: python backtest.py
"""

import asyncio
from datetime import datetime, timezone, timedelta

import aiohttp
import numpy as np
import pandas as pd

# ─── Импортируем параметры из config.py ───────────────────────────
from config import (
    COINS, BYBIT_KLINE_URL, BYBIT_CATEGORY, TIMEFRAME,
    EMA_FAST, EMA_MID, EMA_SLOW, EMA_TREND,
    VOL_SMA_FAST, VOL_SMA_SLOW, ATR_FAST, ATR_SLOW,
    RSI_FAST, RSI_SLOW,
    RR_CLIMAX, RR_L_LONG, RR_BULL_IMPULSE,
    MIN_RISK_PCT, MAX_RISK_PCT,
    SESSION_WEEKDAYS, SESSION_START_HOUR, SESSION_END_HOUR, MSK_OFFSET_HOURS,
    MAX_HOLD_BARS,
)

MSK = timezone(timedelta(hours=MSK_OFFSET_HOURS))

# ─── Сколько дней тестировать и с каким плечом ───────────────────
BACKTEST_DAYS = 30          # Можно поставить 7, 30, 90
INITIAL_DEPOSIT = 1000      # USDT
RISK_PER_TRADE_PCT = 1.0    # % депозита на сделку
COMMISSION_PCT = 0.1        # % на вход и выход (Bybit taker ≈ 0.055)


def in_session(dt_utc: datetime) -> bool:
    """Пн–Пт 10:00–23:00 МСК."""
    msk = dt_utc.astimezone(MSK)
    if msk.weekday() not in SESSION_WEEKDAYS:
        return False
    return SESSION_START_HOUR <= msk.hour < SESSION_END_HOUR


async def fetch_klines(session, symbol, interval="5", limit=1000):
    """Получить свечи с Bybit."""
    params = {
        "category": BYBIT_CATEGORY,
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    try:
        async with session.get(BYBIT_KLINE_URL, params=params, timeout=15) as resp:
            if resp.status != 200:
                print(f"⚠️ {symbol}: HTTP {resp.status}")
                return None
            data = await resp.json()
    except Exception as e:
        print(f"⚠️ {symbol}: {e}")
        return None

    if data.get("retCode") != 0:
        print(f"⚠️ {symbol}: {data.get('retMsg')}")
        return None

    rows = data.get("result", {}).get("list", [])
    if not rows:
        print(f"⚠️ {symbol}: пустой список")
        return None

    rows = list(reversed(rows))
    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume", "turnover"])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna().reset_index(drop=True)


def add_indicators(df):
    """Добавить все индикаторы."""
    df = df.copy()
    c = df["close"]
    df["ema9"] = c.ewm(span=EMA_FAST, adjust=False).mean()
    df["ema21"] = c.ewm(span=EMA_MID, adjust=False).mean()
    df["ema50"] = c.ewm(span=EMA_SLOW, adjust=False).mean()
    df["ema200"] = c.ewm(span=EMA_TREND, adjust=False).mean()
    df["vol12"] = df["volume"].rolling(VOL_SMA_FAST).mean()
    df["vol20"] = df["volume"].rolling(VOL_SMA_SLOW).mean()

    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - c.shift(1)).abs(),
        (df["low"] - c.shift(1)).abs(),
    ], axis=1).max(axis=1)
    df["atr10"] = tr.rolling(ATR_FAST).mean()
    df["atr14"] = tr.rolling(ATR_SLOW).mean()

    delta = c.diff()
    g5 = delta.where(delta > 0, 0).rolling(RSI_FAST).mean()
    l5 = (-delta.where(delta < 0, 0)).rolling(RSI_FAST).mean()
    df["rsi5"] = 100 - (100 / (1 + g5 / l5.replace(0, np.nan)))
    g14 = delta.where(delta > 0, 0).rolling(RSI_SLOW).mean()
    l14 = (-delta.where(delta < 0, 0)).rolling(RSI_SLOW).mean()
    df["rsi14"] = 100 - (100 / (1 + g14 / l14.replace(0, np.nan)))

    df["body"] = (c - df["open"]).abs()
    df["upper_wick"] = df["high"] - df[["open", "close"]].max(axis=1)
    df["lower_wick"] = df[["open", "close"]].min(axis=1) - df["low"]
    df["range"] = df["high"] - df["low"]
    df["ret_1"] = c.pct_change(1)
    df["ret_3"] = c.pct_change(3)
    df["ret_6"] = c.pct_change(6)
    df["ret_12"] = c.pct_change(12)
    return df


def _risk_ok(entry, sl):
    risk = abs(entry - sl)
    if risk <= 0:
        return False
    rp = risk / entry * 100
    return MIN_RISK_PCT <= rp <= MAX_RISK_PCT


def mod_climax(row):
    if row["volume"] < row["vol20"] * 2.8:
        return None
    rng = float(row["range"])
    if rng <= 0:
        return None
    atr = float(row["atr14"])
    if atr <= 0 or np.isnan(atr):
        return None

    if row["rsi14"] <= 26 and row["lower_wick"] >= 0.58 * rng:
        entry = float(row["close"])
        sl = float(row["low"]) - 0.08 * atr
        if not _risk_ok(entry, sl):
            return None
        risk = entry - sl
        return {"direction": "LONG", "entry": entry, "stop": sl,
                "take": entry + RR_CLIMAX * risk, "risk_distance": risk,
                "atr": atr, "module": "Climax"}

    if row["rsi14"] >= 74 and row["upper_wick"] >= 0.58 * rng:
        entry = float(row["close"])
        sl = float(row["high"]) + 0.08 * atr
        if not _risk_ok(entry, sl):
            return None
        risk = sl - entry
        return {"direction": "SHORT", "entry": entry, "stop": sl,
                "take": entry - RR_CLIMAX * risk, "risk_distance": risk,
                "atr": atr, "module": "Climax"}
    return None


def mod_l_long(row):
    if not (row["ema9"] > row["ema21"] and row["close"] > row["ema50"]):
        return None
    if not (row["low"] <= row["ema9"] and row["close"] > row["ema9"]):
        return None
    if not (row["close"] > row["open"] and row["lower_wick"] >= row["body"] * 0.50):
        return None
    if row["volume"] < row["vol12"] * 1.15:
        return None
    if not (30 <= row["rsi5"] <= 58):
        return None

    atr = float(row["atr10"])
    if atr <= 0 or np.isnan(atr):
        return None
    entry = float(row["close"])
    sl = min(float(row["low"]), float(row["ema9"])) - 0.12 * atr
    if not _risk_ok(entry, sl):
        return None
    risk = entry - sl
    return {"direction": "LONG", "entry": entry, "stop": sl,
            "take": entry + RR_L_LONG * risk, "risk_distance": risk,
            "atr": atr, "module": "L_Long"}


def is_bull_regime(btc_row):
    if btc_row is None:
        return False
    if btc_row["close"] < btc_row["ema50"]:
        return False
    r12 = float(btc_row["ret_12"]) if not np.isnan(btc_row["ret_12"]) else 0
    return r12 > 0.004


def mod_bull_impulse(row, btc_row, breadth):
    if btc_row is None:
        return None
    r3 = float(btc_row["ret_3"]) if not np.isnan(btc_row["ret_3"]) else 0
    r6 = float(btc_row["ret_6"]) if not np.isnan(btc_row["ret_6"]) else 0
    if not (r3 >= 0.008 or r6 >= 0.015):
        return None
    if breadth < 0.50:
        return None
    if row["close"] < row["ema50"] * 0.988:
        return None
    if row["volume"] < row["vol12"] * 1.05:
        return None
    if row["rsi5"] > 80:
        return None
    if not (row["close"] > row["open"] or row["close"] > row["ema9"]):
        return None

    atr = float(row["atr10"])
    if atr <= 0 or np.isnan(atr):
        return None
    entry = float(row["close"])
    sl = min(float(row["low"]), float(row["ema9"])) - 0.15 * atr
    if not _risk_ok(entry, sl):
        return None
    risk = entry - sl
    return {"direction": "LONG", "entry": entry, "stop": sl,
            "take": entry + RR_BULL_IMPULSE * risk, "risk_distance": risk,
            "atr": atr, "module": "Bull_Impulse"}


def check_signal(row, btc_row, breadth, bull):
    sig = mod_climax(row)
    if sig:
        return sig
    sig = mod_l_long(row)
    if sig:
        return sig
    if bull:
        sig = mod_bull_impulse(row, btc_row, breadth)
        if sig:
            return sig
    return None


async def backtest():
    print(f"=== БЭКТЕСТ: {BACKTEST_DAYS} дней, M5, {len(COINS)} монет ===")
    print(f"📅 Старт: {datetime.utcnow().isoformat()}")

    trades = []

    async with aiohttp.ClientSession() as session:
        # Загружаем все монеты (по 1000 свечей ≈ 3.5 дня M5)
        # Для 30 дней нужно качать несколько раз — упростим, качаем 1000
        data = {}
        for sym in COINS:
            df = await fetch_klines(session, sym, limit=1000)
            if df is None or len(df) < 220:
                print(f"⚠️ {sym}: пропуск (мало данных)")
                continue
            data[sym] = add_indicators(df)
            await asyncio.sleep(0.08)

        if "BTCUSDT" not in data:
            print("❌ Нет данных BTC")
            return

        # Берём данные BTC для контекста
        btc_df = data["BTCUSDT"]

        # Проходим по всем барам (кроме первых 220 — там нет индикаторов)
        min_len = min(len(df) for df in data.values())
        start_idx = 220

        print(f"📊 Свечей: {min_len}, начало с бара {start_idx}")

        for i in range(start_idx, min_len):
            # ─── Контекст: BTC и breadth ───────────────────────────
            btc_row = btc_df.iloc[i]
            breadth = sum(
                1 for sym, df in data.items()
                if df.iloc[i]["ret_1"] > 0
            ) / len(data)

            bull = is_bull_regime(btc_row)

            # ─── Сигналы по всем монетам ───────────────────────────
            for sym, df in data.items():
                row = df.iloc[i]

                # Проверка сессии
                try:
                    ts = int(df.iloc[i]["time"])
                    dt_utc = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                except Exception:
                    continue
                if not in_session(dt_utc):
                    continue

                signal = check_signal(row, btc_row, breadth, bull)
                if not signal:
                    continue

                # ─── Симуляция сделки ──────────────────────────────
                entry = signal["entry"]
                sl = signal["stop"]
                tp = signal["take"]
                direction = signal["direction"]

                # Идём вперёд до MAX_HOLD_BARS, ищем TP/SL
                result = None
                for j in range(i + 1, min(i + 1 + MAX_HOLD_BARS, min_len)):
                    future = df.iloc[j]
                    if direction == "LONG":
                        if future["low"] <= sl:
                            result = "loss"
                            break
                        if future["high"] >= tp:
                            result = "win"
                            break
                    else:  # SHORT
                        if future["high"] >= sl:
                            result = "loss"
                            break
                        if future["low"] <= tp:
                            result = "win"
                            break

                if result is None:
                    result = "expired"

                trades.append({
                    "symbol": sym,
                    "module": signal["module"],
                    "direction": direction,
                    "entry": entry,
                    "sl": sl,
                    "tp": tp,
                    "result": result,
                    "risk_distance": signal["risk_distance"],
                })

                # Пауза после сигнала (не открываем повторно на той же монете)
                # В реальном боте это делается через has_open_position

    # ─── ОТЧЁТ ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("📊 ОТЧЁТ БЭКТЕСТА")
    print("=" * 60)

    total = len(trades)
    if total == 0:
        print("❌ Ни одной сделки. Фильтры слишком строгие.")
        return

    wins = sum(1 for t in trades if t["result"] == "win")
    losses = sum(1 for t in trades if t["result"] == "loss")
    expired = sum(1 for t in trades if t["result"] == "expired")

    closed = wins + losses
    wr_pure = round(wins / closed * 100, 1) if closed > 0 else 0
    wr_total = round(wins / total * 100, 1)

    print(f"Всего сделок: {total}")
    print(f"✅ WIN: {wins}")
    print(f"❌ LOSS: {losses}")
    print(f"⏰ EXPIRED: {expired}")
    print(f"📈 Win Rate (закрытые): {wr_pure}%")
    print(f"📈 Win Rate (общий): {wr_total}%")

    # PnL симуляция
    pnl = 0
    for t in trades:
        risk_pct = t["risk_distance"] / t["entry"] * 100
        if t["result"] == "win":
            pnl += risk_pct * 1.2  # средний RR
        elif t["result"] == "loss":
            pnl -= risk_pct
        pnl -= COMMISSION_PCT * 2  # комиссия вход+выход

    print(f"💰 PnL (сумма %): {pnl:.2f}%")

    # По модулям
    print("\n📋 По модулям:")
    for mod_name in ["Climax", "L_Long", "Bull_Impulse"]:
        mod_trades = [t for t in trades if t["module"] == mod_name]
        if not mod_trades:
            continue
        mw = sum(1 for t in mod_trades if t["result"] == "win")
        ml = sum(1 for t in mod_trades if t["result"] == "loss")
        mc = mw + ml
        mwr = round(mw / mc * 100, 1) if mc > 0 else 0
        print(f"  {mod_name}: {len(mod_trades)} сделок, WR {mwr}%")

    # По монетам (топ-5)
    print("\n📋 Топ монет по количеству сигналов:")
    from collections import Counter
    cnt = Counter(t["symbol"] for t in trades)
    for sym, c in cnt.most_common(5):
        print(f"  {sym}: {c} сигналов")

    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(backtest())
