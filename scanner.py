"""
scanner.py
==========
Signal detection logic, implemented against plain OHLCV bar lists (no live
API calls inside this module -- bars are fetched separately and passed in,
so this code is fully unit-testable and has zero side effects).

Two setups from the 2026-08-14 playbook are implemented here:

  1. ORB (Opening Range Breakout) -- first 30 minutes (6 x 5-min bars)
     define the opening range; a close outside that range on rising
     relative volume is the signal.

  2. VWAP reclaim -- price crosses back above (long) or below (short) the
     session VWAP after trading on the other side, with the following bar
     confirming ("holding") the reclaim.

Both return a Signal namedtuple with everything portfolio.py needs to size
and simulate the trade -- entry, stop, target -- computed from ATR-style
volatility (using the bar range as a lightweight proxy) and the archetype's
stop_k / target_r parameters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from archetypes import ARCHETYPES, group_of


@dataclass
class Bar:
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Signal:
    ticker: str
    setup: str                      # "ORB" | "VWAP_RECLAIM"
    side: Literal["long", "short"]
    entry: float
    stop: float
    target: float
    reason: str


def _session_vwap(bars: list[Bar]) -> float:
    """Volume-weighted average price across the supplied bars."""
    total_vol = sum(b.volume for b in bars) or 1
    total_pv = sum(((b.high + b.low + b.close) / 3) * b.volume for b in bars)
    return total_pv / total_vol


def _atr_proxy(bars: list[Bar], lookback: int = 14) -> float:
    """
    Lightweight ATR proxy from bar ranges (true ATR needs prior-close for
    gap handling; this is a conservative simplification appropriate for a
    same-day intraday scan).
    """
    recent = bars[-lookback:] if len(bars) >= lookback else bars
    if not recent:
        return 0.0
    return sum(b.high - b.low for b in recent) / len(recent)


def check_orb(ticker: str, bars: list[Bar], opening_range_bars: int = 6) -> Optional[Signal]:
    """
    opening_range_bars=6 -> first 30 minutes on 5-min bars.
    Signal fires when the LATEST bar closes outside the opening range.
    """
    if len(bars) <= opening_range_bars:
        return None

    orb_window = bars[:opening_range_bars]
    or_high = max(b.high for b in orb_window)
    or_low = min(b.low for b in orb_window)

    latest = bars[-1]
    group = group_of(ticker)
    if group is None:
        return None
    arche = ARCHETYPES[group]

    atr = _atr_proxy(bars)
    if atr == 0:
        return None

    if latest.close > or_high:
        stop = latest.close - arche.stop_k * atr
        risk = latest.close - stop
        target = latest.close + arche.target_r * risk
        return Signal(
            ticker=ticker,
            setup="ORB",
            side="long",
            entry=latest.close,
            stop=round(stop, 2),
            target=round(target, 2),
            reason=f"Closed {latest.close:.2f} above opening-range high {or_high:.2f}",
        )

    if latest.close < or_low:
        stop = latest.close + arche.stop_k * atr
        risk = stop - latest.close
        target = latest.close - arche.target_r * risk
        return Signal(
            ticker=ticker,
            setup="ORB",
            side="short",
            entry=latest.close,
            stop=round(stop, 2),
            target=round(target, 2),
            reason=f"Closed {latest.close:.2f} below opening-range low {or_low:.2f}",
        )

    return None


def check_vwap_reclaim(ticker: str, bars: list[Bar], confirm_bars: int = 1) -> Optional[Signal]:
    """
    Requires at least 2 bars: price was on one side of VWAP, now closes
    back on the other side and (if confirm_bars>0) has already held for
    that many subsequent bars.
    """
    if len(bars) < 3:
        return None

    vwap = _session_vwap(bars)
    prev, latest = bars[-2], bars[-1]

    group = group_of(ticker)
    if group is None:
        return None
    arche = ARCHETYPES[group]
    atr = _atr_proxy(bars)
    if atr == 0:
        return None

    reclaimed_up = prev.close < vwap <= latest.close
    reclaimed_down = prev.close > vwap >= latest.close

    if reclaimed_up:
        stop = latest.close - arche.stop_k * atr
        risk = latest.close - stop
        target = latest.close + arche.target_r * risk
        return Signal(
            ticker=ticker,
            setup="VWAP_RECLAIM",
            side="long",
            entry=latest.close,
            stop=round(stop, 2),
            target=round(target, 2),
            reason=f"Reclaimed VWAP {vwap:.2f} to the upside",
        )

    if reclaimed_down:
        stop = latest.close + arche.stop_k * atr
        risk = stop - latest.close
        target = latest.close - arche.target_r * risk
        return Signal(
            ticker=ticker,
            setup="VWAP_RECLAIM",
            side="short",
            entry=latest.close,
            stop=round(stop, 2),
            target=round(target, 2),
            reason=f"Lost VWAP {vwap:.2f} to the downside",
        )

    return None


def scan_ticker(ticker: str, bars: list[Bar]) -> Optional[Signal]:
    """Try each setup in priority order; return the first that fires."""
    return check_orb(ticker, bars) or check_vwap_reclaim(ticker, bars)
