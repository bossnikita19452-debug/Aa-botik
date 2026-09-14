import aiohttp
import asyncio

async def test():
    url = "https://open-api.bingx.com/openApi/swap/v3/quote/klines"
    params = {
        "symbol": "BTC-USDT",
        "interval": "5m",
        "limit": 5,
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            data = await resp.json()
            print("Ответ от BingX:")
            print(data)

asyncio.run(test())
