"""
Golden Scanner Bot — точка входа.
Планировщик: каждые 15 мин скан, раз в сутки фаза BTC.
Запуск: python main_golden.py
Требует config.ini (см. config.ini.example).
"""
from __future__ import annotations

import configparser
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

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
    count_open,
    get_state,
    has_open,
    init_db,
    save_open_trade,
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


def load_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    if not CONFIG_PATH.exists():
        example = Path(__file__).resolve().parent / "config.ini.example"
        if example.exists():
            logger.warning("config.ini не найден — скопируй config.ini.example → config.ini")
        cfg.read_dict(
            {
                "API": {"binance_key": "", "binance_secret": "", "testnet": "True"},
                "TELEGRAM": {"token": "", "chat_id": ""},
                "RISK": {
                    "risk_per_trade_pct": "1.0",
                    "max_open_positions": "3",
                    "max_daily_loss_pct": "5.0",
                    "circuit_breaker_losses": "5",
                    "circuit_breaker_pause_minutes": "60",
                },
                "SCANNER": {
                    "timeframe": "15m",
                    "btc_phase_timeframe": "1d",
                    "check_interval_minutes": "15",
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
                },
                "MR": {
                    "rsi_long_max": "30",
                    "rsi_short_min": "70",
                    "atr_mult_max": "1.5",
                    "sl_pct": "1.0",
                },
                "PHASE": {"ema_fast": "50", "ema_slow": "200", "adx_period": "14", "adx_min": "20"},
            }
        )
        return cfg
    cfg.read(CONFIG_PATH, encoding="utf-8")
    return cfg


def section_dict(cfg: configparser.ConfigParser, name: str) -> dict:
    if not cfg.has_section(name):
        return {}
    out = {}
    for k, v in cfg.items(name):
        try:
            if "." in v:
                out[k] = float(v)
            else:
                out[k] = int(v)
        except ValueError:
            out[k] = v
    return out


class GoldenBot:
    def __init__(self):
        self.cfg = load_config()
        self.tg = TelegramNotifier(
            self.cfg.get("TELEGRAM", "token", fallback=""),
            self.cfg.get("TELEGRAM", "chat_id", fallback=""),
        )
        testnet = self.cfg.getboolean("API", "testnet", fallback=True)
        self.ex = ExchangeClient(
            self.cfg.get("API", "binance_key", fallback=""),
            self.cfg.get("API", "binance_secret", fallback=""),
            testnet=testnet,
        )
        self.phase = MarketPhase.RANGE
        self.consecutive_losses = 0
        self.paused_until = 0.0
        self.tf = self.cfg.get("SCANNER", "timeframe", fallback="15m")
        self.risk_pct = self.cfg.getfloat("RISK", "risk_per_trade_pct", fallback=1.0)
        self.max_pos = self.cfg.getint("RISK", "max_open_positions", fallback=3)
        self.brk_cfg = section_dict(self.cfg, "BRK")
        self.mr_cfg = section_dict(self.cfg, "MR")
        self.phase_cfg = section_dict(self.cfg, "PHASE")
        self.paper = not bool(
            self.cfg.get("API", "binance_key", fallback="").strip()
        )  # без ключей — только сигналы

    def circuit_active(self) -> bool:
        return time.time() < self.paused_until

    def trigger_circuit(self, reason: str):
        mins = self.cfg.getint("RISK", "circuit_breaker_pause_minutes", fallback=60)
        self.paused_until = time.time() + mins * 60
        logger.warning("Circuit breaker: %s (%s min)", reason, mins)
        self.tg.circuit_breaker(reason, mins)

    def update_phase(self):
        df = fetch_klines("BTCUSDT", interval="1d", limit=250, futures=True)
        if df is None:
            logger.error("Не удалось загрузить BTC 1d")
            return
        df = df.rename(columns={"open_time": "time"})
        # phase expects high/low/close
        phase = detect_btc_phase(
            df,
            ema_fast=int(self.phase_cfg.get("ema_fast", 50)),
            ema_slow=int(self.phase_cfg.get("ema_slow", 200)),
            adx_period=int(self.phase_cfg.get("adx_period", 14)),
            adx_min=float(self.phase_cfg.get("adx_min", 20)),
        )
        if phase != self.phase:
            logger.info("Фаза BTC: %s → %s", self.phase.value, phase.value)
            self.tg.phase(phase.value)
        self.phase = phase
        set_state("btc_phase", phase.value)

    def scan_once(self):
        if self.circuit_active():
            logger.info("Пауза circuit breaker до %s", datetime.fromtimestamp(self.paused_until, tz=timezone.utc))
            return

        open_n = count_open()
        if open_n >= self.max_pos:
            logger.info("Лимит позиций %s/%s", open_n, self.max_pos)
            return

        strategies = active_strategies(self.phase)
        symbols = pairs_for_phase(self.phase.value)
        logger.info("Скан | фаза=%s | стратегии=%s | пар=%s", self.phase.value, strategies, len(symbols))

        equity = 1000.0
        if not self.paper:
            try:
                self.ex.connect()
                equity = self.ex.fetch_balance() or 1000.0
            except Exception as e:
                logger.error("Balance: %s", e)
                self.tg.error(str(e))

        found = 0
        for symbol in symbols:
            if count_open() >= self.max_pos:
                break
            if has_open(symbol):
                continue

            df = fetch_klines(symbol, interval=self.tf, limit=300, futures=True)
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
                continue

            logger.info(
                "SIGNAL %s %s %s entry=%.6g sl=%.6g tp=%.6g",
                sig.strategy, sig.side, symbol, sig.entry, sig.stop, sig.take,
            )
            self.tg.entry(sig.side, symbol, sig.entry, sig.stop, sig.take, self.risk_pct, sig.strategy)

            if self.paper:
                save_open_trade(symbol, sig.strategy, sig.side, sig.entry, amount, sig.stop, sig.take)
                found += 1
            else:
                try:
                    res = self.ex.open_with_sl_tp(symbol, sig.side, amount, sig.stop, sig.take)
                    if res.get("entry"):
                        save_open_trade(
                            symbol, sig.strategy, sig.side, sig.entry, amount, sig.stop, sig.take
                        )
                        found += 1
                    else:
                        self.tg.error(f"Order failed {symbol}")
                except Exception as e:
                    logger.exception("Order %s", symbol)
                    self.tg.error(str(e))

            time.sleep(0.2)

        logger.info("Скан завершён, новых сигналов: %s", found)

    def run_loop(self):
        init_db()
        interval = self.cfg.getint("SCANNER", "check_interval_minutes", fallback=15) * 60
        logger.info("Golden Scanner старт | paper=%s | interval=%ss", self.paper, interval)
        self.update_phase()
        last_phase_day = datetime.now(timezone.utc).date()

        while True:
            try:
                now = datetime.now(timezone.utc)
                if now.date() != last_phase_day and now.hour >= 0:
                    self.update_phase()
                    last_phase_day = now.date()

                self.scan_once()
            except Exception as e:
                logger.exception("Loop error")
                self.tg.error(str(e))
            time.sleep(interval)


if __name__ == "__main__":
    GoldenBot().run_loop()
