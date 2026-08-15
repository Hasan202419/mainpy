"""
web_broker.py
=============
Playwright wrapper around the trading.try2bfunded.com WEB interface, used
only because (as far as we could find) Try2BFunded does not expose a public
REST/FIX API -- the account is driven through its web UI, so this module
drives that UI with a real (headless or headed) browser instead.

READ THIS BEFORE TOUCHING SELECTORS
------------------------------------
This file was written WITHOUT ever loading a real trading.try2bfunded.com
page -- the sandbox this was authored in has that domain blocked at the
network layer, so nobody has confirmed the CSS/text selectors below against
the actual DOM. Every value in SELECTORS is a labeled placeholder guess.

Run in `inspect` mode first (see bottom of this file / README) to capture
the real page HTML, then fill in SELECTORS from that HTML before this is
trusted to click anything -- especially place_order(). Until SELECTORS is
confirmed, order-placing calls refuse to run (see _require_selectors()).

Safety model
------------
- login() and get_quote() are read-only.
- place_order() defaults to dry_run=True: it fills the order form, LOGS
  exactly what it would submit, and returns WITHOUT clicking the final
  submit/confirm button. Only dry_run=False actually submits -- and that
  path is meant to be reached exclusively through live_trade.py's --live
  flag, never called ad hoc.
- Credentials are read from environment variables only (see .env.example).
  Never hardcode a login/password in this file or pass one on a command
  line where it would land in shell history.
"""

from __future__ import annotations

import datetime
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ.get("TRY2BFUNDED_BASE_URL", "https://trading.try2bfunded.com")
EMAIL = os.environ.get("TRY2BFUNDED_EMAIL")
PASSWORD = os.environ.get("TRY2BFUNDED_PASSWORD")

# --------------------------------------------------------------------- #
# PLACEHOLDER selectors -- confirm every single one against real page
# HTML (see `inspect` mode) before relying on this file for anything that
# clicks a real button.
# --------------------------------------------------------------------- #
SELECTORS = {
    "confirmed": False,  # flip to True only after every selector below has
                          # been checked against the live DOM.
    "login": {
        "email_input": "PLACEHOLDER input[name='email']",
        "password_input": "PLACEHOLDER input[name='password']",
        "submit_button": "PLACEHOLDER button[type='submit']",
        "logged_in_marker": "PLACEHOLDER text=Dashboard",
    },
    "quote": {
        # On a symbol page like /profile/NYSE-GRMN
        "last_price": "PLACEHOLDER [data-testid='last-price']",
    },
    "order_form": {
        "side_buy_button": "PLACEHOLDER button:has-text('Buy')",
        "side_sell_button": "PLACEHOLDER button:has-text('Sell')",
        "qty_input": "PLACEHOLDER input[name='quantity']",
        "order_type_select": "PLACEHOLDER select[name='orderType']",
        "limit_price_input": "PLACEHOLDER input[name='limitPrice']",
        "stop_loss_input": "PLACEHOLDER input[name='stopLoss']",
        "take_profit_input": "PLACEHOLDER input[name='takeProfit']",
        "review_button": "PLACEHOLDER button:has-text('Review Order')",
        "confirm_submit_button": "PLACEHOLDER button:has-text('Place Order')",
        "order_confirmation_marker": "PLACEHOLDER text=Order placed",
    },
}


class SelectorsNotConfirmed(RuntimeError):
    pass


def _require_selectors() -> None:
    if not SELECTORS["confirmed"]:
        raise SelectorsNotConfirmed(
            "web_broker.SELECTORS has not been confirmed against the real "
            "trading.try2bfunded.com DOM yet. Run inspect mode, fill in the "
            "real selectors, set SELECTORS['confirmed']=True, then retry. "
            "Refusing to guess-click a live order form."
        )


@dataclass
class Quote:
    ticker: str
    price: float
    fetched_at: str


