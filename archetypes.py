"""
archetypes.py
=============
29-ticker behavioral archetype map, derived from the 2026-08-14 Model Council
synthesis (Claude Opus 5 / GPT-5.6 / Claude Fable 5 reports).

Each group carries:
    - tickers: member list
    - max_concurrent: how many positions from this group may be open at once
      (correlation risk control -- Group A tickers move together, so only 1
      position is allowed open across the whole group at any time)
    - stop_k: ATR% multiplier used for stop-loss distance (k in Stop% = k * ATR%)
    - target_r: default reward multiple for Target 2 (in R, i.e. multiples of
      the initial risk)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Archetype:
    key: str
    name: str
    tickers: tuple
    max_concurrent: int
    stop_k: float
    target_r: float


ARCHETYPES = {
    "A": Archetype(
        key="A",
        name="Mega-beta semis/EV",
        tickers=("TSLA", "AMD", "MU", "NVDA", "AVGO"),
        max_concurrent=1,   # correlation 0.57-0.67 -- treat as ONE trade slot
        stop_k=0.50,
        target_r=2.0,
    ),
    "B": Archetype(
        key="B",
        name="AI/infra proxy",
        tickers=("TSM", "ASML", "QCOM", "TXN", "ORCL"),
        max_concurrent=1,
        stop_k=0.45,
        target_r=1.8,
    ),
    "C": Archetype(
        key="C",
        name="Thin high-vol software",
        tickers=("NET", "ZS", "CRWD", "FTNT", "ABNB"),
        max_concurrent=1,
        stop_k=0.50,
        target_r=1.5,
    ),
    "D": Archetype(
        key="D",
        name="Mega-cap movers",
        tickers=("AAPL", "MSFT", "AMZN"),
        max_concurrent=1,
        stop_k=0.30,
        target_r=1.6,
    ),
    "E": Archetype(
        key="E",
        name="Idiosyncratic large-cap",
        tickers=("CRM", "ADBE", "LLY", "NKE"),
        max_concurrent=2,   # lower cross-correlation -- 2 slots allowed
        stop_k=0.40,
        target_r=2.5,
    ),
    "F": Archetype(
        key="F",
        name="ADR / foreign listing",
        tickers=("BABA", "NVO"),  # ASML/TSM already counted in B
        max_concurrent=1,
        stop_k=0.45,
        target_r=1.8,
    ),
    "G": Archetype(
        key="G",
        name="True defensive",
        tickers=("JNJ", "XOM", "MDT", "V", "MA"),
        max_concurrent=1,   # regime indicator only, not a P&L generator
        stop_k=0.25,
        target_r=1.5,
    ),
}

# Flat ticker -> archetype-key lookup, built once at import time.
TICKER_TO_GROUP = {
    ticker: group.key
    for group in ARCHETYPES.values()
    for ticker in group.tickers
}


def group_of(ticker: str) -> str | None:
    """Return the archetype key for a ticker, or None if not classified."""
    return TICKER_TO_GROUP.get(ticker.upper())
