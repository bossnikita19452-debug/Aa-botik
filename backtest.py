#!/usr/bin/env python3
"""
Подробный бэктест стратегии Aa-botik (Climax / L_Long / Bull_Impulse)
На 5-минутках Bybit за последние 30 дней.
"""

import time
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Optional

# ═══════════════════════════════════════════════════════════════
# КОНФИГ (точно как в твоём config.py)
# ═══════════════════════════════════════════════════════════════
TIMEFRAME = "5"
EMA_FAST, EMA_MID, EMA_SLOW, EMA_TREND = 9, 21, 50, 200
VOL_SMA_FAST, VOL_SMA_SLOW = 12, 20
ATR_FAST, ATR_SLOW = 10, 14
RSI_FAST, RSI_SLOW = 5, 14

RR_CLIMAX = 1.35
RR_L_LONG = 1.25
RR_BULL_IMPULSE = 1.30

MIN_RISK_PCT = 0.20
MAX_RISK_PCT = 2.00
MAX_HOLD_BARS = 12          # 60 минут
RISK_PER_TRADE_PCT = 1.0    # риск на сделку в % от депозита

COINS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "LINKUSDT", "AVAXUSDT", "ADAUSDT", "LTCUSDT", "DOGEUSDT",
    "DOTUSDT", "NEARUSDT",
]

BYBIT_KLINE_URL = "https://api.bybit.com/v5/market/kline"
BYBIT_CATEGORY = "linear"
MSK = timezone(timedelta(hours=3))


# ═══════════════════════════════════════════════════════════════
# ИНДИКАТОРЫ И МОДУЛИ (1-в-1 из scanner.py)
# ═══════════════════════════════════════════════════════════════
def in_session(dt: datetime) -> bool:
    msk = dt.astimezone(MSK)
    return msk.weekday() in (0, 1, 2, 3, 4) and 10 <= msk.hour < 23


def fetch_klines(symbol: str, start_ms: int, end_ms: int) -> list:
    all_rows = []
    current_end = end_ms
    while True:
        params = {
            "category": BYBIT_CATEGORY,
            "symbol": symbol,
            "interval": TIMEFRAME,
            "end": current_end,
            "limit": 1000,
        }
        try:
            r = requests.get(BYBIT_KLINE_URL, params=params, timeout=30)
            if r.status_code != 200:
                print(f"  HTTP {r.status_code} {symbol}")
                break
            data = r.json()
        except Exception as e:
            print(f"  Error {symbol}: {e}")
            break

        if data.get("retCode") != 0:
            print(f"  API {symbol}: {data.get('retMsg')}")
            break

        rows = data.get("result", {}).get("list", [])
        if not rows:
            break

        for row in rows:
            ts = int(row[0])
            if ts < start_ms:
                all_rows.extend([r for r in rows if int(r[0]) >= start_ms])
                return list(reversed(all_rows))
            all_rows.append(row)

        oldest = int(rows[-1][0])
        if oldest <= start_ms:
            all_rows = [r for r in all_rows if int(r[0]) >= start_ms]
            return list(reversed(all_rows))

        current_end = oldest - 1
        time.sleep(0.12)

    return list(reversed(all_rows))


def rows_to_df(rows) -> Optional[pd.DataFrame]:
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume", "turnover"])
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["time"] = pd.to_numeric(df["time"])
    return df.dropna().reset_index(drop=True)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    c = df["close"]
    df["ema9"]  = c.ewm(span=EMA_FAST, adjust=False).mean()
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
    return MIN_RISK_PCT <= (risk / entry * 100) <= MAX_RISK_PCT


def mod_climax(row) -> Optional[dict]:
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
                "atr": atr, "module": "Climax", "rr": RR_CLIMAX}

    if row["rsi14"] >= 74 and row["upper_wick"] >= 0.58 * rng:
        entry = float(row["close"])
        sl = float(row["high"]) + 0.08 * atr
        if not _risk_ok(entry, sl):
            return None
        risk = sl - entry
        return {"direction": "SHORT", "entry": entry, "stop": sl,
                "take": entry - RR_CLIMAX * risk, "risk_distance": risk,
                "atr": atr, "module": "Climax", "rr": RR_CLIMAX}
    return None


