import os
from dotenv import load_dotenv

load_dotenv()

# ─── Telegram ─────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ─── Groq (ИИ) ────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "openai/gpt-oss-120b"  # актуальная модель, 1000 запросов/день

# ─── BingX (публичные данные) ─────────────────────────────────────
BINGX_API_KEY = os.getenv("BINGX_API_KEY", "")
BINGX_SECRET_KEY = os.getenv("BINGX_SECRET_KEY", "")
BINGX_BASE_URL = "https://open-api.bingx.com"

# ─── Настройки сканирования ───────────────────────────────────────
SCAN_INTERVAL_MINUTES = 15
MIN_VOLUME_USDT = 5_000

# ─── Соотношение риск/прибыль ─────────────────────────────────────
MIN_RR = 1.0
MAX_RR = 5.0


# ─── Типы сделок ──────────────────────────────────────────────────
SCALP_ENABLED = True
SWING_ENABLED = True
LONGTERM_ENABLED = True
