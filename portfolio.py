"""
portfolio.py
============
A fully-simulated ("paper") trading portfolio. No real broker, no real
money, no real order is ever touched by this module -- it only mutates a
local JSON state file. This is the safe sandbox for testing the scanner +
automatic-execution flow end to end.

Mirrors the real Try2BFunded account's starting size ($30,000) and risk
rules (2% daily loss limit, 4% max drawdown, one-slot-per-archetype-group)
so behaviour learned here transfers directly to the real account -- where
Hasan, not this code, presses the final button.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from archetypes import ARCHETYPES, group_of

STATE_PATH = os.path.join(os.path.dirname(__file__), "state.json")

STARTING_BALANCE = 30_000.00
DAILY_LOSS_LIMIT_PCT = 0.02      # Try2BFunded qualification rule
MAX_DRAWDOWN_PCT = 0.04          # Try2BFunded qualification rule
DEFAULT_RISK_PCT = 0.0025        # 0.25% of equity per trade (paper's default)


@dataclass
class Position:
    ticker: str
    side: str            # "long" | "short"
    qty: float
    entry_price: float
    stop_price: float
    target_price: float
    group: str
    opened_at: str


@dataclass
class Trade:
    ticker: str
    side: str
    qty: float
    entry_price: float
    exit_price: float
    pnl: float
    reason: str           # "target" | "stop" | "manual"
    opened_at: str
    closed_at: str


class PaperPortfolio:
    """
    JSON-file-backed simulated account. Every method here only edits the
    local state.json -- nothing ever reaches a real broker or API.
    """

    def __init__(self, path: str = STATE_PATH):
        self.path = path
        if os.path.exists(path):
            self._load()
        else:
            self.cash = STARTING_BALANCE
            self.start_of_day_equity = STARTING_BALANCE
            self.positions: dict[str, Position] = {}
            self.trade_log: list[Trade] = []
            self._save()

    # ------------------------------------------------------------------ #
    # persistence
    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        with open(self.path, "r") as f:
            data = json.load(f)
        self.cash = data["cash"]
        self.start_of_day_equity = data["start_of_day_equity"]
        self.positions = {
            k: Position(**v) for k, v in data["positions"].items()
        }
        self.trade_log = [Trade(**t) for t in data["trade_log"]]

    def _save(self) -> None:
        data = {
            "cash": self.cash,
            "start_of_day_equity": self.start_of_day_equity,
            "positions": {k: asdict(v) for k, v in self.positions.items()},
            "trade_log": [asdict(t) for t in self.trade_log],
        }
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    # ------------------------------------------------------------------ #
    # derived state
    # ------------------------------------------------------------------ #
    def equity(self, mark_prices: dict[str, float]) -> float:
        """
        Cash + unrealized P&L of open positions.

        NOTE: cash is never debited/credited for a position's entry notional
        (entry_price * qty) -- that models this as a margin/futures-style P&L
        account, which matches how mark_and_check_exits() already realizes
        P&L (self.cash += pnl) on close. Adding entry_price*qty here as well
        double-counted the notional on top of untouched cash and inflated
        equity by ~entry_price*qty per open position -- caught and fixed
        2026-08-14 before the first real demo run.
        """
        value = self.cash
        for pos in self.positions.values():
            px = mark_prices.get(pos.ticker, pos.entry_price)
            sign = 1 if pos.side == "long" else -1
            value += sign * (px - pos.entry_price) * pos.qty
        return value

    def daily_pnl_pct(self, mark_prices: dict[str, float]) -> float:
        return (self.equity(mark_prices) - self.start_of_day_equity) / self.start_of_day_equity

    def group_open_count(self, group: str) -> int:
        return sum(1 for p in self.positions.values() if p.group == group)

    # ------------------------------------------------------------------ #
    # risk gate -- called before every simulated entry
    # ------------------------------------------------------------------ #
    def can_open(self, ticker: str, mark_prices: dict[str, float]) -> tuple[bool, str]:
        group = group_of(ticker)
        if group is None:
            return False, f"{ticker} is not in the classified 29-ticker universe"

        if ticker in self.positions:
            return False, f"{ticker} already has an open paper position"

        max_slots = ARCHETYPES[group].max_concurrent
        if self.group_open_count(group) >= max_slots:
            return False, (
                f"Group {group} ({ARCHETYPES[group].name}) already has "
                f"{max_slots} open slot(s) used -- correlation-risk cap reached"
            )

        if self.daily_pnl_pct(mark_prices) <= -DAILY_LOSS_LIMIT_PCT:
            return False, "Daily loss limit (2%) reached -- no new paper entries today"

        equity = self.equity(mark_prices)
        if equity <= STARTING_BALANCE * (1 - MAX_DRAWDOWN_PCT):
            return False, "Max drawdown (4%) breached -- paper account halted"

        return True, "OK"

    # ------------------------------------------------------------------ #
    # simulated execution (paper only)
    # ------------------------------------------------------------------ #
    def open_position(
        self,
        ticker: str,
        side: str,
        entry_price: float,
        stop_price: float,
        target_price: float,
        risk_pct: float = DEFAULT_RISK_PCT,
    ) -> Position:
        group = group_of(ticker)
        risk_dollars = self.equity({}) * risk_pct
        stop_distance = abs(entry_price - stop_price)
        qty = round(risk_dollars / stop_distance, 2) if stop_distance > 0 else 0

        pos = Position(
            ticker=ticker,
            side=side,
            qty=qty,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
            group=group,
            opened_at=datetime.now(timezone.utc).isoformat(),
        )
        self.positions[ticker] = pos
        self._save()
        return pos

    def mark_and_check_exits(self, mark_prices: dict[str, float]) -> list[Trade]:
        """
        Check every open paper position against its stop/target using the
        supplied live prices, and simulate a fill if either level is
        touched. Returns the list of trades closed this call.
        """
        closed = []
        for ticker, pos in list(self.positions.items()):
            px = mark_prices.get(ticker)
            if px is None:
                continue

            hit_target = (pos.side == "long" and px >= pos.target_price) or (
                pos.side == "short" and px <= pos.target_price
            )
            hit_stop = (pos.side == "long" and px <= pos.stop_price) or (
                pos.side == "short" and px >= pos.stop_price
            )

            if hit_target or hit_stop:
                exit_price = pos.target_price if hit_target else pos.stop_price
                sign = 1 if pos.side == "long" else -1
                pnl = sign * (exit_price - pos.entry_price) * pos.qty
                self.cash += pnl
                trade = Trade(
                    ticker=ticker,
                    side=pos.side,
                    qty=pos.qty,
                    entry_price=pos.entry_price,
                    exit_price=exit_price,
                    pnl=round(pnl, 2),
                    reason="target" if hit_target else "stop",
                    opened_at=pos.opened_at,
                    closed_at=datetime.now(timezone.utc).isoformat(),
                )
                self.trade_log.append(trade)
                closed.append(trade)
                del self.positions[ticker]

        if closed:
            self._save()
        return closed
