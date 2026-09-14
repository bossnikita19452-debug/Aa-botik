import json
from openai import AsyncOpenAI
from config import GROQ_API_KEY, GROQ_MODEL


client = AsyncOpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY,
)


SYSTEM_PROMPT = """Ты — профессиональный крипто-аналитик. Твоя задача — оценить торговый сетап 
по монете на основе технических данных и новостного фона.

Ты должен ответить ТОЛЬКО валидным JSON без лишнего текста. Формат:
{
  "signal": "long" | "no_signal",
  "confidence": "high" | "medium" | "low",
  "reason": "краткое объяснение на русском (1-2 предложения)",
  "risk_note": "предупреждение о рисках, если есть",
  "suggested_entry": число или null,
  "suggested_tp": число или null,
  "suggested_sl": число или null
}

Правила:
- "long" — если новости позитивные И технические данные подтверждают рост.
- "no_signal" — если новости негативные, нейтральные или противоречат технике.
- confidence: high = всё совпадает, medium = есть сомнения, low = много рисков.
"""


async def analyze_setup(
    symbol: str,
    price: float,
    rsi: float,
    macd_positive: bool,
    trend_up: bool,
    news_headlines: list[str],
    deal_type: str,
) -> dict:
    news_text = "\n".join(f"- {h}" for h in news_headlines[:5]) or "Новостей нет."

    user_prompt = f"""Монета: {symbol}
Тип сделки: {deal_type}
Текущая цена: {price}
RSI: {rsi}
MACD положительный: {macd_positive}
Тренд восходящий (цена выше EMA200): {trend_up}

Последние новости:
{news_text}

Оцени, стоит ли открывать Long. Ответь только JSON."""

    try:
        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=500,
        )
        content = response.choices[0].message.content.strip()

        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        result = json.loads(content)
        return result

    except json.JSONDecodeError:
        return {
            "signal": "no_signal",
            "confidence": "low",
            "reason": "ИИ вернул невалидный ответ",
            "risk_note": "Пропущено",
        }
    except Exception as e:
        return {
            "signal": "no_signal",
            "confidence": "low",
            "reason": f"Ошибка ИИ: {str(e)[:100]}",
            "risk_note": "Пропущено",
        }
