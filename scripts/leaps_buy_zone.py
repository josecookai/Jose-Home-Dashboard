#!/usr/bin/env python3
"""
leaps_buy_zone.py — LEAPS Buy Zone Monitor

Checks current prices for a watchlist of stocks against predefined buy zones
for LEAPS options entry. Sends Telegram alerts when a ticker is in or below
its buy zone, and saves per-ticker results to Supabase.

Scheduled usage (cron example — runs daily at 08:00 UTC):
    0 8 * * * /usr/bin/python3 /path/to/leaps_buy_zone.py >> /var/log/leaps_buy_zone.log 2>&1

Environment variables (via .env or shell):
    NEXT_PUBLIC_SUPABASE_URL   or  SUPABASE_URL
    SUPABASE_SERVICE_KEY       or  SUPABASE_SERVICE_ROLE_KEY
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID
"""

import json
import logging
import os
from datetime import date, datetime, timezone
from typing import Optional

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("leaps_buy_zone")

# ---------------------------------------------------------------------------
# Inline helpers (mirror of common.py for portability)
# ---------------------------------------------------------------------------

SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL") or os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

MODULE_NAME = "leaps_buy_zone"
REQUEST_TIMEOUT = 15  # seconds


def _supabase_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }


def save_to_supabase(table: str, data: dict) -> bool:
    """Upsert *data* into *table* via the Supabase REST API."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("Supabase credentials not configured — skipping save.")
        return False
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    try:
        response = requests.post(
            url, json=data, headers=_supabase_headers(), timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        logger.info("Saved record to Supabase table '%s'.", table)
        return True
    except requests.RequestException as exc:
        logger.error("Failed to save to Supabase table '%s': %s", table, exc)
        return False


def update_module_status(name: str, status: str, message: str = "") -> None:
    """Upsert a row in the module_status table."""
    save_to_supabase(
        "module_status",
        {
            "module_name": name,
            "last_run_at": datetime.now(timezone.utc).isoformat(),
            "last_status": status,
            "last_message": message,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def send_telegram(msg: str) -> bool:
    """Send *msg* to the configured Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning(
            "Telegram not configured — set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."
        )
        return False
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": msg,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        logger.info("Telegram message sent (chat_id=%s).", TELEGRAM_CHAT_ID)
        return True
    except requests.RequestException as exc:
        logger.error("Failed to send Telegram message: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Watchlist configuration
# ---------------------------------------------------------------------------

WATCHLIST: list[dict] = [
    {"ticker": "GOOGL", "buy_zone_low": 150, "buy_zone_high": 165},
    {"ticker": "AAPL",  "buy_zone_low": 165, "buy_zone_high": 180},
    {"ticker": "META",  "buy_zone_low": 480, "buy_zone_high": 520},
    {"ticker": "MU",    "buy_zone_low": 85,  "buy_zone_high": 100},
]

# ---------------------------------------------------------------------------
# Price fetching
# ---------------------------------------------------------------------------


def fetch_price_yfinance(ticker: str) -> Optional[float]:
    """
    Fetch the most recent closing price for *ticker* via yfinance.

    Returns None when yfinance is unavailable or the fetch fails.
    """
    try:
        import yfinance as yf  # optional dependency — import lazily
    except ImportError:
        return None  # caller handles the ImportError path

    try:
        hist = yf.Ticker(ticker).history(period="2d")
        if hist.empty:
            logger.warning("No price history returned by yfinance for %s.", ticker)
            return None
        price = float(hist["Close"].iloc[-1])
        logger.info("yfinance price for %s: $%.2f", ticker, price)
        return price
    except Exception as exc:  # noqa: BLE001
        logger.error("yfinance error fetching %s: %s", ticker, exc)
        return None


def fetch_price_yahoo_api(ticker: str) -> Optional[float]:
    """
    Fallback: fetch the current price via Yahoo Finance's public query API
    (no third-party library required).

    Returns None on failure.
    """
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        "?interval=1d&range=1d"
    )
    headers = {"User-Agent": "Mozilla/5.0 (compatible; leaps-buy-zone-bot/1.0)"}
    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        close_prices = (
            data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        )
        # Filter out None values and take the last valid close
        valid_closes = [p for p in close_prices if p is not None]
        if not valid_closes:
            logger.warning("No valid close prices in Yahoo API response for %s.", ticker)
            return None
        price = float(valid_closes[-1])
        logger.info("Yahoo API price for %s: $%.2f", ticker, price)
        return price
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
        logger.error("Yahoo API error fetching %s: %s", ticker, exc)
        return None


def fetch_current_price(ticker: str) -> Optional[float]:
    """
    Attempt to retrieve the current price for *ticker*, trying yfinance first
    and falling back to the Yahoo Finance API if yfinance is unavailable.
    """
    # Try yfinance (preferred)
    try:
        import yfinance  # noqa: F401 — just checking availability
        price = fetch_price_yfinance(ticker)
        if price is not None:
            return price
    except ImportError:
        logger.warning(
            "yfinance not installed — falling back to Yahoo Finance API. "
            "Run: pip install yfinance"
        )

    # Fallback to direct HTTP request
    return fetch_price_yahoo_api(ticker)


