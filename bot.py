import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
from config import TELEGRAM_BOT_TOKEN, ADMIN_IDS, CHANNEL_ID, SCAN_INTERVAL_MINUTES, CHECK_INTERVAL_SECONDS
from database import (
    init_db, get_active_signals, get_recent_signals,
    get_stats, count_open_positions,
)
from scanner import scan_once, in_session
from stats_checker import check_open_signals, set_bot

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Последние сигналы", callback_data="last_signals")],
        [InlineKeyboardButton("📈 Статистика", callback_data="stats")],
        [InlineKeyboardButton("⚙️ Панель управления", callback_data="admin_panel")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = "✅ в сессии" if in_session() else "⏸ вне сессии"
    await update.message.reply_text(
        "🤖 <b>Quality Bot 5m</b>\n\n"
        "Модули: <b>Climax</b> → <b>L_Long</b> → <b>Bull_Impulse</b>\n"
        "Таймфрейм: <b>5m</b>\n"
        "Сессия: <b>Пн–Пт 10:00–23:00 МСК</b>\n"
        f"Сейчас: {session}\n\n"
        "Цель: WR ~58%, ~9 сделок/день\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=main_menu()
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "last_signals":
        signals = get_recent_signals(10)
        if not signals:
            await query.edit_message_text("Пока нет сигналов.", reply_markup=main_menu())
            return
        status_map = {"win": "✅", "loss": "❌", "expired": "⏰", "active": "⏳"}
        text = "<b>Последние 10 сигналов:</b>\n\n"
        for s in signals:
            # 0=id, 1=symbol, 2=direction, 3=entry, 4=stop, 5=take, ...
            emoji = status_map.get(s[9], "⚪")
            dir_emoji = "🟢" if s[2] == "LONG" else "🔴"
            text += f"{emoji} {dir_emoji} {s[1]} | Entry {s[3]:.4f}\n"
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=main_menu())

    elif data == "stats":
        st = get_stats()
        closed = st["win"] + st["loss"]
        winrate = round(st["win"] / closed * 100, 1) if closed > 0 else 0.0

        long_closed = st["long_win"] + st["long_loss"]
        short_closed = st["short_win"] + st["short_loss"]
        long_wr = round(st["long_win"] / long_closed * 100, 1) if long_closed > 0 else 0.0
        short_wr = round(st["short_win"] / short_closed * 100, 1) if short_closed > 0 else 0.0

        open_now = count_open_positions()

        text = (
            f"📈 <b>Статистика Quality 5m</b>\n\n"
            f"Всего сигналов: <b>{st['total']}</b>\n"
            f"✅ TP: <b>{st['win']}</b>\n"
            f"❌ SL: <b>{st['loss']}</b>\n"
            f"⏰ Таймаут: <b>{st['expired']}</b>\n"
            f"⏳ Открыто сейчас: <b>{open_now}</b>\n\n"
            f"<b>Winrate общий: {winrate}%</b>\n\n"
            f"🟢 LONG: {long_wr}% ({st['long_win']}/{long_closed})\n"
            f"🔴 SHORT: {short_wr}% ({st['short_win']}/{short_closed})\n\n"
            f"Сессия: Пн–Пт 10:00–23:00 МСК\n"
            f"Модули: Climax · L_Long · Bull_Impulse"
        )
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=main_menu())

    elif data == "admin_panel":
        if user_id not in ADMIN_IDS:
            await query.edit_message_text("Доступ запрещён.")
            return
        status = "▶️ Активно" if config.SCANNING_ENABLED else "⏸ Остановлено"
        toggle_text = "⏸ Остановить сканер" if config.SCANNING_ENABLED else "▶️ Возобновить сканер"
        sess = "✅ в сессии" if in_session() else "⏸ вне сессии"
        keyboard = [
            [InlineKeyboardButton(f"Сканер: {status}", callback_data="noop")],
            [InlineKeyboardButton(f"Сессия: {sess}", callback_data="noop")],
            [InlineKeyboardButton(toggle_text, callback_data="toggle_scan")],
            [InlineKeyboardButton("🔄 Сканировать сейчас", callback_data="force_scan")],
            [InlineKeyboardButton("🔍 Проверить позиции", callback_data="check_trades")],
            [InlineKeyboardButton("« Назад", callback_data="back_main")],
        ]
        await query.edit_message_text(
            "⚙️ <b>Панель управления</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "toggle_scan":
        if user_id not in ADMIN_IDS:
            return
        config.SCANNING_ENABLED = not config.SCANNING_ENABLED
        status = "▶️ активно" if config.SCANNING_ENABLED else "⏸ остановлено"
        await query.answer(f"Сканирование {status}")
        status_label = "▶️ Активно" if config.SCANNING_ENABLED else "⏸ Остановлено"
        toggle_text = "⏸ Остановить сканер" if config.SCANNING_ENABLED else "▶️ Возобновить сканер"
        sess = "✅ в сессии" if in_session() else "⏸ вне сессии"
        keyboard = [
            [InlineKeyboardButton(f"Сканер: {status_label}", callback_data="noop")],
            [InlineKeyboardButton(f"Сессия: {sess}", callback_data="noop")],
            [InlineKeyboardButton(toggle_text, callback_data="toggle_scan")],
            [InlineKeyboardButton("🔄 Сканировать сейчас", callback_data="force_scan")],
            [InlineKeyboardButton("🔍 Проверить позиции", callback_data="check_trades")],
            [InlineKeyboardButton("« Назад", callback_data="back_main")],
        ]
        await query.edit_message_text(
            "⚙️ <b>Панель управления</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "noop":
        await query.answer()

    elif data == "force_scan":
        if user_id not in ADMIN_IDS:
            return
        await query.edit_message_text("🔄 Сканирую...")
        await scan_once(context.bot)
        await query.edit_message_text("✅ Сканирование завершено.", reply_markup=main_menu())

    elif data == "check_trades":
        if user_id not in ADMIN_IDS:
            return
        await query.edit_message_text("🔍 Проверяю позиции...")
        await check_open_signals(chat_id=CHANNEL_ID)
        await query.edit_message_text("✅ Проверка завершена.", reply_markup=main_menu())

    elif data == "back_main":
        await query.edit_message_text(
            "Выберите действие:",
            reply_markup=main_menu()
        )


async def main():
    init_db()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    set_bot(app.bot)

    scheduler = AsyncIOScheduler()
    # Сканирование каждые 5 минут (закрытие 5m свечи)
    scheduler.add_job(scan_once, "interval", minutes=SCAN_INTERVAL_MINUTES, args=[app.bot])
    # Проверка TP/SL
    scheduler.add_job(
        check_open_signals, "interval", seconds=CHECK_INTERVAL_SECONDS,
        kwargs={"chat_id": CHANNEL_ID}
    )
    scheduler.start()

    logger.info("Quality Bot 5m запускается...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")
