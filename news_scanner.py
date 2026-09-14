import aiohttp
from datetime import datetime, timedelta


# Бесплатный API без ключей — cryptocurrency.cv
NEWS_API_BASE = "https://cryptocurrency.cv/api"


async def get_news_for_coin(session: aiohttp.ClientSession, symbol: str, limit: int = 5) -> list[str]:
    """
    Получить последние новости по монете.
    symbol: "SOL-USDT" → берём "SOL"
    """
    coin = symbol.split("-")[0].upper()

    # Убираем стейблкоины и обёртки
    if coin in ("USDT", "USDC", "BUSD", "DAI"):
        return []

    try:
        url = f"{NEWS_API_BASE}/search"
        params = {"q": coin, "limit": limit}
        async with session.get(url, params=params, timeout=10) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
    except Exception:
        return []

    headlines = []
    # cryptocurrency.cv возвращает список статей
    articles = data.get("articles", data.get("data", []))
    for art in articles[:limit]:
        title = art.get("title") or art.get("headline")
        if title:
            headlines.append(title)

    return headlines


async def get_global_crypto_news(session: aiohttp.ClientSession, limit: int = 5) -> list[str]:
    """Получить общие новости крипторынка (для кнопки «Биткоин дня»)."""
    try:
        url = f"{NEWS_API_BASE}/news"
        params = {"limit": limit}
        async with session.get(url, params=params, timeout=10) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
    except Exception:
        return []

    headlines = []
    articles = data.get("articles", data.get("data", []))
    for art in articles[:limit]:
        title = art.get("title") or art.get("headline")
        if title:
            headlines.append(title)

    return headlines


async def get_bitcoin_news(session: aiohttp.ClientSession, limit: int = 10) -> list[str]:
    """Получить новости именно по BTC — для кнопки «Биткоин дня»."""
    try:
        url = f"{NEWS_API_BASE}/bitcoin"
        params = {"limit": limit}
        async with session.get(url, params=params, timeout=10) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
    except Exception:
        return []

    headlines = []
    articles = data.get("articles", data.get("data", []))
    for art in articles[:limit]:
        title = art.get("title") or art.get("headline")
        if title:
            headlines.append(title)

    return headlines