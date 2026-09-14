import asyncio
import aiohttp
import pandas as pd
from bingx_py import BingXClient

from config import (
    BINGX_API_KEY, BINGX_SECRET_KEY,
    MIN_VOLUME_USDT, MIN_RR, MAX_RR,
    SCALP_ENABLED, SWING_ENABLED, LONGTERM_ENABLED,
)
from indicators import calculate_ema, calculate_rsi, calculate_macd
from news_scanner import get_news_for_coin
from ai_analyzer import analyze_setup
from risk_calculator import calculate_tp_sl, is_rr_valid


MAX_SYMBOLS = 50


async def get_all_futures_symbols() -> list[str]:
    """Получить список фьючерсных пар BingX через библиотеку."""
    try:
        async with BingXClient(api_key=BINGX_API_KEY, api_secret=BINGX_SECRET_KEY) as client:
            # Правильный вызов метода для фьючерсов
            response = await client.swap.get_contracts()
            symbols = []
            for item in response.get("data", []):
                symbol = item.get("symbol", "")
                if symbol.endswith("-USDT") and item.get("status") == 1:
                    symbols.append(symbol)
            return symbols
    except Exception as e:
        print(f"Ошибка получения списка пар: {e}")
        return []


async def get_klines(symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
    """Получить свечи через библиотеку BingX."""
    try:
        async with BingXClient(api_key=BINGX_API_KEY, api_secret=BINGX_SECRET_KEY) as client:
            # Правильный вызов метода для свечей
            response = await client.market.get_klines_v3(symbol, interval, limit)

        if not isinstance(response, dict) or response.get("code") != 0:
            return pd.DataFrame()

        rows = response.get("data", [])
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=["open_time", "open", "high", "low", "close", "volume", "close_time"])
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna()
    except Exception as e:
        print(f"Ошибка свечей {symbol} {interval}: {e}")
        return pd.DataFrame()


def check_scalp(df_5m, df_15m):
    if len(df_5m) < 100 or len(df_15m) < 30:
        return None
    close = df_5m["close"].iloc[-1]
    ema50 = calculate_ema(df_5m, 50).iloc[-1]
    ema100 = calculate_ema(df_5m, 100).iloc[-1]
    rsi = calculate_rsi(df_15m, 14).iloc[-1]
    _, _, macd_hist = calculate_macd(df_15m)
    macd_pos = macd_hist.iloc[-1] > 0

    conditions = [close > ema50, close > ema100, rsi > 45, macd_pos]
    met = sum(conditions)
    if met < 2:
        return None

    return {
        "type": "scalp",
        "type_label": "Скальп (до часа)",
        "timeframe": "5м + 15м",
        "price": close,
        "rsi": round(rsi, 1),
        "macd_positive": macd_pos,
        "trend_up": close > ema100,
        "met": met,
        "total": 4,
    }


def check_swing(df_1h, df_4h):
    if len(df_1h) < 200 or len(df_4h) < 30:
        return None
    close = df_1h["close"].iloc[-1]
    ema200 = calculate_ema(df_1h, 200).iloc[-1]
    rsi = calculate_rsi(df_4h, 14).iloc[-1]
    _, _, macd_hist = calculate_macd(df_4h)
    macd_pos = macd_hist.iloc[-1] > 0

    conditions = [
        close > ema200 * 0.97,
        40 <= rsi <= 70,
        macd_pos,
        df_4h["close"].iloc[-1] > df_4h["close"].iloc[-2],
    ]
    met = sum(conditions)
    if met < 2:
        return None

    return {
        "type": "swing",
        "type_label": "Среднесрок (до 3 дней)",
        "timeframe": "1ч + 4ч",
        "price": close,
        "rsi": round(rsi, 1),
        "macd_positive": macd_pos,
        "trend_up": close > ema200,
        "met": met,
        "total": 4,
    }