def mod_l_long(row) -> Optional[dict]:
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
            "atr": atr, "module": "L_Long", "rr": RR_L_LONG}


def is_bull_regime(btc_row) -> bool:
    if btc_row is None or btc_row["close"] < btc_row["ema50"]:
        return False
    r12 = float(btc_row["ret_12"]) if not np.isnan(btc_row["ret_12"]) else 0
    return r12 > 0.004


def mod_bull_impulse(row, btc_row, breadth: float) -> Optional[dict]:
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
            "atr": atr, "module": "Bull_Impulse", "rr": RR_BULL_IMPULSE}


def check_signal(row, btc_row, breadth: float, bull: bool) -> Optional[dict]:
    for mod in (mod_climax, mod_l_long):
        sig = mod(row)
        if sig:
            return sig
    if bull:
        return mod_bull_impulse(row, btc_row, breadth)
    return None


def simulate_trade(df: pd.DataFrame, entry_idx: int, signal: dict) -> tuple[str, float, int]:
    """
    Возвращает (outcome, r_multiple, bars_held)
    r_multiple: +RR при тейке, -1 при стопе, 0 при таймауте
    """
    direction = signal["direction"]
    stop = signal["stop"]
    take = signal["take"]
    rr = signal["rr"]

    end_idx = min(entry_idx + 1 + MAX_HOLD_BARS, len(df))
    for i in range(entry_idx + 1, end_idx):
        high = df.iloc[i]["high"]
        low = df.iloc[i]["low"]
        bars = i - entry_idx

        if direction == "LONG":
            if low <= stop:
                return "loss", -1.0, bars
            if high >= take:
                return "win", rr, bars
        else:
            if high >= stop:
                return "loss", -1.0, bars
            if low <= take:
                return "win", rr, bars

    # expired — закрываем по цене закрытия последней свечи
    last_close = df.iloc[end_idx - 1]["close"]
    entry = signal["entry"]
    if direction == "LONG":
        r = (last_close - entry) / signal["risk_distance"]
    else:
        r = (entry - last_close) / signal["risk_distance"]
    return "expired", r, MAX_HOLD_BARS


