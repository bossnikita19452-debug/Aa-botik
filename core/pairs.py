"""
Списки пар Golden Scanner: 81 пара (strategy + symbol).

Важно:
- Считаем пары strategy:symbol, НЕ уникальные монеты.
- Одна монета может быть в нескольких стратегиях (это норма).
- В один момент активны только пары текущей фазы BTC.

Разбивка:
  BRK_LONG  22
  BRK_SHORT 12
  MR_LONG   25
  MR_SHORT  22
  ИТОГО     81
"""

# UPTREND → только эти
BRK_LONG_PAIRS = [
    "AVAXUSDT",
    "CAKEUSDT",
    "COTIUSDT",
    "DASHUSDT",
    "DOTUSDT",
    "ETCUSDT",
    "ICPUSDT",
    "INJUSDT",
    "NILUSDT",
    "PENGUUSDT",
    "PYTHUSDT",
    "RAYUSDT",
    "RENDERUSDT",
    "SAGAUSDT",
    "SOXLBUSDT",
    "THEUSDT",
    "TIAUSDT",
    "TRUMPUSDT",
    "XLMUSDT",
    "ZENUSDT",
    "ZKCUSDT",
    "ZROUSDT",
]  # 22

# DOWNTREND → только эти
BRK_SHORT_PAIRS = [
    "BANKUSDT",
    "DEXEUSDT",
    "ENAUSDT",
    "ENSOUSDT",
    "ETHFIUSDT",
    "ICPUSDT",
    "RAYUSDT",
    "SOLUSDT",
    "TRUMPUSDT",
    "VIRTUALUSDT",
    "XPLUSDT",
    "ZECUSDT",
]  # 12

# RANGE → MR_LONG + MR_SHORT
MR_LONG_PAIRS = [
    "ADAUSDT",
    "ARBUSDT",
    "BICOUSDT",
    "CRVUSDT",
    "DEXEUSDT",
    "ENAUSDT",
    "ENSOUSDT",
    "FFUSDT",
    "INJUSDT",
    "JUPUSDT",
    "MORPHOUSDT",
    "PENDLEUSDT",
    "PENGUUSDT",
    "RAYUSDT",
    "SAGAUSDT",
    "SOLUSDT",
    "STRKUSDT",
    "SUIUSDT",
    "TUTUSDT",
    "UNIUSDT",
    "VIRTUALUSDT",
    "WLDUSDT",
    "XPLUSDT",
    "ZAMAUSDT",
    "ZECUSDT",
]  # 25

MR_SHORT_PAIRS = [
    "ACEUSDT",
    "ARUSDT",
    "ASTERUSDT",
    "BABYUSDT",
    "BTCUSDT",
    "CAKEUSDT",
    "CHIPUSDT",
    "CRVUSDT",
    "ENSOUSDT",
    "FETUSDT",
    "INJUSDT",
    "NVDABUSDT",
    "RAYUSDT",
    "SEIUSDT",
    "SYNUSDT",
    "TAOUSDT",
    "TRUMPUSDT",
    "WLDUSDT",
    "WLFIUSDT",
    "XLMUSDT",
    "XPLUSDT",
    "ZKCUSDT",
]  # 22

PAIRS_BY_STRATEGY = {
    "BRK_LONG": BRK_LONG_PAIRS,
    "BRK_SHORT": BRK_SHORT_PAIRS,
    "MR_LONG": MR_LONG_PAIRS,
    "MR_SHORT": MR_SHORT_PAIRS,
}

# Все уникальные тикеры (для загрузки свечей)
ALL_SYMBOLS = sorted(
    set(BRK_LONG_PAIRS + BRK_SHORT_PAIRS + MR_LONG_PAIRS + MR_SHORT_PAIRS)
)

# Совместимость со старым именем
ALL_PAIRS = ALL_SYMBOLS


def count_strategy_pairs() -> dict:
    """81 = сумма длин списков по стратегиям."""
    return {
        "BRK_LONG": len(BRK_LONG_PAIRS),
        "BRK_SHORT": len(BRK_SHORT_PAIRS),
        "MR_LONG": len(MR_LONG_PAIRS),
        "MR_SHORT": len(MR_SHORT_PAIRS),
        "total_strategy_pairs": (
            len(BRK_LONG_PAIRS)
            + len(BRK_SHORT_PAIRS)
            + len(MR_LONG_PAIRS)
            + len(MR_SHORT_PAIRS)
        ),
        "unique_symbols": len(ALL_SYMBOLS),
    }


def pairs_for_phase(phase: str) -> list[str]:
    """
    Уникальные символы, активные в фазе (для скана).
    UPTREND  → 22 BRK_LONG
    DOWNTREND → 12 BRK_SHORT
    RANGE    → unique(MR_LONG ∪ MR_SHORT) ≤ 47
    """
    if phase == "UPTREND":
        return list(BRK_LONG_PAIRS)
    if phase == "DOWNTREND":
        return list(BRK_SHORT_PAIRS)
    return sorted(set(MR_LONG_PAIRS + MR_SHORT_PAIRS))


def strategy_pairs_for_phase(phase: str) -> list[tuple[str, str]]:
    """Список (strategy, symbol) для текущей фазы — без потери дублей по стратегиям."""
    if phase == "UPTREND":
        return [("BRK_LONG", s) for s in BRK_LONG_PAIRS]
    if phase == "DOWNTREND":
        return [("BRK_SHORT", s) for s in BRK_SHORT_PAIRS]
    out = [("MR_LONG", s) for s in MR_LONG_PAIRS]
    out += [("MR_SHORT", s) for s in MR_SHORT_PAIRS]
    return out
