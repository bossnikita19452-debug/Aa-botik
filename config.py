import os
from dotenv import load_dotenv

load_dotenv()

# ─── Telegram ─────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# ─── Флаг активности сканера ──────────────────────────────────────
SCANNING_ENABLED = True

# ─── Параметры стратегии ──────────────────────────────────────────
TIMEFRAME = "5"                # Bybit ждёт "5", а не "5m"
SCAN_INTERVAL_MINUTES = 1
CHECK_INTERVAL_SECONDS = 30

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

# ─── RR для модулей ──────────────────────────────────────────────
RR_CLIMAX = 1.3
RR_L_LONG = 1.0
RR_BULL_IMPULSE = 1.2

# ─── Риск-менеджмент ─────────────────────────────────────────────
MIN_RISK_PCT = 0.2
MAX_RISK_PCT = 1.8
RISK_PER_TRADE_PCT = 1.0
MAX_LEVERAGE = 50
MAX_OPEN_POSITIONS = 10
MAX_HOLD_BARS = 9

# ─── Сессия (Пн–Пт 10:00–23:00 МСК) ──────────────────────────────
SESSION_WEEKDAYS = [0, 1, 2, 3, 4]   # 0=Пн, 4=Пт
SESSION_START_HOUR = 10
SESSION_END_HOUR = 23
MSK_OFFSET_HOURS = 3

# ─── Bybit ────────────────────────────────────────────────────────
BYBIT_KLINE_URL = "https://api.bybit.com/v5/market/kline"
BYBIT_CATEGORY = "linear"

# ─── Монеты ──────────────────────────────────────────────────────
COINS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "AVAXUSDT", "LINKUSDT", "NEARUSDT", "SUIUSDT",
    "APTUSDT", "ARBUSDT", "OPUSDT", "ATOMUSDT", "DOTUSDT",
    "LTCUSDT", "AAVEUSDT", "TRXUSDT", "ICPUSDT", "TONUSDT",
]

# ─── Эмодзи для модулей ──────────────────────────────────────────
SIGNAL_EMOJI = {
    "Climax": "⚡",
    "L_Long": "🟢",
    "Bull_Impulse": "🚀",
}
