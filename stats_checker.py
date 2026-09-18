from datetime import datetime
import aiohttp

from database import get_active_signals, update_signal_status
from config import BYBIT_KLINE_URL, BYBIT_CATEGORY, TIMEFRAME

_bot = None


def set_bot(bot):
    global _bot
    _bot = bot


async def _get_current_prices(session, symbols: list) -> dict:
    """Получить последние цены для списка монет через Bybit tickers."""
    url = "https://api.bybit.com/v5/market/tickers"
    params = {"category": BYBIT_CATEGORY}
    prices = {}
    try:
        async with session.get(url, params=params, timeout=15) as resp:
            if resp.status != 200:
                return {}
            data = await resp.json()
    except Exception as e:
        print(f"Ошибка цен: {e}")
        return {}

    if data.get("retCode") != 0:
        return {}

    for item in data.get("result", {}).get("list", []):
        sym = item.get("symbol")
        if sym in symbols:
            try:
                prices[sym] = float(item.get("lastPrice", 0))
            except (TypeError, ValueError):
                continue
    return prices


async def _get_current_bar_index(session, symbol: str) -> int:
    """Получить индекс текущей свечи M15 (для подсчёта bars_held)."""
    params = {
        "category": BYBIT_CATEGORY,
        "symbol": symbol,
        "interval": TIMEFRAME,
        "limit": 1,
    }
    try:
        async with session.get(BYBIT_KLINE_URL, params=params, timeout=10) as resp:
            if resp.status != 200:
                return 0
            data = await resp.json()
    except Exception:
        return 0

    if data.get("retCode") != 0:
        return 0
    rows = data.get("result", {}).get("list", [])
    if not rows:
        return 0
    return int(rows[0][0])


async def _notify(chat_id, text: str):
    if _bot is None or not chat_id:
        return
    try:
        await _bot.send_message(chat_id, text, parse_mode="HTML")
    except Exception as e:
        print(f"Ошибка уведомления: {e}")


async def check_open_signals(chat_id=None):
    """Проверить все активные сделки и обновить статусы."""
    signals = get_active_signals(limit=100)
    if not signals:
        return

    symbols = list({s[1] for s in signals})

    async with aiohttp.ClientSession() as session:
        prices = await _get_current_prices(session, symbols)
        if not prices:
            print("⚠️ Не удалось получить цены")
            return

        now_ts = int(datetime.utcnow().timestamp() * 1000)
        bar_duration_ms = 15 * 60 * 1000  # 15 минут в мс

        for s in signals:
            # Индексы таблицы signals:
            # 0=id, 1=symbol, 2=direction, 3=entry, 4=stop, 5=take,
            # 6=risk_distance, 7=atr, 8=created_at, 9=status,
            # 10=result_price, 11=closed_at, 12=bars_held
            sig_id = s[0]
            symbol = s[1]
            direction = s[2]
            entry = s[3]
            stop = s[4]
            take = s[5]
            created_at_str = s[8]

            current = prices.get(symbol)
            if not current:
                continue

            # Считаем bars_held
            try:
                created_ts = int(
                    datetime.fromisoformat(created_at_str).timestamp() * 1000
                )
            except Exception:
                created_ts = now_ts
            bars_held = max(0, int((now_ts - created_ts) / bar_duration_ms))

            # ─── LONG ─────────────────────────────────────────────
            if direction == "LONG":
                if current >= take:
                    update_signal_status(sig_id, "win", current, bars_held)
                    profit_pct = (current - entry) / entry * 100
                    await _notify(
                        chat_id,
                        f"✅ <b>ТЕЙК ПРОФИТ (LONG)</b>\n\n"
                        f"{symbol}\n"
                        f"Вход: <code>{entry:.6f}</code>\n"
                        f"Тейк: <code>{take:.6f}</code>\n"
                        f"Цена: <code>{current:.6f}</code>\n"
                        f"Профит: <b>+{profit_pct:.2f}%</b>"
                    )
                    continue

                if current <= stop:
                    update_signal_status(sig_id, "loss", current, bars_held)
                    loss_pct = (current - entry) / entry * 100
                    await _notify(
                        chat_id,
                        f"❌ <b>СТОП ЛОСС (LONG)</b>\n\n"
                        f"{symbol}\n"
                        f"Вход: <code>{entry:.6f}</code>\n"
                        f"Стоп: <code>{stop:.6f}</code>\n"
                        f"Цена: <code>{current:.6f}</code>\n"
                        f"Убыток: <b>{loss_pct:.2f}%</b>"
                    )
                    continue

            # ─── SHORT ────────────────────────────────────────────
            elif direction == "SHORT":
                if current <= take:
                    update_signal_status(sig_id, "win", current, bars_held)
                    profit_pct = (entry - current) / entry * 100
                    await _notify(
                        chat_id,
                        f"✅ <b>ТЕЙК ПРОФИТ (SHORT)</b>\n\n"
                        f"{symbol}\n"
                        f"Вход: <code>{entry:.6f}</code>\n"
                        f"Тейк: <code>{take:.6f}</code>\n"
                        f"Цена: <code>{current:.6f}</code>\n"
                        f"Профит: <b>+{profit_pct:.2f}%</b>"
                    )
                    continue

                if current >= stop:
                    update_signal_status(sig_id, "loss", current, bars_held)
                    loss_pct = (entry - current) / entry * 100
                    await _notify(
                        chat_id,
                        f"❌ <b>СТОП ЛОСС (SHORT)</b>\n\n"
                        f"{symbol}\n"
                        f"Вход: <code>{entry:.6f}</code>\n"
                        f"Стоп: <code>{stop:.6f}</code>\n"
                        f"Цена: <code>{current:.6f}</code>\n"
                        f"Убыток: <b>{loss_pct:.2f}%</b>"
                    )
                    continue

            # ─── Таймаут 16 свечей ────────────────────────────────
            if bars_held >= 16:
                update_signal_status(sig_id, "expired", current, bars_held)
                await _notify(
                    chat_id,
                    f"⏰ <b>ТАЙМАУТ (16 свечей)</b>\n\n"
                    f"{symbol} | {direction}\n"
                    f"Вход: <code>{entry:.6f}</code>\n"
                    f"Цена: <code>{current:.6f}</code>\n"
                    f"Закрыто по рынку"
                )
                continue
