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
SCAN_INTERVAL_MINUTES = 5
CHECK_INTERVAL_SECONDS = 60    # tickers реже — меньше rate limit

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

# ─── Сессия ───────────────────────────────────────────────────────
SESSION_24_7 = True
SESSION_WEEKDAYS = [0, 1, 2, 3, 4, 5, 6]
SESSION_START_HOUR = 0
SESSION_END_HOUR = 24
MSK_OFFSET_HOURS = 3

# ─── Bybit / rate limit ───────────────────────────────────────────
BYBIT_KLINE_URL = "https://api.bybit.com/v5/market/kline"
BYBIT_CATEGORY = "linear"
# ~26 монет × 0.55 ≈ 14 сек на цикл
API_SLEEP_SEC = 0.55
API_MAX_RETRIES = 4
KLINE_LIMIT = 250

# ─── Монеты ───────────────────────────────────────────────────────
# Базовый список + месяц-тест WR >= 55%
# WR55: BRETT 66.7%, GRT 63.9%, CNPY 71.4%(n=9), YGG 58.6%,
#        SHIB 57.7%, SEI 56.8%, PROVE 55.6%
COINS = [
    # core
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "AVAXUSDT", "LINKUSDT", "NEARUSDT", "SUIUSDT",
    "APTUSDT", "ARBUSDT", "OPUSDT", "ATOMUSDT", "DOTUSDT",
    "LTCUSDT", "AAVEUSDT", "TRXUSDT", "ICPUSDT",
    # month-test Pure WR >= 55%
    "BRETTUSDT", "GRTUSDT", "YGGUSDT", "SHIBUSDT",
    "SEIUSDT", "PROVEUSDT", "CNPYUSDT",
]

SIGNAL_EMOJI = {
    "Climax": "⚡",
    "L_Long": "🟢",
    "Bull_Impulse": "🚀",
}
