"""
run_scan.py
===========
Orchestrator for one scan cycle of the PAPER (simulated) portfolio.

Usage:
    python run_scan.py bars.json

Where bars.json has the shape:
    {
      "TSLA": [{"time": "...", "open": .., "high": .., "low": .., "close": .., "volume": ..}, ...],
      "NVDA": [...],
      ...
    }

This script performs NO network calls and touches NO real broker -- bar
data is fetched separately (by Claude, via the IBKR market-data tools) and
handed to this script as a plain JSON file. That keeps a hard, auditable
wall between "reading market data" (fine, read-only) and "this code could
possibly place a live order" (impossible -- there is no broker client
imported anywhere in this package).
"""

from __future__ import annotations

import json
import sys

from portfolio import PaperPortfolio
from scanner import Bar, scan_ticker


def load_bars(path: str) -> dict[str, list[Bar]]:
    with open(path, "r") as f:
        raw = json.load(f)
    return {
        ticker: [Bar(**b) for b in bar_list]
        for ticker, bar_list in raw.items()
    }


def main(bars_path: str) -> None:
    bars_by_ticker = load_bars(bars_path)
    mark_prices = {t: bars[-1].close for t, bars in bars_by_ticker.items() if bars}

    portfolio = PaperPortfolio()

    print("=" * 72)
    print("PAPER PORTFOLIO -- scan cycle")
    print("=" * 72)

    # 1) check existing positions for stop/target hits first
    closed = portfolio.mark_and_check_exits(mark_prices)
    for t in closed:
        tag = "TARGET HIT" if t.reason == "target" else "STOP HIT"
        print(f"[{tag}] {t.ticker} {t.side} closed @ {t.exit_price:.2f} -> P&L {t.pnl:+.2f}")

    # 2) scan for new signals
    any_signal = False
    for ticker, bars in bars_by_ticker.items():
        if not bars:
            continue
        signal = scan_ticker(ticker, bars)
        if signal is None:
            continue

        any_signal = True
        ok, why = portfolio.can_open(signal.ticker, mark_prices)
        if not ok:
            print(f"[SKIPPED] {signal.ticker} {signal.setup} {signal.side} -- {why}")
            continue

        pos = portfolio.open_position(
            ticker=signal.ticker,
            side=signal.side,
            entry_price=signal.entry,
            stop_price=signal.stop,
            target_price=signal.target,
        )
        print(
            f"[OPENED] {pos.ticker} {pos.side} x{pos.qty} @ {pos.entry_price:.2f} "
            f"(stop {pos.stop_price:.2f} / target {pos.target_price:.2f}) "
            f"-- {signal.setup}: {signal.reason}"
        )

    if not any_signal:
        print("No setups fired this cycle.")

    equity = portfolio.equity(mark_prices)
    day_pnl_pct = portfolio.daily_pnl_pct(mark_prices) * 100
    print("-" * 72)
    print(f"Equity: ${equity:,.2f}   Day P&L: {day_pnl_pct:+.2f}%   "
          f"Open positions: {len(portfolio.positions)}   "
          f"Closed trades total: {len(portfolio.trade_log)}")
    print("=" * 72)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python run_scan.py bars.json")
        sys.exit(1)
    main(sys.argv[1])
