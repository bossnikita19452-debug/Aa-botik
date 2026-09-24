"""
Golden Scanner Bot — Telegram + скан + SL/TP мониторинг.
Запуск: python main_golden.py
"""
from __future__ import annotations

import asyncio
import configparser
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from core.data import fetch_klines
from core.exchange import ExchangeClient
from core.indicators import add_common_indicators
from core.pairs import PAIRS_BY_STRATEGY, pairs_for_phase
from core.phase import MarketPhase, active_strategies, detect_btc_phase
from strategies.brk_long import scan_brk_long
from strategies.brk_short import scan_brk_short
from strategies.mr_long import scan_mr_long
from strategies.mr_short import scan_mr_short
from storage.db import (
    close_trade,
    count_open,
    get_open_trades,
    get_recent_trades,
    get_state,
    get_stats,
    has_open,
    init_db,
    is_scanning_enabled,
    save_open_trade,
    set_scanning_enabled,
    set_state,
)
from bot.telegram_notify import TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("golden")

CONFIG_PATH = Path(__file__).resolve().parent / "config.ini"

_bot = None


def load_config():
    """Загружает config.ini + ENV variables (Railway)."""
    cfg = configparser.ConfigParser()
    cfg.read_dict({
        "API": {"binance_key": "", "binance_secret": "", "testnet": "True"},
        "TELEGRAM": {"token": "", "chat_id": "", "admin_ids": ""},
        "RISK": {
            "risk_per_trade_pct": "1.0",
            "max_open_positions": "3",
            "circuit_breaker_losses": "5",
            "circuit_breaker_pause_minutes": "60",
        },
        "SCANNER": {
            "timeframe": "15m",
            "check_interval_minutes": "15",
            "position_check_seconds": "60",
        },
        "BRK": {
            "volume_mult": "2.5",
            "rsi_long_min": "55",
            "rsi_long_max": "70",
            "rsi_short_min": "30",
            "rsi_short_max": "45",
            "retest_bars": "8",
            "sl_atr_min": "0.3",
            "sl_atr_max": "1.5",
            "rr": "1.5",
            "time_stop_bars": "24",
        },
        "MR": {
            "rsi_long_max": "30",
            "rsi_short_min": "70",
            "atr_mult_max": "1.5",
            "sl_pct": "1.0",
            "time_stop_bars": "24",
        },
        "PHASE": {"ema_fast": "50", "ema_slow": "200", "adx_period": "14", "adx_min": "20"},
    })

    if CONFIG_PATH.exists():
        cfg.read(CONFIG_PATH, encoding="utf-8")
        logger.info("config.ini loaded")
    else:
        logger.warning("config.ini not found — using ENV / defaults")

    env_map = {
        ("TELEGRAM", "token"): "TELEGRAM_BOT_TOKEN",
        ("TELEGRAM", "chat_id"): "CHANNEL_ID",
        ("TELEGRAM", "admin_ids"): "ADMIN_IDS",
        ("API", "binance_key"): "BINANCE_KEY",
        ("API", "binance_secret"): "BINANCE_SECRET",
    }
    for (section, key), env_name in env_map.items():
        val = os.environ.get(env_name, "").strip()
        if val:
            if not cfg.has_section(section):
                cfg.add_section(section)
            cfg.set(section, key, val)
            logger.info("ENV %s -> [%s] %s", env_name, section, key)

    return cfg


def section_dict(cfg, name):
    if not cfg.has_section(name):
        return {}
    out = {}
    for k, v in cfg.items(name):
        try:
            if "." in str(v):
                out[k] = float(v)
            else:
                out[k] = int(v)
        except ValueError:
            out[k] = v
    return out


def main_menu(scanning=None):
    if scanning is None:
        scanning = is_scanning_enabled()
    scan_label = "Остановить сканер" if scanning else "Запустить сканер"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Статистика", callback_data="stats")],
        [InlineKeyboardButton("Последние сигналы", callback_data="last_signals")],
        [InlineKeyboardButton("Открытые позиции", callback_data="open_pos")],
        [InlineKeyboardButton(scan_label, callback_data="toggle_scan")],
        [InlineKeyboardButton("Сканировать сейчас", callback_data="force_scan")],
        [InlineKeyboardButton("Проверить SL/TP", callback_data="check_pos")],
    ])


