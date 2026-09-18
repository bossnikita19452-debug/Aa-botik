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
TIMEFRAME = "15"             # M15
SCAN_INTERVAL_MINUTES = 15   # Сканирование на закрытии свечи
CHECK_INTERVAL_SECONDS = 30  # Проверка TP/SL

# ─── Параметры индикаторов ────────────────────────────────────────
BTC_EMA_PERIOD = 50          # EMA 50 на M15 для BTC-фильтра
ALT_EMA_PERIOD = 800         # EMA 800 на M15 = EMA 200 на H1
VOLUME_SMA_PERIOD = 20       # Volume SMA 20
ATR_PERIOD = 14              # ATR 14

# ─── Параметры пробоя ─────────────────────────────────────────────
LOOKBACK_BARS = 48           # 48 свечей M15 = 12 часов
MIN_TOUCHES = 3              # Минимум касаний уровня
TOUCH_TOLERANCE = 0.002      # 0.2% для подсчёта касаний

# ─── Объёмные фильтры ─────────────────────────────────────────────
VOLUME_MULT_LONG = 1.8       # Для LONG
VOLUME_MULT_SHORT = 2.2      # Для SHORT (жёстче)

# ─── Риск-менеджмент ──────────────────────────────────────────────
ATR_SL_MULTIPLIER = 1.5      # SL = Entry ± 1.5 * ATR
RR_RATIO = 1.5               # TP = 1.5R
RISK_PER_TRADE_PCT = 1.0     # 1% от equity

# ─── Лимиты ───────────────────────────────────────────────────────
MAX_OPEN_POSITIONS = 10      # Максимум одновременных сделок
MAX_HOLD_BARS = 16           # Таймаут: 16 свечей M15 = 4 часа

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
