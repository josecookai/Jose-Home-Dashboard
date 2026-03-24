"""
pelosi_tracker.py — Track Nancy Pelosi's AMZN LEAPS position and calculate daily P&L.

Position details (configurable via env vars)
---------------------------------------------
LEAPS_TICKER       = AMZN           (default)
LEAPS_STRIKE       = 120            (default)
LEAPS_EXPIRY       = 2027-01-15     (default, YYYY-MM-DD)
LEAPS_CONTRACTS    = 20             (default)
LEAPS_ENTRY_PRICE  = 25.00          (default, per-contract premium in dollars)

Valuation model
---------------
Intrinsic value : max(0, price - strike) × 100 × contracts
Time value      : 0.3 × sqrt(days_to_expiry / 365) × price × 100 × contracts
Est. total value: intrinsic + time_value
P&L             : est_value − entry_cost   where entry_cost = entry_price × 100 × contracts

Output tables (Supabase)
------------------------
market_positions   type='leaps'   — daily snapshot
module_status                      — run result
"""

import logging
import math
import os
from datetime import date, datetime, timezone
from typing import Any

from dotenv import load_dotenv

from common import save_to_supabase, send_telegram, update_module_status

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pelosi_tracker")

MODULE_NAME = "pelosi_tracker"

# ---------------------------------------------------------------------------
# Position configuration
# ---------------------------------------------------------------------------

LEAPS_TICKER: str = os.environ.get("LEAPS_TICKER", "AMZN")
LEAPS_STRIKE: float = float(os.environ.get("LEAPS_STRIKE", "120"))
LEAPS_EXPIRY: str = os.environ.get("LEAPS_EXPIRY", "2027-01-15")
LEAPS_CONTRACTS: int = int(os.environ.get("LEAPS_CONTRACTS", "20"))
LEAPS_ENTRY_PRICE: float = float(os.environ.get("LEAPS_ENTRY_PRICE", "25.00"))

# ---------------------------------------------------------------------------
# Price fetching
# ---------------------------------------------------------------------------