class GoldenBot:
    def __init__(self):
        self.cfg = load_config()
        self.token = self.cfg.get("TELEGRAM", "token", fallback="").strip()
        self.chat_id = self.cfg.get("TELEGRAM", "chat_id", fallback="").strip()
        admin_raw = self.cfg.get("TELEGRAM", "admin_ids", fallback="")
        self.admin_ids = [int(x) for x in admin_raw.split(",") if x.strip().isdigit()]

        self.tg = TelegramNotifier(self.token, self.chat_id)
        testnet = self.cfg.getboolean("API", "testnet", fallback=True)
        self.ex = ExchangeClient(
            self.cfg.get("API", "binance_key", fallback=""),
            self.cfg.get("API", "binance_secret", fallback=""),
            testnet=testnet,
        )
        self.phase = MarketPhase.RANGE
        self.paused_until = 0.0
        self.consecutive_losses = 0
        self.tf = self.cfg.get("SCANNER", "timeframe", fallback="15m")
        self.risk_pct = self.cfg.getfloat("RISK", "risk_per_trade_pct", fallback=1.0)
        self.max_pos = self.cfg.getint("RISK", "max_open_positions", fallback=3)
        self.brk_cfg = section_dict(self.cfg, "BRK")
        self.mr_cfg = section_dict(self.cfg, "MR")
        self.phase_cfg = section_dict(self.cfg, "PHASE")
        self.paper = not bool(self.cfg.get("API", "binance_key", fallback="").strip())
        self._scan_lock = asyncio.Lock()

        self.last_signal_time = {}
        self.lock_bars = 8
        self.tf_seconds = 15 * 60

    def is_admin(self, user_id):
        if not self.admin_ids:
            return True
        return user_id in self.admin_ids

    def circuit_active(self):
        return time.time() < self.paused_until

    def trigger_circuit(self, reason):
        mins = self.cfg.getint("RISK", "circuit_breaker_pause_minutes", fallback=60)
        self.paused_until = time.time() + mins * 60
        self.tg.circuit_breaker(reason, mins)

    def update_phase(self):
        df = fetch_klines("BTCUSDT", interval="1d", limit=250, futures=True)
        if df is None:
            logger.error("BTC 1d load failed")
            return
        phase = detect_btc_phase(
            df,
            ema_fast=int(self.phase_cfg.get("ema_fast", 50)),
            ema_slow=int(self.phase_cfg.get("ema_slow", 200)),
            adx_period=int(self.phase_cfg.get("adx_period", 14)),
            adx_min=float(self.phase_cfg.get("adx_min", 20)),
        )
        if phase != self.phase:
            logger.info("Phase: %s -> %s", self.phase.value, phase.value)
            self.tg.phase(phase.value)
        self.phase = phase
        set_state("btc_phase", phase.value)

    def check_positions_sync(self):
        opens = get_open_trades()
        if not opens:
            return 0
        closed_n = 0
        for t in opens:
            symbol = t["symbol"]
            df = fetch_klines(symbol, interval=self.tf, limit=30, futures=True)
            if df is None or df.empty:
                continue
            last = df.iloc[-1]
            high = float(last["high"])
            low = float(last["low"])
            close = float(last["close"])
            entry = float(t["entry_price"])
            stop = float(t["stop_price"])
            take = float(t["take_price"])
            side = t["side"]
            qty = float(t["quantity"] or 0)
            risk = abs(entry - stop) or 1e-12

            exit_price = None
            reason = None

            if side == "LONG":
                if low <= stop:
                    exit_price = stop
                    reason = "SL"
                elif high >= take:
                    exit_price = take
                    reason = "TP"
            else:
                if high >= stop:
                    exit_price = stop
                    reason = "SL"
                elif low <= take:
                    exit_price = take
                    reason = "TP"

            try:
                entry_ts = datetime.fromisoformat(t["entry_time"].replace("Z", "+00:00"))
                if entry_ts.tzinfo is None:
                    entry_ts = entry_ts.replace(tzinfo=timezone.utc)
                hours = (datetime.now(timezone.utc) - entry_ts).total_seconds() / 3600
                if reason is None and hours >= 6:
                    exit_price = close
                    reason = "TIME"
            except Exception:
                pass

            if exit_price is None or reason is None:
                continue

            if side == "LONG":
                r_mult = (exit_price - entry) / risk
                pnl = (exit_price - entry) * qty
            else:
                r_mult = (entry - exit_price) / risk
                pnl = (entry - exit_price) * qty

            close_trade(int(t["id"]), exit_price, reason, round(r_mult, 3), round(pnl, 4))
            closed_n += 1

            if reason == "TP":
                self.tg.exit_tp(symbol, r_mult, pnl)
                self.consecutive_losses = 0
            elif reason == "SL":
                self.tg.exit_sl(symbol, r_mult, pnl)
                self.consecutive_losses += 1
                max_l = self.cfg.getint("RISK", "circuit_breaker_losses", fallback=5)
                if self.consecutive_losses >= max_l:
                    self.trigger_circuit(str(max_l) + " losses in a row")
                    self.consecutive_losses = 0
            else:
                self.tg.exit_time(symbol, r_mult, pnl)

            logger.info("CLOSED %s %s %s R=%.2f", symbol, reason, side, r_mult)
        return closed_n

    def scan_once_sync(self):
        if not is_scanning_enabled():
            logger.info("Scanner disabled")
            return 0
        if self.circuit_active():
            logger.info("Circuit breaker active")
            return 0

        open_n = count_open()
        if open_n >= self.max_pos:
            logger.info("Position limit %s/%s", open_n, self.max_pos)
            return 0

        strategies = active_strategies(self.phase)
        symbols = pairs_for_phase(self.phase.value)
        logger.info("Scan phase=%s strat=%s pairs=%s", self.phase.value, strategies, len(symbols))

        equity = 1000.0
        if not self.paper:
            try:
                self.ex.connect()
                equity = self.ex.fetch_balance() or 1000.0
            except Exception as e:
                self.tg.error(str(e))

        found = 0
        for symbol in symbols:
            if count_open() >= self.max_pos:
                break
            if has_open(symbol):
                continue

            now_utc = datetime.now(timezone.utc)
            last = self.last_signal_time.get(symbol)
            if last is not None:
                elapsed = (now_utc - last).total_seconds()
                lock_seconds = self.lock_bars * self.tf_seconds
                if elapsed < lock_seconds:
                    continue

            df = fetch_klines(symbol, interval=self.tf, limit=1000, futures=True)
            if df is None or len(df) < 80:
                continue
            df = add_common_indicators(df)

            sig = None
            if "BRK_LONG" in strategies and symbol in PAIRS_BY_STRATEGY["BRK_LONG"]:
                sig = scan_brk_long(df, symbol, self.brk_cfg)
            if sig is None and "BRK_SHORT" in strategies and symbol in PAIRS_BY_STRATEGY["BRK_SHORT"]:
                sig = scan_brk_short(df, symbol, self.brk_cfg)
            if sig is None and "MR_LONG" in strategies and symbol in PAIRS_BY_STRATEGY["MR_LONG"]:
                sig = scan_mr_long(df, symbol, self.mr_cfg)
            if sig is None and "MR_SHORT" in strategies and symbol in PAIRS_BY_STRATEGY["MR_SHORT"]:
                sig = scan_mr_short(df, symbol, self.mr_cfg)

            if sig is None:
                continue

            amount = self.ex.position_size(equity, self.risk_pct, sig.entry, sig.stop)
            if amount <= 0:
                amount = 1.0

            logger.info("SIGNAL %s %s %s", sig.strategy, sig.side, symbol)
            self.tg.entry(sig.side, symbol, sig.entry, sig.stop, sig.take, self.risk_pct, sig.strategy)

            opened = False

            if self.paper:
                save_open_trade(symbol, sig.strategy, sig.side, sig.entry, amount, sig.stop, sig.take)
                found += 1
                opened = True
            else:
                try:
                    res = self.ex.open_with_sl_tp(symbol, sig.side, amount, sig.stop, sig.take)
                    if res.get("entry"):
                        save_open_trade(symbol, sig.strategy, sig.side, sig.entry, amount, sig.stop, sig.take)
                        found += 1
                        opened = True
                    else:
                        self.tg.error("Order failed " + symbol)
                except Exception as e:
                    self.tg.error(str(e))

            if opened:
                self.last_signal_time[symbol] = datetime.now(timezone.utc)

            time.sleep(0.15)

        logger.info("Scan: new %s", found)
        return found


