for i, symbol in enumerate(symbols):
            try:
                df_5m = await get_klines(session, symbol, "5m", 100)
                df_15m = await get_klines(session, symbol, "15m", 100)
                df_1h = await get_klines(session, symbol, "1h", 250)
                df_4h = await get_klines(session, symbol, "4h", 100)
                df_1d = await get_klines(session, symbol, "1d", 250)

                if df_5m.empty or df_1h.empty or df_1d.empty:
                    print(f"[{i+1}/{len(symbols)}] {symbol}: нет свечей")
                    continue

                volume_24h = df_1h["volume"].tail(24).sum() * df_1h["close"].iloc[-1]
                if volume_24h < MIN_VOLUME_USDT:
                    print(f"[{i+1}/{len(symbols)}] {symbol}: объём {volume_24h:.0f} < {MIN_VOLUME_USDT}")
                    continue

                candidates = []
                if SCALP_ENABLED:
                    c = check_scalp(df_5m, df_15m)
                    if c:
                        candidates.append(c)
                if SWING_ENABLED:
                    c = check_swing(df_1h, df_4h)
                    if c:
                        candidates.append(c)
                if LONGTERM_ENABLED:
                    c = check_longterm(df_1d)
                    if c:
                        candidates.append(c)

                if not candidates:
                    print(f"[{i+1}/{len(symbols)}] {symbol}: технических сигналов нет")
                    continue

                print(f"[{i+1}/{len(symbols)}] {symbol}: КАНДИДАТ {[c['type'] for c in candidates]}")
