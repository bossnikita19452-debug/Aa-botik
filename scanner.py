import asyncio
import aiohttp
import pandas as pd
from datetime import datetime

import config
from config import (
    COINS, BYBIT_KLINE_URL, BYBIT_CATEGORY, TIMEFRAME,
    BTC_EMA_PERIOD, ALT_EMA_PERIOD, VOLUME_SMA_PERIOD, ATR_PERIOD,
    LOOKBACK_BARS, MIN_TOUCHES, TOUCH_TOLERANCE,
    VOLUME_MULT_LONG, VOLUME_MULT_SHORT,
    ATR_SL_MULTIPLIER, RR_RATIO,
    MAX_LEVERAGE, RISK_PER_TRADE_PCT, MIN_RISK_PCT,
    MAX_OPEN_POSITIONS,
)
from database import save_signal, has_open_position, count_open_positions
from stats_checker import check_open_signals


async def fetch_klines(session: aiohttp.ClientSession, symbol: str, limit: int = 1000):
    params = {
        "category": BYBIT_CATEGORY,
        "symbol": symbol,
        "interval": TIMEFRAME,
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


def check_signal(df_alt: pd.DataFrame, df_btc: pd.DataFrame, symbol: str):
    if len(df_alt) < 850 or len(df_btc) < 60:
        return None

    btc_close = df_btc["close"].iloc[-1]
    btc_ema50 = df:
_btc["close"].ewm(span=BTC       _EMA_PERIOD).mean().iloc[-1 return]
    btc_is_bullish = btc_close None > btc_ema50

    close = df_

alt["close"].iloc[-1]
       volume = df_alt["volume"].iloc[-1]
    vol_sma20 = df_alt["volume"].rolling(VOLUME_SMA_PERIOD).mean().iloc[-1]
    atr14 = (df_alt["high"] - df_alt["low"]).rolling(ATR_PERIOD).mean().iloc[-1]
    ema200_h1 = df_alt["close"].ewm(span=ALT_EMA_PERIOD).mean().iloc[-1]

    if pd.isna(vol_sma20) or pd.isna(atr14) or pd.isna(ema200_h1):
        return None

    last_48_highs = df_alt["high"].iloc[-LOOKBACK_BARS - 1:-1]
    last_48_lows = df_alt["low"].iloc[-LOOKBACK_BARS - 1:-1]

    if len(last_48_highs) < LOOKBACK_BARS or len(last_48_lows) < LOOKBACK_BARS resistance = last_48_highs.max()
    support = last_48_lows.min()

    resistance_touches = (last_48_highs >= resistance * (1 - TOUCH_TOLERANCE)).sum()
    support_touches = (last_48_lows <= support * (1 + TOUCH_TOLERANCE)).sum()

    # LONG
    if (btc_is_bullish and close > ema200_h1
            and resistance_touches >= MIN_TOUCHES
            and close > resistance
            and volume >= VOLUME_MULT_LONG * vol_sma20):
        sl = close - (ATR_SL_MULTIPLIER * atr14)
        risk_dist = close - sl
        tp = close + (RR_RATIO * risk_dist)
        return {
            "symbol": symbol, "direction": "LONG",
            "entry": float(close), "stop": float(sl),
            "take": float(tp), "risk_distance": float(risk_dist),
            "atr": float(atr14),
        }

    # SHORT
    if (not btc_is_bullish and close < ema200_h1
            and support_touches >= MIN_TOUCHES
            and close < support
            and volume >= VOLUME_MULT_SHORT * vol_sma20):
        sl = close + (ATR_SL_MULTIPLIER * atr14)
        risk_dist = sl - close
        tp = close - (RR_RATIO * risk_dist)
        return {
            "symbol": symbol, "direction": "SHORT",
            "entry": float(close), "stop": float(sl),
            "take": float(tp), "risk_distance": float(risk_dist),
            "atr": float(atr14),
        }

    return None


async def scan_once(bot):
    if not config.SCANNING_ENABLED:
        print("⏸ Сканирование остановлено")
        return

    open_count = count_open_positions()
    if open_count >= MAX_OPEN_POSITIONS:
        print(f"⛔ Уже открыто {open_count}/{MAX_OPEN_POSITIONS} — пропуск")
        return

    print(f"=== Сканирование: {datetime.utcnow().isoformat()} ===")
    print(f"📊 Открытых позиций: {open_count}/{MAX_OPEN_POSITIONS}")

    async with aiohttp.ClientSession() as session:
        df_btc = await fetch_klines(session, "BTCUSDT", limit=200)
        if df_btc is None or df_btc.empty:
            print("❌ Не удалось получить свечи BTC")
            return

        btc_close = df_btc["close"].iloc[-1]
        btc_ema50 = df_btc["close"].ewm(span=BTC_EMA_PERIOD).mean().iloc[-1]
        btc_is_bullish = btc_close > btc_ema50
        print(f"₿ BTC: ${btc_close:.2f} | EMA50: ${btc_ema50:.2f} | Режим: {'BULL' if btc_is_bullish else 'BEAR'}")

        found = 0
        for symbol in COINS:
            if not config.SCANNING_ENABLED:
                return
            if count_open_positions() >= MAX_OPEN_POSITIONS:
                break
            if has_open_position(symbol):
                continue

            df_alt = await fetch_klines(session, symbol, limit=1000)
            if df_alt is None or df_alt.empty:
                continue

            signal = check_signal(df_alt, df_btc, symbol)
            if signal:
                risk_pct = signal["risk_distance"] / signal["entry"] * 100

                # Фильтр по минимальному риску
                if risk_pct < MIN_RISK_PCT:
                    print(f"⛔ {symbol}: риск {risk_pct:.2f}% < {MIN_RISK_PCT}% — пропуск")
                    continue

                save_signal(signal)
                found += 1

                # ─── Расчёт позиции и плеча ───────────────────
                leverage = MAX_LEVERAGE  # из config.py = 50
                position_pct = (RISK_PER_TRADE_PCT / risk_pct) * 100
                margin_pct = position_pct / leverage

                print(f"✅ {signal['direction']} {symbol} | Entry ${signal['entry']:.4f} | SL ${signal['stop']:.4f} | TP ${signal['take']:.4f} | Риск {risk_pct:.2f}% | Плечо {leverage}x")

                emoji = "🟢" if signal["direction"] == "LONG" else "🔴"
                text = (
                    f"{emoji} <b>{signal['direction']} | {symbol}</b>\n\n"
                    f"Вход: <code>{signal['entry']:.6f}</code>\n"
                    f"Стоп: <code>{signal['stop']:.6f}</code>\n"
                    f"Тейк: <code>{signal['take']:.6f}</code>\n"
                    f"R:R = <b>1:{RR_RATIO}</b>\n"
                    f"ATR: <code>{signal['atr']:.6f}</code>\n"
                    f"Риск: <b>{risk_pct:.2f}%</b>\n\n"
                    f"⚡ Плечо: <b>{leverage}x</b> (макс)\n"
                    f"💰 Риск: <b>{RISK_PER_TRADE_PCT}%</b> депозита\n"
                    f"📊 Размер позиции: <b>{position_pct:.1f}%</b> депозита\n"
                    f"📌 Маржа: <b>{margin_pct:.2f}%</b> депозита"
                )
                if config.CHANNEL_ID:
                    try:
                        await bot.send_message(config.CHANNEL_ID, text, parse_mode="HTML")
                    except Exception as e:
                        print(f"Ошибка отправки: {e}")

            await asyncio.sleep(0.3)

        print(f"=== Найдено сигналов: {found} ===")

    await check_open_signals()
