import asyncio
import hashlib
import hmac
import time

import aiohttp
import pandas as pd

from config import (
    BINGX_API_KEY, BINGX_SECRET_KEY, BINGX_BASE_URL,
    MIN_VOLUME_USDT, MIN_RR, MAX_RR,
    SCALP_ENABLED, SWING_ENABLED, LONGTERM_ENABLED,
)
from indicators import calculate_ema, calculate_rsi, calculate_macd
from news_scanner import get_news_for_coin
from ai_analyzer import analyze_setup
from risk_calculator import calculate_tp_sl, is_rr_valid


def _sign(params: str) -> str:
    return hmac.new(
        BINGX_SECRET_KEY.encode("utf-8"),
        params.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def fetch_signed(session: aiohttp.ClientSession, endpoint: str, params: dict) -> dict:
    params["timestamp"] = int(time.time() * 1000)
    sorted_params = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if v is not None)
    signature = _sign(sorted_params)
    url = f"{BINGX_BASE_URL}{endpoint}?{sorted_params}&signature={signature}"
    headers = {"X-BX-APIKEY": BINGX_API_KEY}
    async with session.get(url, headers=headers) as resp:
        return await resp.json()


async def get_all_futures_symbols(session: aiohttp.ClientSession) -> list[str]:
    data = await fetch_signed(session, "/openApi/swap/v2/quote/contracts", {})
    return [
        item.get("symbol", "")
        for item in data.get("data", [])
        if item.get("symbol", "").endswith("-USDT") and item.get("status") == 1
    ]


async def get_klines(session: aiohttp.ClientSession, symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
    data = await fetch_signed(
        session,
        "/openApi/swap/v3/quote/klines",
        {"symbol": symbol, "interval": interval, "limit": limit},
    )
    rows = data.get("data", [])
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["open_time", "open", "high", "low", "close", "volume", "close_time"])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna()


def check_scalp(df_5m, df_15m):
    if len(df_5m) < 100 or len(df_15m) < 30:
        return None
    close = df_5m["close"].iloc[-1]
    ema50 = calculate_ema(df_5m, 50).iloc[-1]
    ema100 = calculate_ema(df_5m, 100).iloc[-1]
    rsi = calculate_rsi(df_15m, 14).iloc[-1]
    _, _, macd_hist = calculate_macd(df_15m)
    macd_pos = macd_hist.iloc[-1] > 0

    conditions = [close > ema50, close > ema100, rsi > 50, macd_pos]
    met = sum(conditions)
    if met < 3:
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
        close > ema200,
        50 <= rsi <= 65,
        macd_pos,
        df_4h["close"].iloc[-1] > df_4h["close"].iloc[-2],
    ]
    met = sum(conditions)
    if met < 3:
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
        close > ema200,
        50 <= rsi <= 70,
        df_1d["close"].iloc[-1] > df_1d["close"].iloc[-5],
    ]
    met = sum(conditions)
    if met < 2:
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
    async with aiohttp.ClientSession() as session:
        symbols = await get_all_futures_symbols(session)

        for symbol in symbols:
            try:
                df_5m = await get_klines(session, symbol, "5m", 100)
                df_15m = await get_klines(session, symbol, "15m", 100)
                df_1h = await get_klines(session, symbol, "1h", 250)
                df_4h = await get_klines(session, symbol, "4h", 100)
                df_1d = await get_klines(session, symbol, "1d", 250)

                if df_5m.empty or df_1h.empty or df_1d.empty:
                    continue

                volume_24h = df_1h["volume"].tail(24).sum() * df_1h["close"].iloc[-1]
                if volume_24h < MIN_VOLUME_USDT:
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
                    continue

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
                print(f"Error scanning {symbol}: {e}")
                continue

    conf_order = {"high": 0, "medium": 1, "low": 2}
    signals.sort(key=lambda s: conf_order.get(s["confidence"], 3))
    return signals