async def cmd_start(update, context):
    phase = get_state("btc_phase", "?")
    scanning = is_scanning_enabled()
    mode = "paper" if (_bot and _bot.paper) else "live"
    text = (
        "Golden Scanner\n\n"
        "Phase BTC: " + str(phase) + "\n"
        "Scanner: " + ("on" if scanning else "off") + "\n"
        "Mode: " + mode + "\n\n"
        "Choose action:"
    )
    await update.message.reply_text(text, reply_markup=main_menu(scanning))


async def on_button(update, context):
    global _bot
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id if query.from_user else 0

    if data == "stats":
        st = get_stats()
        lines = [
            "Statistics Golden Scanner\n",
            "Total: " + str(st["total"]),
            "Open: " + str(st["open"]),
            "TP: " + str(st["win"]),
            "SL: " + str(st["loss"]),
            "TIME: " + str(st["expired"]),
            "",
            "Winrate: " + str(st["wr"]) + "%",
            "LONG WR: " + str(st["long_wr"]) + "%",
            "SHORT WR: " + str(st["short_wr"]) + "%",
            "",
            "Total R: " + str(round(st["total_r"], 2)),
            "Total PnL: $" + str(round(st["total_pnl"], 2)),
            "",
            "Phase: " + str(get_state("btc_phase", "?")),
        ]
        await query.edit_message_text("\n".join(lines), reply_markup=main_menu())

    elif data == "last_signals":
        rows = get_recent_trades(10)
        if not rows:
            await query.edit_message_text("No trades yet.", reply_markup=main_menu())
            return
        reason_map = {"TP": "TP", "SL": "SL", "TIME": "TIME", None: "", "": ""}
        text = "Last 10:\n\n"
        for r in rows:
            if r["status"] == "open":
                mark = "OPEN"
            else:
                mark = reason_map.get(r.get("exit_reason"), "?")
            de = "LONG" if r["side"] == "LONG" else "SHORT"
            extra = ""
            if r["status"] == "closed" and r.get("r_multiple") is not None:
                extra = " | R " + str(round(r["r_multiple"], 2))
            text += mark + " " + de + " " + str(r["symbol"]) + " " + str(r["strategy"]) + extra + "\n"
        await query.edit_message_text(text, reply_markup=main_menu())

    elif data == "open_pos":
        rows = get_open_trades()
        if not rows:
            await query.edit_message_text("No open positions.", reply_markup=main_menu())
            return
        text = "Open:\n\n"
        for r in rows:
            de = "LONG" if r["side"] == "LONG" else "SHORT"
            text += de + " " + str(r["symbol"]) + " | " + str(r["strategy"]) + "\n"
        await query.edit_message_text(text, reply_markup=main_menu())

    elif data == "toggle_scan":
        if _bot and not _bot.is_admin(uid):
            await query.answer("No access", show_alert=True)
            return
        new_state = not is_scanning_enabled()
        set_scanning_enabled(new_state)
        await query.answer("Scanner on" if new_state else "Scanner off")
        phase = get_state("btc_phase", "?")
        text = "Golden Scanner\nScanner: " + ("on" if new_state else "off") + "\nPhase: " + str(phase)
        await query.edit_message_text(text, reply_markup=main_menu(new_state))

    elif data == "force_scan":
        if _bot and not _bot.is_admin(uid):
            await query.answer("No access", show_alert=True)
            return
        await query.edit_message_text("Scanning...")
        if _bot:
            n = await asyncio.to_thread(_bot.scan_once_sync)
            await query.edit_message_text("Scan done. New signals: " + str(n), reply_markup=main_menu())
        else:
            await query.edit_message_text("Bot not initialized", reply_markup=main_menu())

    elif data == "check_pos":
        await query.edit_message_text("Checking positions...")
        if _bot:
            n = await asyncio.to_thread(_bot.check_positions_sync)
            await query.edit_message_text("Check done. Closed: " + str(n), reply_markup=main_menu())
        else:
            await query.edit_message_text("Error", reply_markup=main_menu())


