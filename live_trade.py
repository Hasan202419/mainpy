"""
live_trade.py
=============
Wires scanner.py + portfolio.py's risk gate to the real
trading.try2bfunded.com account via web_broker.py, instead of the paper-only
flow in run_scan.py.

Two commands:

    python3 live_trade.py inspect TICKER [--exchange NYSE]
        Read-only. Logs in, opens the symbol page, saves its HTML +
        screenshot to inspect_dump/. Use this FIRST to fill in the real
        selectors in web_broker.SELECTORS -- do this before anything else.

    python3 live_trade.py scan bars.json [--live] [--exchange NYSE]
        Runs one scan cycle exactly like run_scan.py (same scanner.py
        signals, same portfolio.py risk gate: daily loss limit, max
        drawdown, one-slot-per-archetype-group), but instead of a
        simulated fill it calls web_broker.place_order() for real.

        Without --live: every action is a dry run -- it prints exactly
        what order it WOULD submit and does not touch the real order
        form's submit button. This is the default on purpose.

        With --live: it actually submits real orders on your real
        Try2BFunded account. It will refuse to run until
        web_broker.SELECTORS['confirmed'] is True, and it asks for a
        typed confirmation before doing anything.

This script assumes it is being run on a machine with real network access
to trading.try2bfunded.com -- it will not work from the sandbox this repo
was authored in (that domain is blocked there).
"""

from __future__ import annotations

import argparse
import sys

from portfolio import PaperPortfolio
from run_scan import load_bars
from scanner import scan_ticker
from web_broker import SELECTORS, SelectorsNotConfirmed, Try2BFundedWebBroker


def cmd_inspect(args: argparse.Namespace) -> None:
    with Try2BFundedWebBroker(headless=args.headed is False) as broker:
        path = broker.inspect(args.ticker, args.exchange)
    print(f"Saved page HTML + screenshot under inspect_dump/ (see {path}).")
    print(
        "Next: open that HTML, find the real selectors for login, quote, "
        "and the order form, and fill them into web_broker.SELECTORS. Set "
        "SELECTORS['confirmed'] = True only once every entry is verified."
    )


def cmd_scan(args: argparse.Namespace) -> None:
    if args.live:
        if not SELECTORS["confirmed"]:
            raise SelectorsNotConfirmed(
                "Refusing --live: web_broker.SELECTORS is not confirmed yet. "
                "Run `inspect` first."
            )
        typed = input(
            "Type EXACTLY 'PLACE REAL ORDERS' to confirm this will submit "
            "real trades on your real Try2BFunded account: "
        )
        if typed != "PLACE REAL ORDERS":
            print("Confirmation text did not match -- aborting, nothing was sent.")
            sys.exit(1)

    bars_by_ticker = load_bars(args.bars_path)
    portfolio = PaperPortfolio()  # risk-gate bookkeeping stays local + auditable

    with Try2BFundedWebBroker(headless=not args.headed) as broker:
        broker.login()

        mark_prices = {}
        for ticker in bars_by_ticker:
            try:
                mark_prices[ticker] = broker.get_quote(ticker, args.exchange).price
            except Exception as e:  # noqa: BLE001 -- surface and keep scanning
                print(f"[WARN] could not fetch live quote for {ticker}: {e}")

        closed = portfolio.mark_and_check_exits(mark_prices)
        for t in closed:
            tag = "TARGET HIT" if t.reason == "target" else "STOP HIT"
            print(f"[{tag}] {t.ticker} {t.side} closed @ {t.exit_price:.2f} -> P&L {t.pnl:+.2f}")

        for ticker, bars in bars_by_ticker.items():
            if not bars or ticker not in mark_prices:
                continue
            signal = scan_ticker(ticker, bars)
            if signal is None:
                continue

            ok, why = portfolio.can_open(signal.ticker, mark_prices)
            if not ok:
                print(f"[SKIPPED] {signal.ticker} {signal.setup} {signal.side} -- {why}")
                continue

            result = broker.place_order(
                ticker=signal.ticker,
                side=signal.side,
                qty=portfolio.equity(mark_prices) * 0.0025 / abs(signal.entry - signal.stop),
                stop_price=signal.stop,
                target_price=signal.target,
                dry_run=not args.live,
            )
            if result["submitted"]:
                portfolio.open_position(
                    ticker=signal.ticker,
                    side=signal.side,
                    entry_price=signal.entry,
                    stop_price=signal.stop,
                    target_price=signal.target,
                )

        equity = portfolio.equity(mark_prices)
        print("-" * 72)
        print(f"Equity (paper-tracked): ${equity:,.2f}   "
              f"Open positions: {len(portfolio.positions)}   "
              f"Mode: {'LIVE' if args.live else 'DRY-RUN'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_inspect = sub.add_parser("inspect", help="Read-only: dump a symbol page's HTML")
    p_inspect.add_argument("ticker")
    p_inspect.add_argument("--exchange", default="NYSE")
    p_inspect.add_argument("--headed", action="store_true", help="Show the browser window")
    p_inspect.set_defaults(func=cmd_inspect)

    p_scan = sub.add_parser("scan", help="Run one scan cycle against live quotes")
    p_scan.add_argument("bars_path")
    p_scan.add_argument("--exchange", default="NYSE")
    p_scan.add_argument("--headed", action="store_true", help="Show the browser window")
    p_scan.add_argument(
        "--live", action="store_true",
        help="Actually submit real orders. Default is dry-run.",
    )
    p_scan.set_defaults(func=cmd_scan)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
