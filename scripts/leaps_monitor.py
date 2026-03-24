"""
leaps_monitor.py — Monitor LEAPS options positions and Congressional trading.

Data sources
------------
LEAPS   : yfinance (AMZN options chain + underlying price)
Congress: House Stock Watcher public API
           https://house-stock-watcher-data.s3-us-east-2.amazonaws.com/data/all_transactions.json

Configuration (env vars / .env file)
-------------------------------------
LEAPS_TICKER  = AMZN          (default)
LEAPS_STRIKE  = 200           (required)
LEAPS_EXPIRY  = 2026-01-16    (required, YYYY-MM-DD)

Output tables (Supabase)
------------------------
market_positions   type='leaps'   — LEAPS snapshot
market_positions   type='congress'— Congressional trades (last 7 days)
module_status                      — run result
"""

import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv

from common import save_to_supabase, update_module_status, send_telegram

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("leaps_monitor")

MODULE_NAME = "leaps_monitor"

# ---------------------------------------------------------------------------
# LEAPS config
# ---------------------------------------------------------------------------

LEAPS_TICKER = os.environ.get("LEAPS_TICKER", "AMZN")
LEAPS_STRIKE_RAW = os.environ.get("LEAPS_STRIKE", "")
LEAPS_EXPIRY = os.environ.get("LEAPS_EXPIRY", "2026-01-16")

# Congressional trading
CONGRESS_API_URL = (
    "https://house-stock-watcher-data.s3-us-east-2.amazonaws.com"
    "/data/all_transactions.json"
)
CONGRESS_LOOKBACK_DAYS = 7


# ---------------------------------------------------------------------------
# LEAPS monitoring
# ---------------------------------------------------------------------------

