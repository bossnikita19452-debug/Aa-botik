import os
from dotenv import load_dotenv

load_dotenv()

# ─── Telegram ─────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# ─── Флаг активности сканера ──────────────────────────────────────
SCANNING_ENABLED = True

# ─── Параметры стратегии (Quality 5m) ─────────────────────────────
TIMEFRAME = "5"                    # Bybit interval: 5 minutes
SCAN_INTERVAL_MINUTES = 5
CHECK_INTERVAL_SECONDS = 20

# ─── Сессия: Пн–Пт 10:00–23:00 МСК ────────────────────────────────
SESSION_WEEKDAYS = (0, 1, 2, 3, 4)  # Mon=0 ... Fri=4
SESSION_START_HOUR = 10             # MSK
SESSION_END_HOUR = 23               # MSK (не включая 23:00)
MSK_OFFSET_HOURS = 3

# ─── Индикаторы ───────────────────────────────────────────────────
EMA_FAST = 9
EMA_MID = 21
EMA_SLOW = 50
EMA_TREND = 200
VOL_SMA_FAST = 12
VOL_SMA_SLOW = 20
ATR_FAST = 10
ATR_SLOW = 14
RSI_FAST = 5
RSI_SLOW = 14

# ─── Риск ─────────────────────────────────────────────────────────
RISK_PER_TRADE_PCT = 1.0
MAX_LEVERAGE = 50
MIN_RISK_PCT = 0.20
MAX_RISK_PCT = 2.00
MAX_OPEN_POSITIONS = 12
MAX_HOLD_BARS = 12                  # 12 × 5m = 60 минут
MAX_TRADES_PER_SYMBOL_DAY = 3

# ─── RR по модулям ────────────────────────────────────────────────
RR_CLIMAX = 1.35
RR_L_LONG = 1.25
RR_BULL_IMPULSE = 1.30

# ─── Bybit ────────────────────────────────────────────────────────
BYBIT_KLINE_URL = "https://api.bybit.com/v5/market/kline"
BYBIT_CATEGORY = "linear"

# ─── Монеты (12) ──────────────────────────────────────────────────
COINS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "LINKUSDT", "AVAXUSDT", "ADAUSDT", "LTCUSDT", "DOGEUSDT",
    "DOTUSDT", "NEARUSDT",
]

SIGNAL_EMOJI = {
    "Climax": "⚡",
    "L_Long": "📈",
    "Bull_Impulse": "🚀",
}