# ═══════════════════════════════════════════════════════════════
# ОСНОВНОЙ БЭКТЕСТ
# ═══════════════════════════════════════════════════════════════
def run_backtest(days: int = 30):
    now = datetime.now(timezone.utc)
    end_ms = int(now.timestamp() * 1000)
    start_ms = int((now - timedelta(days=days + 7)).timestamp() * 1000)

    print("=" * 70)
    print("БЭКТЕСТ СТРАТЕГИИ Aa-botik")
    print(f"Период: {days} дней + прогрев индикаторов")
    print(f"Монеты: {len(COINS)} | Таймфрейм: 5m | Сессия: Пн-Пт 10-23 МСК")
    print("=" * 70)

    # ── Загрузка данных ──
    dfs = {}
    for sym in COINS:
        print(f"  {sym}...", end=" ", flush=True)
        rows = fetch_klines(sym, start_ms, end_ms)
        df = rows_to_df(rows)
        if df is not None and len(df) > 250:
            dfs[sym] = add_indicators(df)
            print(f"{len(df)} баров")
        else:
            print("ОШИБКА")
        time.sleep(0.15)

    if "BTCUSDT" not in dfs:
        print("\n❌ Нет данных BTC. Проверь интернет / API.")
        return

    print(f"\n✅ Загружено {len(dfs)} монет. Генерация сигналов...")

    results = []
    btc_df = dfs["BTCUSDT"]
    start_i = 220

    for i in range(start_i, len(btc_df) - MAX_HOLD_BARS - 2):
        btc_row = btc_df.iloc[i]
        ts = int(btc_row["time"])
        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)

        if not in_session(dt):
            continue

        # Breadth
        green = total = 0
        for sym, df in dfs.items():
            idx = df["time"].searchsorted(ts)
            if idx >= len(df):
                idx = len(df) - 1
            if abs(df.iloc[idx]["time"] - ts) > 300_000:
                continue
            total += 1
            if df.iloc[idx]["ret_1"] > 0:
                green += 1
        breadth = green / total if total else 0
        bull = is_bull_regime(btc_row)

        for sym, df in dfs.items():
            idx = df["time"].searchsorted(ts)
            if idx >= len(df):
                idx = len(df) - 1
            if abs(df.iloc[idx]["time"] - ts) > 300_000:
                continue
            if idx < 220 or idx + MAX_HOLD_BARS + 2 >= len(df):
                continue

            row = df.iloc[idx]
            sig = check_signal(row, btc_row, breadth, bull)
            if not sig:
                continue

            outcome, r_mult, bars_held = simulate_trade(df, idx, sig)
            risk_pct = sig["risk_distance"] / sig["entry"] * 100

            results.append({
                "time": dt,
                "date": dt.date(),
                "weekday": dt.strftime("%a"),
                "hour_msk": dt.astimezone(MSK).hour,
                "symbol": sym,
                "direction": sig["direction"],
                "module": sig["module"],
                "entry": sig["entry"],
                "stop": sig["stop"],
                "take": sig["take"],
                "rr": sig["rr"],
                "risk_pct": risk_pct,
                "outcome": outcome,
                "r_multiple": r_mult,
                "bars_held": bars_held,
                "pnl_pct": r_mult * RISK_PER_TRADE_PCT,  # в % от депозита
            })

    if not results:
        print("\n⚠️ За период не найдено ни одного сигнала.")
        return

    # ═══════════════════════════════════════════════════════════
    # ОТЧЁТ
    # ═══════════════════════════════════════════════════════════
    df = pd.DataFrame(results)
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    def print_stats(sub: pd.DataFrame, title: str):
        if sub.empty:
            print(f"\n{'='*70}\n{title}\n{'='*70}")
            print("Сделок: 0")
            return

        total = len(sub)
        wins = (sub["outcome"] == "win").sum()
        losses = (sub["outcome"] == "loss").sum()
        expired = (sub["outcome"] == "expired").sum()
        decided = wins + losses
        winrate = wins / decided * 100 if decided else 0

        avg_r = sub["r_multiple"].mean()
        median_r = sub["r_multiple"].median()
        sum_r = sub["r_multiple"].sum()
        expectancy = avg_r  # средний R на сделку

        gross_profit = sub.loc[sub["r_multiple"] > 0, "r_multiple"].sum()
        gross_loss = abs(sub.loc[sub["r_multiple"] < 0, "r_multiple"].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Симуляция эквити (риск 1% на сделку)
        equity = [100.0]
        for pnl in sub["pnl_pct"]:
            equity.append(equity[-1] * (1 + pnl / 100))
        equity = np.array(equity)
        max_dd = 0
        peak = equity[0]
        for e in equity:
            peak = max(peak, e)
            dd = (peak - e) / peak * 100
            max_dd = max(max_dd, dd)
        final_equity = equity[-1]
        total_return = final_equity - 100

        print(f"\n{'='*70}")
        print(f"{title}")
        print(f"{'='*70}")
        print(f"Всего сделок:          {total}")
        print(f"  ✅ Win:              {wins:4}  ({wins/total*100:5.1f}%)")
        print(f"  ❌ Loss:             {losses:4}  ({losses/total*100:5.1f}%)")
        print(f"  ⏰ Expired:          {expired:4}  ({expired/total*100:5.1f}%)")
        print(f"Винрейт (только W/L):  {winrate:.1f}%  ({wins}/{decided})")
        print()
        print(f"Средний R:             {avg_r:+.3f} R")
        print(f"Медианный R:           {median_r:+.3f} R")
        print(f"Суммарный R:           {sum_r:+.2f} R")
        print(f"Expectancy:            {expectancy:+.3f} R на сделку")
        print(f"Profit Factor:         {profit_factor:.2f}")
        print()
        print(f"Симуляция депозита (риск {RISK_PER_TRADE_PCT}% на сделку):")
        print(f"  Старт:               100.00%")
        print(f"  Финиш:               {final_equity:.2f}%")
        print(f"  Доходность:          {total_return:+.2f}%")
        print(f"  Макс. просадка:      {max_dd:.2f}%")

        # По модулям
        print(f"\n{'─'*50}")
        print("ПО МОДУЛЯМ:")
        print(f"{'Модуль':<16} {'Всего':>6} {'Win':>5} {'Loss':>5} {'Exp':>5} {'WR%':>6} {'Avg R':>8} {'Sum R':>8}")
        for mod in ["Climax", "L_Long", "Bull_Impulse"]:
            m = sub[sub["module"] == mod]
            if m.empty:
                continue
            w = (m["outcome"] == "win").sum()
            l = (m["outcome"] == "loss").sum()
            e = (m["outcome"] == "expired").sum()
            wr = w / (w + l) * 100 if (w + l) else 0
            print(f"{mod:<16} {len(m):6} {w:5} {l:5} {e:5} {wr:5.1f}% {m['r_multiple'].mean():+7.3f} {m['r_multiple'].sum():+7.2f}")

        # По направлению
        print(f"\n{'─'*50}")
        print("ПО НАПРАВЛЕНИЮ:")
        for d in ["LONG", "SHORT"]:
            m = sub[sub["direction"] == d]
            if m.empty:
                continue
            w = (m["outcome"] == "win").sum()
            l = (m["outcome"] == "loss").sum()
            wr = w / (w + l) * 100 if (w + l) else 0
            print(f"  {d:<6}  total={len(m):3}  W={w:3}  L={l:3}  WR={wr:5.1f}%  AvgR={m['r_multiple'].mean():+.3f}")

        # По монетам (топ)
        print(f"\n{'─'*50}")
        print("ПО МОНЕТАМ (сортировка по Sum R):")
        coin_stats = []
        for sym in sub["symbol"].unique():
            m = sub[sub["symbol"] == sym]
            coin_stats.append((sym, len(m), m["r_multiple"].sum(), m["r_multiple"].mean()))
        coin_stats.sort(key=lambda x: x[2], reverse=True)
        print(f"{'Монета':<12} {'Сделок':>7} {'Sum R':>9} {'Avg R':>8}")
        for sym, cnt, s_r, a_r in coin_stats:
            print(f"{sym:<12} {cnt:7} {s_r:+9.2f} {a_r:+8.3f}")

        # По дням недели
        print(f"\n{'─'*50}")
        print("ПО ДНЯМ НЕДЕЛИ:")
        for day in ["Mon", "Tue", "Wed", "Thu", "Fri"]:
            m = sub[sub["weekday"] == day]
            if m.empty:
                continue
            print(f"  {day}: {len(m):3} сделок | AvgR={m['r_multiple'].mean():+.3f} | SumR={m['r_multiple'].sum():+.2f}")

        # Среднее время удержания
        print(f"\n{'─'*50}")
        print(f"Среднее удержание:     {sub['bars_held'].mean():.1f} свечей ({sub['bars_held'].mean()*5:.0f} мин)")
        print(f"Медиана удержания:     {sub['bars_held'].median():.0f} свечей")

    # ── Вывод ──
    print_stats(df[df["time"] >= week_ago], "ПРОШЛАЯ НЕДЕЛЯ (7 дней)")
    print_stats(df[df["time"] >= month_ago], "ПРОШЛЫЙ МЕСЯЦ (30 дней)")

    # Последние 15 сигналов
    print(f"\n{'='*70}")
    print("ПОСЛЕДНИЕ 15 СИГНАЛОВ")
    print(f"{'='*70}")
    print(f"{'Дата/время UTC':<18} {'Монета':<11} {'Dir':<6} {'Модуль':<13} {'R':>6} {'Исход':<8} {'Бары'}")
    for _, t in df.sort_values("time").tail(15).iterrows():
        print(f"{t['time'].strftime('%Y-%m-%d %H:%M'):<18} {t['symbol']:<11} {t['direction']:<6} "
              f"{t['module']:<13} {t['r_multiple']:+5.2f} {t['outcome']:<8} {t['bars_held']}")

    print(f"\n{'='*70}")
    print("Готово.")
    print("=" * 70)


if __name__ == "__main__":
    run_backtest(days=30)
