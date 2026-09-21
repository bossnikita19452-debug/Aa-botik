import asyncio
from datetime import datetime, timezone, timedelta

import aiohttp
import numpy as np
import pandas as pd

import config
from config import (
    COINS, BYBIT_KLINE_URL, BYBIT_CATEGORY, TIMEFRAME,
    EMA_FAST, EMA_MID, EMA_SLOW, EMA_TREND,
    VOL_SMA_FAST, VOL_SMA_SLOW, ATR_FAST, ATR_SLOW,
    RSI_FAST, RSI_SLOW,
    RR_CLIMAX, RR_L_LONG, RR_BULL_IMPULSE,
    MIN_RISK_PCT, MAX_RISK_PCT,
    MAX_OPEN_POSITIONS, MAX_LEVERAGE, RISK_PER_TRADE_PCT,
    SESSION_WEEKDAYS, SESSION_START_HOUR, SESSION_END_HOUR, MSK_OFFSET_HOURS,
)
from database import save_signal, has_open_position, count_open_positions
from stats_checker import check_open_signals

MSK = timezone(timedelta(hours=MSK_OFFSET_HOURS))


def in_session(now_utc: datetime = None) -> bool:
    """Пн–Пт 10:00–23:00 МСК"""
    now = now_utc or datetime.now(timezone.utc)
    msk = now.astimezone(MSK)
    if msk.weekday() not in SESSION_WEEKDAYS:
        return False
    return SESSION_START_HOUR <= msk.hour < SESSION_END_HOUR


async def fetch_klines(session: aiohttp.ClientSession, symbol: str, limit: int = 300):
    params = {
        "category": BYBIT_CATEGORY,
        "symbol": symbol,
        "interval": TIMEFRAME,
        "limit": limit,
    }
    try:
        async with session.get(BYBIT_KLINE_URL, params=params, timeout=15) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
    except Exception as e:
        print(f"⚠️ {symbol}: {e}")
        return None

    if data.get("retCode") != 0:
        return None

    rows = data.get("result", {}).get("list", [])
    if not rows:
        return None

    rows = list(reversed(rows))
    df = pd.DataFrame(
        rows,
        columns=["time", "open", "high", "low", "close", "volume", "turnover"]
    )
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
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


def _risk_ok(entry: float, sl: float) -> bool:
    risk = abs(entry - sl)
    if risk <= 0:
        return False
    rp = risk / entry * 100
    return MIN_RISK_PCT <= rp <= MAX_RISK_PCT


def mod_climax(row) -> dict | None:
    """Volume climax rejection"""
    if row["volume"] < row["vol20"] * 2.8:
        return None
    rng = float(row["range"])
    if rng <= 0:
        return None
    atr = float(row["atr14"])
    if atr <= 0 or np.isnan(atr):
        return None

    # LONG after panic
    if row["rsi14"] <= 26 and row["lower_wick"] >= 0.58 * rng:
        entry = float(row["close"])
        sl = float(row["low"]) - 0.08 * atr
        if not _risk_ok(entry, sl):
            return None
        risk = entry - sl
        tp = entry + RR_CLIMAX * risk
        return {
            "direction": "LONG", "entry": entry, "stop": sl, "take": tp,
            "risk_distance": risk, "atr": atr, "module": "Climax",
        }

    # SHORT after euphoria
    if row["rsi14"] >= 74 and row["upper_wick"] >= 0.58 * rng:
        entry = float(row["close"])
        sl = float(row["high"]) + 0.08 * atr
        if not _risk_ok(entry, sl):
            return None
        risk = sl - entry
        tp = entry - RR_CLIMAX * risk
        return {
            "direction": "SHORT", "entry": entry, "stop": sl, "take": tp,
            "risk_distance": risk, "atr": atr, "module": "Climax",
        }
    return None


def mod_l_long(row) -> dict | None:
    """Tight long pullback"""
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
    tp = entry + RR_L_LONG * risk
    return {
        "direction": "LONG", "entry": entry, "stop": sl, "take": tp,
        "risk_distance": risk, "atr": atr, "module": "L_Long",
    }


def is_bull_regime(btc_row) -> bool:
    if btc_row is None:
        return False
    if btc_row["close"] < btc_row["ema50"]:
        return False
    r12 = float(btc_row["ret_12"]) if not np.isnan(btc_row["ret_12"]) else 0
    return r12 > 0.004


