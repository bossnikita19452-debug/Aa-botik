import aiohttp


BASE_URL = "https://cryptocurrency.cv"


async def _fetch_news(session: aiohttp.ClientSession, endpoint: str, limit: int = 5) -> list[str]:
    """Базовый запрос новостей к cryptocurrency.cv."""
    url = f"{BASE_URL}/api/{endpoint}"
    params = {"limit": limit}

    try:
        async with session.get(url, params=params, timeout=10) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
    except Exception:
        return []

    headlines = []
    articles = data.get("articles", data.get("data", []))
    for item in articles[:limit]:
        title = item.get("title")
        if title:
            headlines.append(title)
    return headlines


async def get_news_for_coin(session: aiohttp.ClientSession, symbol: str, limit: int = 5) -> list[str]:
    """Новости по конкретной монете (BTC, ETH, SOL...)."""
    coin = symbol.split("-")[0].upper()
    if coin in ("USDT", "USDC", "BUSD", "DAI"):
        return []
    # Для конкретной монеты используем поиск
    return await _fetch_news(session, f"search?q={coin}", limit=limit)


async def get_global_crypto_news(session: aiohttp.ClientSession, limit: int = 5) -> list[str]:
    """Общие новости крипторынка."""
    return await _fetch_news(session, "news", limit=limit)


async def get_bitcoin_news(session: aiohttp.ClientSession, limit: int = 10) -> list[str]:
    """Новости по BTC."""
    return await _fetch_news(session, "bitcoin", limit=limit)