def fetch_leaps_data() -> dict[str, Any] | None:
    """
    Fetch AMZN current price and the closest matching call option for the
    configured strike / expiry using yfinance.

    Returns a dict suitable for inserting into market_positions, or None on
    failure.
    """
    try:
        import yfinance as yf  # optional dependency — import lazily
    except ImportError:
        logger.error(
            "yfinance is not installed. Run: pip install yfinance"
        )
        return None

    if not LEAPS_STRIKE_RAW:
        logger.error(
            "LEAPS_STRIKE is not set. Add it to your .env file (e.g. LEAPS_STRIKE=200)."
        )
        return None

    try:
        strike = float(LEAPS_STRIKE_RAW)
    except ValueError:
        logger.error("LEAPS_STRIKE='%s' is not a valid number.", LEAPS_STRIKE_RAW)
        return None

    logger.info(
        "Fetching LEAPS data: %s $%.0f call expiring %s",
        LEAPS_TICKER, strike, LEAPS_EXPIRY,
    )

    try:
        ticker = yf.Ticker(LEAPS_TICKER)

        # Current underlying price
        info = ticker.fast_info
        current_price: float | None = getattr(info, "last_price", None)
        if current_price is None:
            hist = ticker.history(period="1d")
            current_price = float(hist["Close"].iloc[-1]) if not hist.empty else None

        # Options chain for the target expiry date
        available_expiries: list[str] = list(ticker.options)
        if not available_expiries:
            logger.warning("No options expiry dates available for %s.", LEAPS_TICKER)
            option_details: dict[str, Any] = {}
        else:
            # Pick the nearest available expiry on or after LEAPS_EXPIRY
            target = datetime.strptime(LEAPS_EXPIRY, "%Y-%m-%d").date()
            chosen_expiry: str | None = None
            for exp_str in sorted(available_expiries):
                exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                if exp_date >= target:
                    chosen_expiry = exp_str
                    break

            if chosen_expiry is None:
                chosen_expiry = available_expiries[-1]
                logger.warning(
                    "Target expiry %s not available; using latest: %s",
                    LEAPS_EXPIRY, chosen_expiry,
                )

            calls = ticker.option_chain(chosen_expiry).calls
            # Find the row closest to our strike price
            calls = calls.copy()
            calls["strike_diff"] = (calls["strike"] - strike).abs()
            best = calls.loc[calls["strike_diff"].idxmin()]

            option_details = {
                "expiry_used": chosen_expiry,
                "strike_used": float(best.get("strike", strike)),
                "last_price": float(best.get("lastPrice", 0)),
                "bid": float(best.get("bid", 0)),
                "ask": float(best.get("ask", 0)),
                "volume": int(best.get("volume", 0)) if best.get("volume") == best.get("volume") else 0,
                "open_interest": int(best.get("openInterest", 0)) if best.get("openInterest") == best.get("openInterest") else 0,
                "implied_volatility": round(float(best.get("impliedVolatility", 0)), 4),
            }

        today = date.today().isoformat()
        summary = (
            f"{LEAPS_TICKER} ${strike:.0f} call exp {LEAPS_EXPIRY} — "
            f"underlying: ${current_price:.2f}" if current_price else
            f"{LEAPS_TICKER} ${strike:.0f} call exp {LEAPS_EXPIRY}"
        )
        if option_details.get("last_price"):
            summary += f" | option last: ${option_details['last_price']:.2f}"

        return {
            "date": today,
            "type": "leaps",
            "ticker": LEAPS_TICKER,
            "action": "monitor",
            "details": {
                "underlying_price": round(current_price, 2) if current_price else None,
                "target_strike": strike,
                "target_expiry": LEAPS_EXPIRY,
                **option_details,
            },
            "summary": summary,
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("Error fetching LEAPS data: %s", exc, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Congressional trading
# ---------------------------------------------------------------------------

def _parse_congress_date(date_str: str) -> date | None:
    """Try multiple date formats used by the House Stock Watcher API."""
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    return None


def fetch_congress_trades() -> list[dict[str, Any]]:
    """
    Download all House transactions and return those from the last
    CONGRESS_LOOKBACK_DAYS days as market_positions rows.
    """
    import requests  # noqa: PLC0415 (top-level import already in common; local here for clarity)

    logger.info("Fetching Congressional trades from House Stock Watcher…")

    try:
        response = requests.get(CONGRESS_API_URL, timeout=30)
        response.raise_for_status()
        transactions: list[dict[str, Any]] = response.json()
    except requests.HTTPError as exc:
        logger.error(
            "HTTP error fetching Congress data: %s — %s",
            exc.response.status_code,
            exc.response.text[:300],
        )
        return []
    except requests.RequestException as exc:
        logger.error("Network error fetching Congress data: %s", exc)
        return []
    except ValueError as exc:
        logger.error("Failed to parse Congress JSON: %s", exc)
        return []

    cutoff = date.today() - timedelta(days=CONGRESS_LOOKBACK_DAYS)
    rows: list[dict[str, Any]] = []

    for tx in transactions:
        tx_date_str = tx.get("transaction_date") or tx.get("disclosure_date") or ""
        tx_date = _parse_congress_date(tx_date_str)
        if tx_date is None or tx_date < cutoff:
            continue

        representative: str = tx.get("representative", "Unknown").strip()
        ticker: str = (tx.get("ticker") or "").strip().upper()
        tx_type: str = (tx.get("type") or "unknown").strip().lower()
        amount: str = tx.get("amount") or "Unknown"
        description: str = tx.get("asset_description") or ""

        if not ticker or ticker in ("--", "N/A"):
            ticker = "UNKNOWN"

        summary = f"{representative} {tx_type} {ticker} ({amount})"

        rows.append({
            "date": tx_date.isoformat(),
            "type": "congress",
            "ticker": ticker,
            "action": tx_type,
            "details": {
                "representative": representative,
                "amount": amount,
                "description": description,
                "disclosure_date": tx.get("disclosure_date", ""),
                "transaction_date": tx_date_str,
                "district": tx.get("district", ""),
                "cap_gains_over_200": tx.get("cap_gains_over_200_usd", False),
            },
            "summary": summary,
        })

    logger.info(
        "Found %d Congressional transactions in the last %d days.",
        len(rows),
        CONGRESS_LOOKBACK_DAYS,
    )
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> None:
    errors: list[str] = []

    # --- LEAPS ---
    leaps_row = fetch_leaps_data()
    if leaps_row:
        result = save_to_supabase("market_positions", leaps_row)
        if result:
            logger.info("LEAPS snapshot saved: %s", leaps_row["summary"])
        else:
            errors.append("Failed to save LEAPS data to Supabase.")
    else:
        errors.append("Could not fetch LEAPS data.")

    # --- Congressional trading ---
    congress_rows = fetch_congress_trades()
    saved_count = 0
    failed_count = 0
    for row in congress_rows:
        result = save_to_supabase("market_positions", row)
        if result:
            saved_count += 1
        else:
            failed_count += 1

    logger.info(
        "Congressional trades: %d saved, %d failed (out of %d fetched).",
        saved_count, failed_count, len(congress_rows),
    )
    if failed_count:
        errors.append(
            f"{failed_count} Congressional trade row(s) failed to save."
        )

    # --- Status + Telegram notification ---
    if errors:
        status = "error"
        message = "; ".join(errors)
        logger.error("leaps_monitor finished with errors: %s", message)
    else:
        status = "success"
        lines = []
        if leaps_row:
            lines.append(f"LEAPS: {leaps_row['summary']}")
        if congress_rows:
            lines.append(
                f"Congress: {len(congress_rows)} trade(s) in last {CONGRESS_LOOKBACK_DAYS} days"
            )
            # Highlight any Pelosi trades
            pelosi = [r for r in congress_rows if "Nancy Pelosi" in r["details"].get("representative", "")]
            if pelosi:
                lines.append(f"  Pelosi trades: {len(pelosi)}")
                for p in pelosi[:3]:
                    lines.append(f"    • {p['summary']}")
        message = "\n".join(lines) if lines else "No new data."
        logger.info("leaps_monitor finished successfully.")

    update_module_status(MODULE_NAME, status, message)

    if status == "success" and (leaps_row or congress_rows):
        notify_lines = ["<b>LEAPS &amp; Congress Monitor</b>"]
        if leaps_row:
            notify_lines.append(f"📈 {leaps_row['summary']}")
        if congress_rows:
            notify_lines.append(
                f"🏛 {len(congress_rows)} Congressional trade(s) (last {CONGRESS_LOOKBACK_DAYS}d)"
            )
        send_telegram("\n".join(notify_lines))


if __name__ == "__main__":
    run()
