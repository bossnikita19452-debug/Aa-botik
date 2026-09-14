import aiohttp


BASE_URL = "https://api.coingecko.com/api/v3"

COIN_ID_MAP = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
    "BNB": "binancecoin", "XRP": "ripple", "ADA": "cardano",
    "DOGE": "dogecoin", "AVAX": "avalanche-2", "LINK": "chainlink",
    "TON": "the-open-network", "DOT": "polkadot", "MATIC": "matic-network",
    "LTC": "litecoin", "TRX": "tron", "SHIB": "shiba-inu",
    "ATOM": "cosmos", "UNI": "uniswap", "NEAR": "near",
    "APT": "aptos", "ARB": "arbitrum", "OP": "optimism",
    "SUI": "sui", "PEPE": "pepe", "WIF": "dogwifcoin",
}


async def _fetch_news(session, coin_id: str = "", limit: int = 5) -> list[str]:
    url = f"{BASE_URL}/news"
    params = {"per_page": limit}
    if coin_id:
        params["coin"] = coin_id

    try:
        async with session.get(url, params=params, timeout=10) as resp:
            if resp.status != 200:
                return []
            data = await resp.json()
    except Exception:
        return []

    headlines = []
    for item in data.get("data", [])[:limit]:
        title = item.get("title")
        if title:
            headlines.append(title)
    return headlines


async def get_news_for_coin(session, symbol: str, limit: int = 5) -> list[str]:
    ticker = symbol.split("-")[0].upper()
    if ticker in ("USDT", "USDC", "BUSD", "DAI"):
        return []
    coin_id = COIN_ID_MAP.get(ticker, ticker.lower())
    return await _fetch_news(session, coin_id=coin_id, limit=limit)


async def get_global_crypto_news(session, limit: int = 5) -> list[str]:
    return await _fetch_news(session, limit=limit)


async def get_bitcoin_news(session, limit: int = 10) -> list[str]:
    return await _fetch_news(session, coin_id="bitcoin", limit=limit)