# ---------------------------------------------------------------------------
# Zone classification
# ---------------------------------------------------------------------------


def classify_price(
    price: float, buy_zone_low: float, buy_zone_high: float
) -> str:
    """
    Return 'in_zone', 'below_zone', or 'above_zone' based on price vs zone.
    """
    if buy_zone_low <= price <= buy_zone_high:
        return "in_zone"
    if price < buy_zone_low:
        return "below_zone"
    return "above_zone"


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _zone_status_line(entry: dict, price: float, zone: str) -> str:
    """Return a single-line summary for the daily digest table."""
    low = entry["buy_zone_low"]
    high = entry["buy_zone_high"]
    ticker = entry["ticker"]
    distance_pct = ((price - low) / low) * 100

    zone_label = {
        "in_zone": "IN ZONE ",
        "below_zone": "BELOW   ",
        "above_zone": "ABOVE   ",
    }[zone]

    return (
        f"{ticker:<6} ${price:>8.2f}  zone ${low}-${high}  "
        f"{zone_label} ({distance_pct:+.1f}% vs low)"
    )


def build_summary(results: list[dict]) -> str:
    """
    Build a Markdown daily digest covering all watchlist positions.

    *results* is a list of dicts with keys: ticker, price, buy_zone_low,
    buy_zone_high, zone, error.
    """
    today = date.today().isoformat()
    lines = [
        f"*LEAPS Buy Zone Monitor — {today}*",
        "",
        "*Watchlist Status*",
        "```",
        f"{'Ticker':<6} {'Price':>9}  {'Zone':>12}  {'Status':<8} Vs Low",
        "-" * 56,
    ]

    for r in results:
        if r.get("error") or r.get("price") is None:
            lines.append(f"{r['ticker']:<6}  ERROR — could not fetch price")
        else:
            lines.append(
                _zone_status_line(r, r["price"], r["zone"])
            )

    lines += ["```", ""]

    # Counts
    in_zone = [r for r in results if r.get("zone") == "in_zone"]
    below = [r for r in results if r.get("zone") == "below_zone"]
    if in_zone:
        lines.append(f"*In buy zone ({len(in_zone)}):* " + ", ".join(r["ticker"] for r in in_zone))
    if below:
        lines.append(f"*Below buy zone ({len(below)}):* " + ", ".join(r["ticker"] for r in below))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run() -> None:
    today = date.today().isoformat()
    logger.info("Starting leaps_buy_zone for %s", today)

    results: list[dict] = []
    alerts: list[str] = []
    errors: list[str] = []

    for entry in WATCHLIST:
        ticker = entry["ticker"]
        low = entry["buy_zone_low"]
        high = entry["buy_zone_high"]

        price = fetch_current_price(ticker)

        if price is None:
            logger.error("Could not fetch price for %s.", ticker)
            errors.append(f"No price for {ticker}")
            results.append(
                {
                    "ticker": ticker,
                    "price": None,
                    "buy_zone_low": low,
                    "buy_zone_high": high,
                    "zone": None,
                    "error": True,
                }
            )
            continue

        zone = classify_price(price, low, high)
        results.append(
            {
                "ticker": ticker,
                "price": price,
                "buy_zone_low": low,
                "buy_zone_high": high,
                "zone": zone,
                "error": False,
            }
        )

        # -- Per-ticker Telegram alerts --
        if zone == "in_zone":
            alert = f"🚨 BUY ZONE: {ticker} at ${price:.2f} (zone ${low}–${high})"
            logger.info(alert)
            alerts.append(alert)
            send_telegram(alert)
        elif zone == "below_zone":
            alert = f"⬇️ BELOW buy zone: {ticker} at ${price:.2f} (zone ${low}–${high})"
            logger.info(alert)
            alerts.append(alert)
            send_telegram(alert)
        else:
            logger.info("%s at $%.2f is above buy zone ($%s–$%s).", ticker, price, low, high)

        # -- Persist to market_data --
        save_to_supabase(
            "market_data",
            {
                "date": today,
                "symbol": ticker,
                "data_type": "buy_zone_check",
                "value": price,
                "extra": json.dumps(
                    {
                        "buy_zone_low": low,
                        "buy_zone_high": high,
                        "in_zone": zone == "in_zone",
                        "zone_status": zone,
                    }
                ),
            },
        )

    # -- Daily summary --
    summary_text = build_summary(results)
    logger.info("Daily summary:\n%s", summary_text)
    send_telegram(summary_text)

    # -- Module status --
    in_zone_tickers = [r["ticker"] for r in results if r.get("zone") == "in_zone"]
    below_tickers = [r["ticker"] for r in results if r.get("zone") == "below_zone"]
    status = "error" if len(errors) == len(WATCHLIST) else "success"
    message_parts = [
        f"Checked {len(results)}/{len(WATCHLIST)} tickers",
        f"in_zone: {in_zone_tickers or 'none'}",
        f"below: {below_tickers or 'none'}",
    ]
    if errors:
        message_parts.append(f"errors: {errors}")
    update_module_status(MODULE_NAME, status, " | ".join(message_parts))

    if errors:
        logger.warning("leaps_buy_zone completed with errors: %s", errors)
    else:
        logger.info("leaps_buy_zone completed successfully.")


if __name__ == "__main__":
    run()
