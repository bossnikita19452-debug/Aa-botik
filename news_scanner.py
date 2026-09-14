import aiohttp


NEWS_API = "https://min-api.cryptocompare.com/data/v2/news/"


async def _fetch_news(session: aiohttp.ClientSession, categories: str = "", limit: int = 5) -> list[str]:
    """Базовый запрос новостей к CryptoCompare."""
    params = {"lang": "EN"}
    if categories:
        params["categories"] = categories

    try:
        async with session.get(NEWS_API, params=params, timeout=10) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
    except Exception:
        return []

    headlines = []
    for item in data.get("Data", [])[:limit]:
        title = item.get("title")
        if title:
            headlines.append(title)
    return headlines


async def get_news_for_coin(session: aiohttp.ClientSession, symbol: str, limit: int = 5) -> list[str]:
    """Новости по конкретной монете (BTC, ETH, SOL...)."""
    coin = symbol.split("-")[0].upper()
    if coin in ("USDT", "USDC", "BUSD", "DAI"):
        return []
    return await _fetch_news(session, categories=coin, limit=limit)


async def get_global_crypto_news(session: aiohttp.ClientSession, limit: int = 5) -> list[str]:
    """Общие новости крипторынка."""
    return await _fetch_news(session, limit=limit)


async def get_bitcoin_news(session: aiohttp.ClientSession, limit: int = 10) -> list[str]:
    """Новости по BTC."""
    return await _fetch_news(session, categories="BTC", limit=limit)
