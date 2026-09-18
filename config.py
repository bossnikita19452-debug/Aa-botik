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
TIMEFRAME = "15"
SCAN_INTERVAL_MINUTES = 15
CHECK_INTERVAL_SECONDS = 30

# ─── Параметры индикаторов ────────────────────────────────────────
BTC_EMA_PERIOD = 50
ALT_EMA_PERIOD = 800
VOLUME_SMA_PERIOD = 20
ATR_PERIOD = 14

# ─── Параметры пробоя ─────────────────────────────────────────────
LOOKBACK_BARS = 48
MIN_TOUCHES = 3
TOUCH_TOLERANCE = 0.002

# ─── Объёмные фильтры ─────────────────────────────────────────────
VOLUME_MULT_LONG = 1.8
VOLUME_MULT_SHORT = 2.2

# ─── Риск-менеджмент ──────────────────────────────────────────────
ATR_SL_MULTIPLIER = 1.5
RR_RATIO = 1.5
RISK_PER_TRADE_PCT = 1.0      # всегда 1% депозита
MAX_LEVERAGE = 50             # МАКСИМУМ 50x (было 100)
MIN_RISK_PCT = 0.8            # Минимальный риск для входа (фильтр)

# ─── Лимиты ───────────────────────────────────────────────────────
MAX_OPEN_POSITIONS = 10
MAX_HOLD_BARS = 16

# ─── Bybit ────────────────────────────────────────────────────────
BYBIT_KLINE_URL = "https://api.bybit.com/v5/market/kline"
BYBIT_CATEGORY = "linear"

# ─── Whitelist: 50 монет ─────────────────────────────────────────
COINS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "AVAXUSDT", "LINKUSDT", "NEARUSDT", "SUIUSDT",
    "APTUSDT", "RENDERUSDT", "FETUSDT", "ARBUSDT", "OPUSDT",
    "MATICUSDT", "ATOMUSDT", "FTMUSDT", "DOTUSDT", "LTCUSDT",
    "TIAUSDT", "SEIUSDT", "AAVEUSDT", "STXUSDT", "KASUSDT",
    "TRXUSDT", "ICPUSDT", "TONUSDT", "GALAUSDT", "DYDXUSDT",
    "BLURUSDT", "LDOUSDT", "QNTUSDT", "INJUSDT", "JUPUSDT",
    "WLDUSDT", "PYTHUSDT", "MANTAUSDT", "ZROUSDT", "ENAUSDT",
    "TAOUSDT", "ORDIUSDT", "ARUSDT", "RUNEUSDT", "ALGOUSDT",
    "FLOWUSDT", "AXSUSDT", "SANDUSDT", "CHZUSDT", "MINAUSDT",
]

SIGNAL_EMOJI = {
    "strong": "🟢",
    "medium": "🟡",
    "weak": "🔴",
}