def mod_bull_impulse(row, btc_row, breadth: float) -> dict | None:
    """Market-wide impulse long (only in bull regime)"""
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
    tp = entry + RR_BULL_IMPULSE * risk
    return {
        "direction": "LONG", "entry": entry, "stop": sl, "take": tp,
        "risk_distance": risk, "atr": atr, "module": "Bull_Impulse",
    }


def check_signal(row, btc_row, breadth: float, bull: bool) -> dict | None:
    """Priority: Climax → L_Long → Bull_Impulse"""
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


async def scan_once(bot):
    if not config.SCANNING_ENABLED:
        print("⏸ Сканирование остановлено")
        return

    if not in_session():
        print("⏸ Вне сессии (Пн–Пт 10:00–23:00 МСК)")
        return

    open_count = count_open_positions()
    if open_count >= MAX_OPEN_POSITIONS:
        print(f"⛔ Уже открыто {open_count}/{MAX_OPEN_POSITIONS} — пропуск")
        return

    print(f"=== Сканирование 5m: {datetime.utcnow().isoformat()} ===")
    print(f"📊 Открытых позиций: {open_count}/{MAX_OPEN_POSITIONS}")

    async with aiohttp.ClientSession() as session:
        # BTC + all coins
        dfs = {}
        for sym in COINS:
            df = await fetch_klines(session, sym, limit=300)
            if df is not None and len(df) >= 220:
                dfs[sym] = add_indicators(df)
            await asyncio.sleep(0.08)

        if "BTCUSDT" not in dfs:
            print("❌ Нет данных BTC")
            return

        btc = dfs["BTCUSDT"]
        btc_row = btc.iloc[-1]
        bull = is_bull_regime(btc_row)

        # Breadth: доля зелёных на последней свече
        green = sum(1 for d in dfs.values() if d.iloc[-1]["ret_1"] > 0)
        breadth = green / len(dfs) if dfs else 0

        print(f"₿ BTC: ${btc_row['close']:.2f} | Bull={bull} | Breadth={breadth*100:.0f}%")

        found = 0
        for symbol, df in dfs.items():
            if not config.SCANNING_ENABLED:
                return
            if count_open_positions() >= MAX_OPEN_POSITIONS:
                break
            if has_open_position(symbol):
                continue

            row = df.iloc[-1]
            signal = check_signal(row, btc_row, breadth, bull)
            if not signal:
                continue

            signal["symbol"] = symbol
            risk_pct = signal["risk_distance"] / signal["entry"] * 100

            save_signal(signal)
            found += 1

            leverage = MAX_LEVERAGE
            position_pct = (RISK_PER_TRADE_PCT / risk_pct) * 100 if risk_pct > 0 else 0
            margin_pct = position_pct / leverage if leverage else 0
            mod = signal.get("module", "?")
            rr = {
                "Climax": RR_CLIMAX,
                "L_Long": RR_L_LONG,
                "Bull_Impulse": RR_BULL_IMPULSE,
            }.get(mod, 1.25)

            emoji = "🟢" if signal["direction"] == "LONG" else "🔴"
            mod_emoji = config.SIGNAL_EMOJI.get(mod, "")
            print(
                f"✅ {signal['direction']} {symbol} | {mod} | "
                f"Entry {signal['entry']:.4f} SL {signal['stop']:.4f} TP {signal['take']:.4f} | "
                f"Risk {risk_pct:.2f}%"
            )

            text = (
                f"{emoji} <b>{signal['direction']} | {symbol}</b> {mod_emoji}\n"
                f"Модуль: <b>{mod}</b>\n\n"
                f"Вход: <code>{signal['entry']:.6f}</code>\n"
                f"Стоп: <code>{signal['stop']:.6f}</code>\n"
                f"Тейк: <code>{signal['take']:.6f}</code>\n"
                f"R:R = <b>1:{rr}</b>\n"
                f"ATR: <code>{signal['atr']:.6f}</code>\n"
                f"Риск: <b>{risk_pct:.2f}%</b>\n\n"
                f"⚡ Плечо: <b>{leverage}x</b>\n"
                f"💰 Риск депозита: <b>{RISK_PER_TRADE_PCT}%</b>\n"
                f"📊 Размер позиции: <b>{position_pct:.1f}%</b>\n"
                f"📌 Маржа: <b>{margin_pct:.2f}%</b>\n"
                f"⏱ Таймаут: {config.MAX_HOLD_BARS} свечей (5m)"
            )
            if config.CHANNEL_ID:
                try:
                    await bot.send_message(config.CHANNEL_ID, text, parse_mode="HTML")
                except Exception as e:
                    print(f"Ошибка отправки: {e}")

        print(f"=== Найдено сигналов: {found} ===")

    await check_open_signals()