async def job_scan(context):
    if not _bot:
        return
    async with _bot._scan_lock:
        await asyncio.to_thread(_bot.scan_once_sync)


async def job_positions(context):
    if not _bot:
        return
    await asyncio.to_thread(_bot.check_positions_sync)


async def job_phase(context):
    if not _bot:
        return
    await asyncio.to_thread(_bot.update_phase)


def main():
    global _bot
    init_db()
    set_scanning_enabled(True)
    _bot = GoldenBot()

    if not _bot.token:
        logger.error("TELEGRAM token empty — running without TG")
        _bot.update_phase()
        while True:
            _bot.scan_once_sync()
            _bot.check_positions_sync()
            time.sleep(60)
        return

    app = Application.builder().token(_bot.token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_button))

    scan_min = _bot.cfg.getint("SCANNER", "check_interval_minutes", fallback=15)
    pos_sec = _bot.cfg.getint("SCANNER", "position_check_seconds", fallback=60)

    if app.job_queue:
        app.job_queue.run_repeating(job_scan, interval=scan_min * 60, first=10)
        app.job_queue.run_repeating(job_positions, interval=pos_sec, first=20)
        app.job_queue.run_repeating(job_phase, interval=3600, first=5)
    else:
        logger.warning("job_queue unavailable — install python-telegram-bot[job-queue]")

    _bot.update_phase()
    logger.info("Golden Scanner started | paper=%s", _bot.paper)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