def fetch_price(ticker: str) -> float | None:
    """
    Fetch the current price for *ticker* using yfinance.

    Falls back to Yahoo Finance quote API if yfinance fast_info returns None.
    Returns the price as a float, or None on failure.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance is not installed. Run: pip install yfinance")
        return None

    try:
        t = yf.Ticker(ticker)
        price: float | None = getattr(t.fast_info, "last_price", None)
        if price is None:
            hist = t.history(period="1d")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
        if price is not None:
            logger.info("Fetched %s price via yfinance: $%.2f", ticker, price)
            return float(price)
    except Exception as exc:  # noqa: BLE001
        logger.warning("yfinance fetch failed for %s: %s — trying fallback", ticker, exc)

    # Fallback: Yahoo Finance quote API (no auth required)
    try:
        import requests  # noqa: PLC0415

        url = "https://query1.finance.yahoo.com/v8/finance/chart/" + ticker
        headers = {"User-Agent": "Mozilla/5.0 (compatible; pelosi-tracker/1.0)"}
        resp = requests.get(url, headers=headers, params={"interval": "1d", "range": "1d"}, timeout=10)
        resp.raise_for_status()
        payload = resp.json()
        price = payload["chart"]["result"][0]["meta"]["regularMarketPrice"]
        logger.info("Fetched %s price via Yahoo Finance API: $%.2f", ticker, price)
        return float(price)
    except Exception as exc:  # noqa: BLE001
        logger.error("Yahoo Finance fallback also failed for %s: %s", ticker, exc)
        return None


# ---------------------------------------------------------------------------
# Valuation
# ---------------------------------------------------------------------------


def estimate_leaps_value(
    price: float,
    strike: float,
    expiry_str: str,
    contracts: int,
) -> dict[str, float]:
    """
    Estimate the current value of a LEAPS call position.

    Returns a dict with keys:
        days_to_expiry  — calendar days remaining
        intrinsic_value — max(0, price - strike) × 100 × contracts
        time_value      — rough estimate of extrinsic value
        total_value     — intrinsic + time_value
    """
    expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    today = date.today()
    days_to_expiry = max(0, (expiry_date - today).days)

    intrinsic_per_share = max(0.0, price - strike)
    intrinsic_value = intrinsic_per_share * 100 * contracts

    # Rough time-value estimate:
    #   TV = 0.3 × sqrt(days / 365) × price × 100 × contracts
    # This is a simplified model (no IV input) intended as a ballpark only.
    time_value = 0.3 * math.sqrt(days_to_expiry / 365) * price * 100 * contracts

    total_value = intrinsic_value + time_value

    return {
        "days_to_expiry": float(days_to_expiry),
        "intrinsic_value": round(intrinsic_value, 2),
        "time_value": round(time_value, 2),
        "total_value": round(total_value, 2),
    }


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def format_report(
    today: str,
    price: float,
    strike: float,
    expiry: str,
    contracts: int,
    entry_price: float,
    valuation: dict[str, float],
) -> str:
    """
    Build the Markdown-formatted Telegram report.

    Returns the formatted string.
    """
    days = int(valuation["days_to_expiry"])
    entry_cost = entry_price * 100 * contracts
    est_value = valuation["total_value"]
    pnl = est_value - entry_cost
    pnl_pct = (pnl / entry_cost * 100) if entry_cost else 0.0

    lines = [
        "📊 *Pelosi AMZN LEAPS Tracker*",
        f"Date: {today}",
        "",
        f"AMZN Price: ${price:,.2f}",
        f"Strike: ${strike:,.0f} | Expiry: {expiry}",
        f"Days to Expiry: {days}",
        "",
        f"Position: {contracts} contracts",
        f"Entry Cost: ${entry_cost:,.0f}",
        f"Est. Value: ${est_value:,.0f}",
        f"P&L: ${pnl:+,.0f} ({pnl_pct:+.1f}%)",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run() -> None:
    today = date.today().isoformat()
    logger.info(
        "Starting Pelosi LEAPS tracker for %s | %s $%.0f call exp %s × %d contracts",
        today,
        LEAPS_TICKER,
        LEAPS_STRIKE,
        LEAPS_EXPIRY,
        LEAPS_CONTRACTS,
    )

    # 1. Fetch current price
    price = fetch_price(LEAPS_TICKER)
    if price is None:
        msg = f"Could not fetch {LEAPS_TICKER} price."
        logger.error(msg)
        update_module_status(MODULE_NAME, "error", msg)
        return

    # 2. Estimate position value
    valuation = estimate_leaps_value(
        price=price,
        strike=LEAPS_STRIKE,
        expiry_str=LEAPS_EXPIRY,
        contracts=LEAPS_CONTRACTS,
    )

    entry_cost = LEAPS_ENTRY_PRICE * 100 * LEAPS_CONTRACTS
    est_value = valuation["total_value"]
    pnl = est_value - entry_cost
    pnl_pct = (pnl / entry_cost * 100) if entry_cost else 0.0

    logger.info(
        "Valuation — intrinsic: $%.0f | time: $%.0f | total: $%.0f | P&L: $%+.0f (%.1f%%)",
        valuation["intrinsic_value"],
        valuation["time_value"],
        est_value,
        pnl,
        pnl_pct,
    )

    # 3. Format report
    report = format_report(
        today=today,
        price=price,
        strike=LEAPS_STRIKE,
        expiry=LEAPS_EXPIRY,
        contracts=LEAPS_CONTRACTS,
        entry_price=LEAPS_ENTRY_PRICE,
        valuation=valuation,
    )
    logger.info("Report:\n%s", report)

    # 4. Send Telegram notification
    send_telegram(report)

    # 5. Save to market_positions
    position_row: dict[str, Any] = {
        "date": today,
        "type": "leaps",
        "ticker": LEAPS_TICKER,
        "action": "hold",
        "details": {
            "price": round(price, 2),
            "strike": LEAPS_STRIKE,
            "expiry": LEAPS_EXPIRY,
            "contracts": LEAPS_CONTRACTS,
            "entry_price": LEAPS_ENTRY_PRICE,
            "entry_cost": round(entry_cost, 2),
            "intrinsic_value": valuation["intrinsic_value"],
            "time_value": valuation["time_value"],
            "est_value": est_value,
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "days_to_expiry": int(valuation["days_to_expiry"]),
        },
        "summary": report,
    }

    result = save_to_supabase(
        table="market_positions",
        data=position_row,
        unique_on=["date", "type", "ticker"],
    )
    if result:
        logger.info("Position snapshot saved to market_positions.")
    else:
        logger.warning("Failed to save position snapshot to Supabase (may still have been written).")

    # 6. Update module status
    status_msg = (
        f"{LEAPS_TICKER} ${LEAPS_STRIKE:.0f} call exp {LEAPS_EXPIRY} — "
        f"price: ${price:.2f} | est value: ${est_value:,.0f} | "
        f"P&L: ${pnl:+,.0f} ({pnl_pct:+.1f}%)"
    )
    update_module_status(MODULE_NAME, "success", status_msg)
    logger.info("pelosi_tracker finished successfully.")


if __name__ == "__main__":
    run()
