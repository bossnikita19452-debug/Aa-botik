import asyncio
import logging
from datetime import datetime

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import (
    TELEGRAM_BOT_TOKEN, SCAN_INTERVAL_MINUTES,
    SCALP_ENABLED, SWING_ENABLED, LONGTERM_ENABLED,
    GROQ_MODEL,
)
from scanner import scan_all
from news_scanner import get_bitcoin_news, get_global_crypto_news
from ai_analyzer import client as ai_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(
    token=TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

MY_CHAT_ID = 396041420  # ← ваш ID

sent_signals: dict = {}

settings = {
    "scalp": SCALP_ENABLED,
    "swing": SWING_ENABLED,
    "longterm": LONGTERM_ENABLED,
}


def confidence_emoji(conf: str) -> str:
    return {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(conf, "⚪")


def format_signal(s: dict) -> str:
    emoji = confidence_emoji(s["confidence"])
    return (
        f"{emoji} <b>LONG SIGNAL | BingX</b>\n\n"
        f"💎 Монета: <code>{s['symbol']}</code>\n"
        f"📊 Тип: {s['type_label']}\n"
        f"📈 Таймфрейм: {s['timeframe']}\n\n"
        f"💰 Вход: <code>{s['entry']}</code>\n"
        f"🎯 Take Profit: <code>{s['tp']}</code>\n"
        f"🛑 Stop Loss: <code>{s['sl']}</code>\n"
        f"⚖️ RR: <b>1:{s['rr']}</b>\n\n"
        f"📊 RSI: {s['rsi']}\n"
        f"🧠 Уверенность: <b>{s['confidence']}</b>\n\n"
        f"💬 {s['reason']}\n"
        f"⚠️ {s['risk_note']}"
    )


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🪙 Биткоин дня", callback_data="btc_day")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton(text="📰 Новости рынка", callback_data="news")],
        [InlineKeyboardButton(text="🔄 Обновить сканирование", callback_data="rescan")],
    ])


def settings_menu() -> InlineKeyboardMarkup:
    def label(name: str, key: str) -> str:
        return f"{'✅' if settings[key] else '❌'} {name}"

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label("Скальп", "scalp"), callback_data="toggle_scalp")],
        [InlineKeyboardButton(text=label("Среднесрок", "swing"), callback_data="toggle_swing")],
        [InlineKeyboardButton(text=label("Долгосрок", "longterm"), callback_data="toggle_longterm")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")],
    ])


@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "🤖 <b>AI Crypto Scanner</b>\n\n"
        "Я анализирую рынок каждые 15 минут:\n"
        logger "• Технические индикаторы BingX\n"
        "• Новости по монетам\n"
        "• ИИ-анализ через Groq\n\n"
        "Выберите действие:",
        reply_markup=main_menu(),
    )


@dp.callback_query(F.data == "back_main")
async def cb_back_main(call: CallbackQuery):
    try:
        await call.message.edit_text(
            "🤖 <b>AI Crypto Scanner</b>\n\nВыберите действие:",
            reply_markup=main_menu(),
        )
    except TelegramBadRequest:
        pass
    await call.answer()


@dp.callback_query(F.data == "settings")
async def cb_settings(call: CallbackQuery):
    try:
        await.error call.message.edit_text(
            "⚙️ <b>Настройки типов(f сделок</b>",
            reply_markup=settings_menu(),
        )
    exceptО TelegramBadRequest:
        pass
    await call.answer()


шиб@dp.callback_query(F.data.startswith("toggle_"))
async def cb_toggle(call: CallbackQuery):
    key = call.data.replace("toggle_", "")
    if key in settings:
        settings[key] = not settings[key]
    try:
        await call.message.edit_reply_markup(reply_markup=settings_menu())
    except TelegramBadRequest:
        pass
    await call.answer(f"{key}: {'вкл' if settings[key] else 'выкл'}")


@dp.callback_query(F.data == "stats")
async def cb_stats(call: CallbackQuery):
    total = len(sent_signals)
    try:
        await call.message.edit_text(
            f"📊 <b>Статистика</b>\n\n"
            f"Отправлено сигналов (текущая сессия): <b>{total}</b>\n"
            f"Последнее сканирование: <b>{datetime.now().strftime('%H:%M')}</b>",
            reply_markup=main_menu(),
        )
    except TelegramBadRequest:
        pass
    await call.answer()


@dp.callback_query(F.data == "news")
async def cb_news(call: CallbackQuery):
    await call.answer("Загружаю новости...")
    async with aiohttp.ClientSession() as session:
        news = await get_global_crypto_news(session, limit=5)
    text = "📰 <b>Последние новости крипторынка</b>\n\n" + "\n".join(f"• {n}" for n in news) if news else "Новости не найдены."
    try:
        await call.message.edit_text(text, reply_markup=main_menu())
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data == "btc_day")
async def cb_btc_day(call: CallbackQuery):
    await call.answer("Анализирую BTC...")
    async with aiohttp.ClientSession() as session:
        news = await get_bitcoin_news(session, limit=8)

    prompt = (
        "Ты крипто-аналитик. На основе этих новостей по BTC сделай краткий прогноз "
        "на сегодня на русском (3-4 предложения). Что можно ждать от биткоина: рост, "
        "падение или боковик? Какие риски?\n\nНовости:\n" + "\n".join(f"- {n}" for n in news)
    )

    try:
        response = await ai_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=400,
        )
        answer = response.choices[0].message.content
    except Exception as e:
        answer = f"Ошибка анализа: {e}"

    try:
        await call.message.edit_text(
            f"🪙 <b>Биткоин дня</b>\n\n{answer}",
            reply_markup=main_menu(),
        )
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data == "rescan")
async def cb_rescan(call: CallbackQuery):
    await call.answer("Запускаю сканирование...")
    try:
        await call.message.edit_text(
            "🔄 Сканирование запущено. Результат придёт отдельным сообщением.",
            reply_markup=main_menu(),
        )
    except TelegramBadRequest:
        pass
    asyncio.create_task(run_scan())


async def run_scan():
    logger.info(f"Начинаю сканирование: {datetime.now()}")
    try:
        signals = await scan_all()
        logger.info(f"Найдено сигналов: {len(signals)}")

        for s in signals:
            if s["type"] in settings and not settings[s["type"]]:
                continue

            key = (s["symbol"], s["type"])
            text = format_signal(s)

            if key in sent_signals:
                old = sent_signals[key]
                if old["confidence"] != s["confidence"]:
                    try:
                        await bot.edit_message_text(
                            chat_id=MY_CHAT_ID,
                            message_id=old["message_id"],
                            text="🔄 <b>Сигнал обновлён</b>\n\n" + text,
                        )
                        sent_signals[key]["confidence"] = s["confidence"]
                    except Exception as e:
                        logger.error(f"Edit error: {e}")
                continue

            try:
                msg = await bot.send_message(MY_CHAT_ID, text)
                sent_signals[key] = {
                    "message_id": msg.message_id,
                    "confidence": s["confidence"],
                }
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Send error: {e}")

    except Exception as e:
       ка сканирования: {e}")


async def main():
    scheduler.add_job(run_scan, "interval", minutes=SCAN_INTERVAL_MINUTES)
    scheduler.start()

    asyncio.create_task(run_scan())

    logger.info("Бот запущен, ожидаю сообщений...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