def check_longterm(df_1d):
    if len(df_1d) < 200:
        return None
    close = df_1d["close"].iloc[-1]
    ema200 = calculate_ema(df_1d, 200).iloc[-1]
    rsi = calculate_rsi(df_1d, 14).iloc[-1]

    conditions = [
        close > ema200 * 0.95,
        35 <= rsi <= 75,
        df_1d["close"].iloc[-1] > df_1d["close"].iloc[-5],
    ]
    met = sum(conditions)
    if met < 1:
        return None

    return {
        "type": "longterm",
        "type_label": "Долгосрок (от недели)",
        "timeframe": "1D",
        "price": close,
        "rsi": round(rsi, 1),
        "macd_positive": False,
        "trend_up": close > ema200,
        "met": met,
        "total": 3,
    }


async def scan_all() -> list[dict]:
    signals = []
    all_symbols = await get_all_futures_symbols()
    symbols = all_symbols[:MAX_SYMBOLS]
    print(f"=== Сканирую {len(symbols)} монет из {len(all_symbols)} ===")

    stats = {"no_klines": 0, "low_volume": 0, "no_signal": 0, "candidate": 0}

    async with aiohttp.ClientSession() as session:
        for i, symbol in enumerate(symbols):
            try:
                df_5m = await get_klines(symbol, "5m", 100)
                df_15m = await get_klines(symbol, "15m", 100)
                df_1h = await get_klines(symbol, "1h", 250)
                df_4h = await get_klines(symbol, "4h", 100)
                df_1d = await get_klines(symbol, "1d", 250)

                if df_5m.empty or df_1h.empty or df_1d.empty:
                    print(f"[{i+1}/{len(symbols)}] {symbol}: нет свечей")
                    stats["no_klines"] += 1
                    continue

                volume_24h = df_1h["volume"].tail(24).sum() * df_1h["close"].iloc[-1]
                if volume_24h < MIN_VOLUME_USDT:
                    print(f"[{i+1}/{len(symbols)}] {symbol}: объём {volume_24h:.0f} < {MIN_VOLUME_USDT}")
                    stats["low_volume"] += 1
                    continue

                candidates = []
                if SCALP_ENABLED:
                    c = check_scalp(df_5m, df_15m)
                    if c:
                        candidates.append(c)
                if SWING_ENABLED:
                    c = check_swing(df_1h, df_4h)
                    if c:
                        candidates.append(c)
                if LONGTERM_ENABLED:
                    c = check_longterm(df_1d)
                    if c:
                        candidates.append(c)

                if not candidates:
                    print(f"[{i+1}/{len(symbols)}] {symbol}: тех.сигналов нет")
                    stats["no_signal"] += 1
                    continue

                print(f"[{i+1}/{len(symbols)}] {symbol}: КАНДИДАТ {[c['type'] for c in candidates]}")
                stats["candidate"] += 1

                news = await get_news_for_coin(session, symbol)

                for cand in candidates:
                    if cand["type"] == "scalp":
                        df_for_atr = df_15m
                    elif cand["type"] == "swing":
                        df_for_atr = df_4h
                    else:
                        df_for_atr = df_1d

                    levels = calculate_tp_sl(df_for_atr)
                    if not levels:
                        continue

                    if not is_rr_valid(levels["rr"], MIN_RR, MAX_RR):
                        continue

                    ai_result = await analyze_setup(
                        symbol=symbol,
                        price=cand["price"],
                        rsi=cand["rsi"],
                        macd_positive=cand["macd_positive"],
                        trend_up=cand["trend_up"],
                        news_headlines=news,
                        deal_type=cand["type_label"],
                    )

                    if ai_result.get("signal") != "long":
                        continue

                    signals.append({
                        "symbol": symbol,
                        "type": cand["type"],
                        "type_label": cand["type_label"],
                        "timeframe": cand["timeframe"],
                        "price": cand["price"],
                        "rsi": cand["rsi"],
                        "entry": levels["entry"],
                        "tp": levels["tp"],
                        "sl": levels["sl"],
                        "rr": levels["rr"],
                        "confidence": ai_result.get("confidence", "low"),
                        "reason": ai_result.get("reason", ""),
                        "risk_note": ai_result.get("risk_note", ""),
                    })

                    await asyncio.sleep(1)

            except Exception as e:
                print(f"Ошибка {symbol}: {e}")
                continue

        print(f"=== ИТОГО: {stats} ===")

    conf_order = {"high": 0, "medium": 1, "low": 2}
    signals.sort(key=lambda s: conf_order.get(s["confidence"], 3))
    return signals
