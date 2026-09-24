# Golden Scanner Bot

Реализация ТЗ: 4 стратегии с переключением по фазе BTC.

## Статус — каркас готов

### Готово
- `config.ini.example` — все параметры
- `core/indicators.py` — EMA, RSI, BB, ATR, ADX
- `core/phase.py` — UPTREND / DOWNTREND / RANGE
- `core/data.py` — OHLCV Binance Futures public API
- `core/exchange.py` — ccxt market + STOP_MARKET + TP reduceOnly
- `core/pairs.py` — списки пар из ТЗ
- `strategies/brk_long.py` / `brk_short.py` / `mr_long.py` / `mr_short.py`
- `storage/db.py` — SQLite trades + bot_state
- `bot/telegram_notify.py` — входы/выходы/ошибки/circuit
- `main_golden.py` — цикл: фаза раз в день + скан каждые 15 мин
- `requirements.txt` — + ccxt, requests

### Ещё можно доработать
- Мониторинг закрытий SL/TP с биржи → запись exit в БД + TG
- Time-stop 24 свечи (сейчас SL/TP на бирже)
- Дневной circuit breaker по просадке 5%
- Уточнение demo URL Binance Demo Trading
- Бэктест-скрипт на истории

## Запуск

```bash
cp config.ini.example config.ini
# заполнить token, chat_id; для live — ключи, testnet=False
pip install -r requirements.txt
python main_golden.py
```

Без API-ключей бот работает в **paper-режиме** (только сигналы + запись в SQLite + Telegram).

## Фаза BTC (1d)
| Условие | Фаза | Сканеры |
|---------|------|--------|
| close > EMA50 и ADX > 20 | UPTREND | BRK_LONG |
| close < EMA50 и ADX > 20 | DOWNTREND | BRK_SHORT |
| иначе | RANGE | MR_LONG + MR_SHORT |

## Целевые метрики (из ТЗ)
- WR 50–57%
- PF 1.4–1.6
- ~100–120 сделок/мес
