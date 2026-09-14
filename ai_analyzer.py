import json
import os
from openai import AsyncOpenAI

from config import GROQ_API_KEY, GROQ_MODEL


client = AsyncOpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY,
)


SYSTEM_PROMPT = """Ты — профессиональный крипто-аналитик. Твоя задача — оценить потенциальный LONG-сетап по монете.

Тебе дают:
- Символ монеты
- Тип сделки (скальп / среднесрок / долгосрок)
- Технические данные (RSI, MACD, EMA, цена, объём)
- Свежие новости по монете и по рынку

Ты должен вернуть СТРОГО JSON в таком формате:
{
  "verdict": "long" | "skip",
  "confidence": 0.0-1.0,
  "reason": "краткое объяснение на русском (1-2 предложения)",
  "risk_level": "low" | "medium" | "high",
  "news_summary": "краткая выжимка из новостей на русском (1 предложение)"
}

Правила:
- "long" — только если новости не противоречат росту и технические данные подтверждают.
- confidence: 0.8+ — сильный сигнал, 0.5-0.8 — средний, <0.5 — слабый.
- Если новости негативные (взлом, делистинг, регуляторные проблемы) — verdict = "skip".
- Если новостей нет — оценивай только по технике, но снижай confidence на 0.1.
- Отвечай ТОЛЬКО JSON, без markdown и комментариев.
"""


async def analyze_signal(
    symbol: str,
    trade_type: str,
    technical_data: dict,
    news: list[dict],
) -> dict | None:
    """
    Отправить данные в Groq и получить вердикт.

    technical_data: {rsi, macd, ema_trend, price, volume_24h, conditions_met}
    news: список {title, source, published_at}
    """
    news_text = "\n".join(
        f"- {n['title']} ({n.get('source', 'unknown')})" for n in news[:10]
    ) or "Новостей не найдено."

    user_prompt = f"""
Монета: {symbol}
Тип сделки: {trade_type}

Технические данные:
- Цена: {technical_data.get('price')}
- RSI: {technical_data.get('rsi')}
- MACD histogram: {technical_data.get('macd')}
- EMA(200) тренд: {technical_data.get('ema_trend')}
- Объём за 24ч (USDT): {technical_data.get('volume_24h')}
- Совпало условий: {technical_data.get('conditions_met')}

Свежие новости:
{news_text}
"""

    try:
        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=400,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        result = json.loads(raw)

        # Валидация
        if result.get("verdict") not in ("long", "skip"):
            return None
        result["confidence"] = float(result.get("confidence", 0))
        return result

    except Exception as e:
        print(f"AI analyze error for {symbol}: {e}")
        return None