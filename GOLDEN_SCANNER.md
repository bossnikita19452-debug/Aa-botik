# Golden Scanner Bot

Реализация ТЗ: 4 стратегии с переключением по фазе BTC.

## Статус

### Готово
- `config.ini.example` — все параметры
- `core/indicators.py` — EMA, RSI, BB, ATR, ADX
- `core/phase.py` — UPTREND / DOWNTREND / RANGE по BTC 1d
- `strategies/brk_long.py` — пробой вверх + ретест
- `strategies/brk_short.py` — пробой вниз + ретест
- `strategies/mr_long.py` — mean reversion long
- `strategies/mr_short.py` — mean reversion short

### В работе / далее
- `core/exchange.py` — ccxt Binance Futures (+ demo)
- `core/data.py` — OHLCV (Binance public / vision)
- `bot/telegram.py` — уведомления
- `storage/trades.db` + schema
- `main.py` — планировщик 15m + phase daily
- Риск: размер позиции, max positions, circuit breaker
- Ордера: market + STOP_MARKET / TAKE_PROFIT_MARKET с reduceOnly

## Фаза BTC (1d)
| Условие | Фаза | Активные сканеры |
|---------|------|------------------|
| close > EMA50 и ADX > 20 | UPTREND | BRK_LONG |
| close < EMA50 и ADX > 20 | DOWNTREND | BRK_SHORT |
| иначе | RANGE | MR_LONG + MR_SHORT |

## Запуск (когда main готов)
1. Скопировать `config.ini.example` → `config.ini`
2. Вписать API keys (testnet=True) и Telegram
3. `pip install -r requirements.txt`
4. `python main.py`

## Целевые метрики (из ТЗ)
- WR 50–57%
- PF 1.4–1.6
- ~100–120 сделок/мес
