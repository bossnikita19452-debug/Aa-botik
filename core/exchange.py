"""Подключение к Binance USDT-M Futures через ccxt. Demo / real."""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ExchangeClient:
    def __init(
        self,
        api_key: str = "",
        api_secret: str = "",
        testnet: bool = True,
    ):
        self.testnet = testnet
        self._exchange = None
        self.api_key = api_key
        self.api_secret = api_secret

    def connect(self):
        import ccxt

        opts: dict[str, Any] = {
            "apiKey": self.api_key or "",
            "secret": self.api_secret or "",
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        }
        self._exchange = ccxt.binanceusdm(opts)
        if self.testnet:
            self._exchange.set_sandbox_mode(True)
            # Demo Trading endpoint
            self._exchange.urls["api"] = self._exchange.urls.get("test", self._exchange.urls["api"])
            logger.info("Exchange: Binance USDT-M DEMO (testnet)")
        else:
            logger.info("Exchange: Binance USDT-M LIVE")
        return self._exchange

    @property
    def exchange(self):
        if self._exchange is None:
            self.connect()
        return self._exchange

    def fetch_balance(self) -> float:
        """USDT equity (free + used)."""
        try:
            bal = self.exchange.fetch_balance()
            usdt = bal.get("USDT") or {}
            total = usdt.get("total")
            if total is not None:
                return float(total)
            return float(usdt.get("free", 0) or 0)
        except Exception as e:
            logger.error("fetch_balance: %s", e)
            return 0.0

    def position_size(self, equity: float, risk_pct: float, entry: float, stop: float) -> float:
        """position_size = (equity * risk_pct/100) / abs(entry - stop)"""
        risk_usd = equity * (risk_pct / 100.0)
        dist = abs(entry - stop)
        if dist <= 0 or risk_usd <= 0:
            return 0.0
        return risk_usd / dist

    def create_market_order(
        self, symbol: str, side: str, amount: float, params: Optional[dict] = None
    ) -> Optional[dict]:
        """side: buy | sell"""
        try:
            # ccxt unified: BTC/USDT:USDT for futures often
            sym = self._normalize_symbol(symbol)
            order = self.exchange.create_order(
                sym, "market", side.lower(), amount, params=params or {}
            )
            logger.info("Market %s %s amount=%s", side, sym, amount)
            return order
        except Exception as e:
            logger.error("create_market_order: %s", e)
            return None

    def create_stop_market(
        self, symbol: str, side: str, stop_price: float, amount: Optional[float] = None
    ) -> Optional[dict]:
        """
        STOP_MARKET reduceOnly closePosition.
        side: направление ЗАКРЫТИЯ (sell для long, buy для short).
        """
        try:
            sym = self._normalize_symbol(symbol)
            params = {
                "stopPrice": stop_price,
                "reduceOnly": True,
                "closePosition": True,
            }
            # amount optional when closePosition=True on Binance
            amt = amount if amount is not None else 0
            order = self.exchange.create_order(
                sym, "STOP_MARKET", side.lower(), amt, params=params
            )
            logger.info("STOP_MARKET %s %s @ %s", side, sym, stop_price)
            return order
        except Exception as e:
            logger.error("create_stop_market: %s", e)
            return None

    def create_take_profit_market(
        self, symbol: str, side: str, stop_price: float, amount: Optional[float] = None
    ) -> Optional[dict]:
        try:
            sym = self._normalize_symbol(symbol)
            params = {
                "stopPrice": stop_price,
                "reduceOnly": True,
                "closePosition": True,
            }
            amt = amount if amount is not None else 0
            order = self.exchange.create_order(
                sym, "TAKE_PROFIT_MARKET", side.lower(), amt, params=params
            )
            logger.info("TAKE_PROFIT_MARKET %s %s @ %s", side, sym, stop_price)
            return order
        except Exception as e:
            logger.error("create_take_profit_market: %s", e)
            return None

    def open_with_sl_tp(
        self,
        symbol: str,
        side: str,
        amount: float,
        stop: float,
        take: float,
    ) -> dict:
        """
        Market entry + SL + TP.
        side: LONG -> buy entry, sell SL/TP
              SHORT -> sell entry, buy SL/TP
        """
        entry_side = "buy" if side.upper() == "LONG" else "sell"
        close_side = "sell" if side.upper() == "LONG" else "buy"

        entry_order = self.create_market_order(symbol, entry_side, amount)
        sl_order = self.create_stop_market(symbol, close_side, stop, amount)
        tp_order = self.create_take_profit_market(symbol, close_side, take, amount)
        return {"entry": entry_order, "sl": sl_order, "tp": tp_order}

    def _normalize_symbol(self, symbol: str) -> str:
        s = symbol.upper().replace("/", "")
        if s.endswith("USDT") and ":" not in s:
            base = s[:-4]
            return f"{base}/USDT:USDT"
        return symbol
