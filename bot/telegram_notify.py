"""Telegram-уведомления Golden Scanner. Русский язык.

Формат сигнала:
  Вход        — реальная цена входа (open свечи после ретеста)
  Уровень     — уровень ретеста (справочно)
  Стоп / Тейк — цены
  Риск        — % от депозита
"""
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
            logger.info("[TG выкл] %s", text[:200])
            return False
        url = "https://api.telegram.org/bot" + self.token + "/sendMessage"
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
        level: Optional[float] = None,
    ):
        """Сигнал на вход. level — необязательно, показываем справочно."""
        if side.upper() == "LONG":
            emoji = "🟢"
            side_ru = "ЛОНГ"
        else:
            emoji = "🔴"
            side_ru = "ШОРТ"

        lines = []
        lines.append(emoji + " <b>" + side_ru + " " + symbol + "</b> | " + strategy)
        lines.append("")

        # Основные цены
        lines.append("Вход:  <code>" + self._fmt(entry) + "</code>")
        lines.append("Стоп:  <code>" + self._fmt(sl) + "</code>")
        lines.append("Тейк:  <code>" + self._fmt(tp) + "</code>")

        # Разрыв от уровня (если передан)
        if level is not None and level > 0:
            gap = (entry - level) / level * 100
            gap_abs = abs(gap)
            if gap_abs < 0.01:
                gap_str = "0.00%"
            else:
                gap_str = ("+" if gap >= 0 else "") + str(round(gap, 2)) + "%"
            lines.append("Уровень: <code>" + self._fmt(level) + "</code> (разрыв " + gap_str + ")")

        lines.append("")
        lines.append("Риск: <b>" + str(round(risk_pct, 2)) + "%</b>")

        # SL / TP в %
        if entry > 0:
            sl_pct = abs(entry - sl) / entry * 100
            tp_pct = abs(tp - entry) / entry * 100
            lines.append("Стоп: " + str(round(sl_pct, 2)) + "% | Тейк: " + str(round(tp_pct, 2)) + "%")

        self.send("\n".join(lines))

    def exit_tp(self, symbol: str, r: float, pnl: float):
        emoji = "✅"
        text = (
            emoji + " <b>ТЕЙК-ПРОФИТ</b> " + symbol + "\n"
            "Результат: <b>+" + str(round(r, 2)) + "R</b>\n"
            "PnL: <b>$" + str(round(pnl, 2)) + "</b>"
        )
        self.send(text)

    def exit_sl(self, symbol: str, r: float, pnl: float):
        emoji = "❌"
        text = (
            emoji + " <b>СТОП-ЛОСС</b> " + symbol + "\n"
            "Результат: <b>" + str(round(r, 2)) + "R</b>\n"
            "PnL: <b>$" + str(round(pnl, 2)) + "</b>"
        )
        self.send(text)

    def exit_time(self, symbol: str, r: float, pnl: float):
        emoji = "⏰"
        sign = "+" if r >= 0 else ""
        text = (
            emoji + " <b>ВРЕМЯ ИСТЕКЛО</b> " + symbol + "\n"
            "Результат: <b>" + sign + str(round(r, 2)) + "R</b>\n"
            "PnL: <b>$" + str(round(pnl, 2)) + "</b>"
        )
        self.send(text)

    def error(self, msg: str):
        self.send("⚠️ <b>Ошибка API</b>\n" + str(msg)[:300])

    def circuit_breaker(self, reason: str, minutes: int = 60):
        self.send(
            "🛑 <b>Сканер остановлен</b>\n"
            "Причина: " + reason + "\n"
            "Пауза: " + str(minutes) + " мин"
        )

    def phase(self, phase: str):
        ru = {"UPTREND": "ВОСХОДЯЩИЙ", "DOWNTREND": "НИСХОДЯЩИЙ", "RANGE": "БОКОВИК"}.get(phase, phase)
        self.send("📡 <b>Фаза BTC: " + ru + "</b>")

    def signal_skipped(self, symbol: str, reason: str):
        """Если сигнал был, но пропущен (например, gap > MAX_ENTRY_GAP)."""
        self.send(
            "⚠️ <b>Сигнал пропущен</b> " + symbol + "\n"
            "Причина: " + reason
        )

    @staticmethod
    def _fmt(x: float) -> str:
        """Форматирует цену без лишних нулей."""
        if x is None:
            return "-"
        if x >= 1000:
            return str(round(x, 2))
        if x >= 1:
            return str(round(x, 4))
        if x >= 0.01:
            return str(round(x, 5))
        return str(round(x, 7))
