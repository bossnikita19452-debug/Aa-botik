"""Telegram-уведомления Golden Scanner."""
from __future__ import annotations

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, token: str = "", chat_id: str = ""):
        self.token = token or ""
        self.chat_id = chat_id or ""

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self.enabled:
            logger.info("[TG disabled] %s", text[:120])
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            r = requests.post(
                url,
                json={"chat_id": self.chat_id, "text": text, "parse_mode": parse_mode},
                timeout=15,
            )
            if r.status_code != 200:
                logger.warning("Telegram HTTP %s: %s", r.status_code, r.text[:200])
                return False
            return True
        except Exception as e:
            logger.error("Telegram send: %s", e)
            return False

    def entry(
        self,
        side: str,
        symbol: str,
        entry: float,
        sl: float,
        tp: float,
        risk_pct: float,
        strategy: str,
    ):
        emoji = "🟢" if side.upper() == "LONG" else "🔴"
        text = (
            f"{emoji} <b>{side.upper()} {symbol}</b> | {strategy}\n"
            f"Entry: <code>{entry:.6g}</code>\n"
            f"SL: <code>{sl:.6g}</code>\n"
            f"TP: <code>{tp:.6g}</code>\n"
            f"Риск: <b>{risk_pct:.1f}%</b>"
        )
        self.send(text)

    def exit_tp(self, symbol: str, r: float, pnl: float):
        self.send(f"✅ TP <b>{symbol}</b> +{r:.2f}R | PnL <b>${pnl:.2f}</b>")

    def exit_sl(self, symbol: str, r: float, pnl: float):
        self.send(f"❌ SL <b>{symbol}</b> {r:.2f}R | PnL <b>${pnl:.2f}</b>")

    def exit_time(self, symbol: str, r: float, pnl: float):
        self.send(f"⏰ TimeStop <b>{symbol}</b> {r:+.2f}R | PnL <b>${pnl:.2f}</b>")

    def error(self, msg: str):
        self.send(f"⚠️ API error: {msg}")

    def circuit_breaker(self, reason: str, minutes: int = 60):
        self.send(f"🛑 Бот остановлен на {minutes} мин\nПричина: {reason}")

    def phase(self, phase: str):
        self.send(f"📡 Фаза BTC: <b>{phase}</b>")