class Try2BFundedWebBroker:
    """
    Thin Playwright wrapper. Import and use only from your own machine --
    this needs unblocked network access to trading.try2bfunded.com, which
    the Claude sandbox this repo was built in does NOT have.
    """

    def __init__(self, headless: bool = True):
        if not EMAIL or not PASSWORD:
            raise RuntimeError(
                "TRY2BFUNDED_EMAIL / TRY2BFUNDED_PASSWORD not set. "
                "Copy .env.example to .env and fill them in -- never pass "
                "credentials as CLI args."
            )
        self._headless = headless
        self._pw = None
        self._browser = None
        self._page = None

    def __enter__(self) -> "Try2BFundedWebBroker":
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self._headless)
        self._page = self._browser.new_page()
        return self

    def __exit__(self, *exc) -> None:
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    # ------------------------------------------------------------------ #
    # read-only
    # ------------------------------------------------------------------ #
    def login(self) -> None:
        s = SELECTORS["login"]
        self._page.goto(BASE_URL)
        self._page.fill(s["email_input"], EMAIL)
        self._page.fill(s["password_input"], PASSWORD)
        self._page.click(s["submit_button"])
        self._page.wait_for_selector(s["logged_in_marker"], timeout=30_000)

    def get_quote(self, ticker: str, exchange: str = "NYSE") -> Quote:
        s = SELECTORS["quote"]
        self._page.goto(f"{BASE_URL}/profile/{exchange}-{ticker}")
        el = self._page.wait_for_selector(s["last_price"], timeout=15_000)
        price = float(el.inner_text().replace(",", "").replace("$", "").strip())
        return Quote(
            ticker=ticker,
            price=price,
            fetched_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

    def inspect(self, ticker: str, exchange: str, out_dir: str = "inspect_dump") -> str:
        """
        Read-only reconnaissance: log in, load the symbol page, and dump its
        HTML to disk so real selectors can be filled into SELECTORS above
        without ever guessing. Places no order, clicks nothing beyond login.
        """
        Path(out_dir).mkdir(exist_ok=True)
        self.login()
        self._page.goto(f"{BASE_URL}/profile/{exchange}-{ticker}")
        self._page.wait_for_load_state("networkidle")
        out_path = Path(out_dir) / f"{exchange}-{ticker}.html"
        out_path.write_text(self._page.content())
        shot_path = Path(out_dir) / f"{exchange}-{ticker}.png"
        self._page.screenshot(path=str(shot_path), full_page=True)
        return str(out_path)

    # ------------------------------------------------------------------ #
    # order placement -- gated behind confirmed selectors + explicit
    # dry_run=False
    # ------------------------------------------------------------------ #
    def place_order(
        self,
        ticker: str,
        side: Literal["long", "short"],
        qty: float,
        stop_price: Optional[float] = None,
        target_price: Optional[float] = None,
        dry_run: bool = True,
    ) -> dict:
        _require_selectors()
        s = SELECTORS["order_form"]

        action = {
            "ticker": ticker,
            "side": side,
            "qty": qty,
            "stop_price": stop_price,
            "target_price": target_price,
            "dry_run": dry_run,
            "requested_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        if dry_run:
            print(f"[DRY-RUN] would place order: {action}")
            return {**action, "submitted": False}

        # Live path -- only reachable once SELECTORS['confirmed'] is True.
        self._page.click(s["side_buy_button"] if side == "long" else s["side_sell_button"])
        self._page.fill(s["qty_input"], str(qty))
        if stop_price is not None:
            self._page.fill(s["stop_loss_input"], str(stop_price))
        if target_price is not None:
            self._page.fill(s["take_profit_input"], str(target_price))
        self._page.click(s["review_button"])
        self._page.click(s["confirm_submit_button"])
        self._page.wait_for_selector(s["order_confirmation_marker"], timeout=15_000)

        print(f"[LIVE] order submitted: {action}")
        return {**action, "submitted": True}
