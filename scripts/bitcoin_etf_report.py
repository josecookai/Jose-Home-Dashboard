#!/usr/bin/env python3
"""
Bitcoin ETF Daily Report Script

Fetches BTC price from CoinGecko, scrapes ETF flow data from Farside Investors,
saves results to Supabase, and sends a Telegram notification.
"""

import os
import json
import logging
from datetime import date, datetime, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

COINGECKO_URL = (
    "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
)
FARSIDE_URL = "https://farside.co.uk/bitcoin-etf/flow/"

REQUEST_TIMEOUT = 15  # seconds

# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------


def supabase_headers() -> dict:
    """Return headers required for Supabase REST API calls."""
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }


def save_to_supabase(table: str, data: dict) -> bool:
    """
    Upsert a single record into a Supabase table.

    Uses the REST PostgREST endpoint with 'resolution=merge-duplicates'
    so duplicate rows (matched on the table's unique / primary key) are
    updated rather than rejected.

    Returns True on success, False otherwise.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        logger.warning("Supabase credentials not configured – skipping save.")
        return False

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    try:
        response = requests.post(
            url,
            headers=supabase_headers(),
            json=data,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        logger.info("Saved record to Supabase table '%s'.", table)
        return True
    except requests.RequestException as exc:
        logger.error("Failed to save to Supabase table '%s': %s", table, exc)
        return False


def update_module_status(
    module_name: str,
    status: str,
    message: str = "",
) -> None:
    """
    Upsert a row in the 'module_status' table to record the last run
    outcome for a given module.

    Fields written: module_name, last_run_at, last_status, last_message.
    """
    payload = {
        "module_name": module_name,
        "last_run_at": datetime.now(timezone.utc).isoformat(),
        "last_status": status,
        "last_message": message,
    }
    save_to_supabase("module_status", payload)


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------


def fetch_btc_price() -> Optional[float]:
    """
    Fetch the current Bitcoin price in USD from the CoinGecko public API.

    Returns the price as a float, or None on failure.
    """
    try:
        response = requests.get(COINGECKO_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        price = data["bitcoin"]["usd"]
        logger.info("BTC price fetched: $%s", price)
        return float(price)
    except (requests.RequestException, KeyError, ValueError) as exc:
        logger.error("Failed to fetch BTC price: %s", exc)
        return None


def _parse_flow_value(cell_text: str) -> Optional[float]:
    """
    Convert a flow cell string such as '123.45', '-45.6', or '-' to a float.

    Returns None for missing / non-numeric values.
    """
    text = cell_text.strip().replace(",", "")
    if text in ("", "-", "—", "N/A"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def scrape_etf_flows() -> dict:
    """
    Scrape today's ETF flow values (IBIT, FBTC, GBTC) from Farside Investors.

    The page contains an HTML table whose first column is the ticker name and
    whose last data column (before totals) is the most recent day's flow in
    millions USD.

    Returns a dict with keys 'ibit_flow', 'fbtc_flow', 'gbtc_flow' and
    'raw_data' (the full parsed table as a list of dicts).  Flow values are
    floats (millions USD) or None when unavailable.
    """
    result = {
        "ibit_flow": None,
        "fbtc_flow": None,
        "gbtc_flow": None,
        "raw_data": None,
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; bitcoin-etf-report-bot/1.0)"
        )
    }

    try:
        response = requests.get(
            FARSIDE_URL, headers=headers, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Could not fetch Farside page: %s", exc)
        return result

    try:
        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table")
        if table is None:
            logger.warning("No HTML table found on Farside page.")
            return result

        rows = table.find_all("tr")
        if not rows:
            logger.warning("Empty table on Farside page.")
            return result

        # Derive column headers from the first header row.
        header_row = rows[0]
        col_headers = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]

        # Map ticker -> last non-empty column value across data rows.
        # The table layout: row per ETF, columns = Date | daily flows...
        # We want the *last* date column's value for each ticker.
        raw_rows = []
        ticker_flows: dict[str, Optional[float]] = {}

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue

            cell_texts = [c.get_text(strip=True) for c in cells]
            if not cell_texts:
                continue

            ticker = cell_texts[0].upper()

            # Build a dict for raw_data output.
            row_dict = {}
            for idx, header in enumerate(col_headers):
                row_dict[header] = cell_texts[idx] if idx < len(cell_texts) else ""
            raw_rows.append(row_dict)

            # Find the last non-empty, non-header cell value (rightmost data).
            last_value = None
            for cell_text in reversed(cell_texts[1:]):
                parsed = _parse_flow_value(cell_text)
                if parsed is not None:
                    last_value = parsed
                    break

            ticker_flows[ticker] = last_value

        result["ibit_flow"] = ticker_flows.get("IBIT")
        result["fbtc_flow"] = ticker_flows.get("FBTC")
        result["gbtc_flow"] = ticker_flows.get("GBTC")
        result["raw_data"] = raw_rows

        logger.info(
            "ETF flows – IBIT: %s, FBTC: %s, GBTC: %s",
            result["ibit_flow"],
            result["fbtc_flow"],
            result["gbtc_flow"],
        )

    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Error parsing Farside HTML: %s", exc)

    return result


# ---------------------------------------------------------------------------
# Summary generation
# ---------------------------------------------------------------------------


def generate_summary(
    report_date: str,
    btc_price: Optional[float],
    ibit_flow: Optional[float],
    fbtc_flow: Optional[float],
    gbtc_flow: Optional[float],
    total_flow: Optional[float],
) -> str:
    """Build a human-readable text summary of the daily report."""

    def fmt_price(value: Optional[float]) -> str:
        return f"${value:,.2f}" if value is not None else "N/A"

    def fmt_flow(value: Optional[float]) -> str:
        if value is None:
            return "N/A"
        sign = "+" if value >= 0 else ""
        return f"{sign}{value:.1f}M USD"

    lines = [
        f"Bitcoin ETF Daily Report — {report_date}",
        "=" * 45,
        f"BTC Price : {fmt_price(btc_price)}",
        "",
        "ETF Flows (today, millions USD):",
        f"  IBIT  : {fmt_flow(ibit_flow)}",
        f"  FBTC  : {fmt_flow(fbtc_flow)}",
        f"  GBTC  : {fmt_flow(gbtc_flow)}",
        f"  TOTAL : {fmt_flow(total_flow)}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Telegram notification
# ---------------------------------------------------------------------------


def send_telegram(message: str) -> None:
    """
    Send a plain-text Telegram message if bot credentials are configured.
    Silently skips when TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID are absent.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.info("Telegram credentials not set – skipping notification.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }
    try:
        response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        logger.info("Telegram notification sent.")
    except requests.RequestException as exc:
        logger.warning("Failed to send Telegram notification: %s", exc)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    today = date.today().isoformat()  # YYYY-MM-DD
    logger.info("Starting Bitcoin ETF report for %s", today)

    try:
        # 1. Fetch BTC price
        btc_price = fetch_btc_price()

        # 2. Scrape ETF flows
        flow_data = scrape_etf_flows()
        ibit_flow = flow_data["ibit_flow"]
        fbtc_flow = flow_data["fbtc_flow"]
        gbtc_flow = flow_data["gbtc_flow"]
        raw_data = flow_data["raw_data"]

        # 3. Compute total flow (only sum known values)
        known_flows = [f for f in [ibit_flow, fbtc_flow, gbtc_flow] if f is not None]
        total_flow: Optional[float] = sum(known_flows) if known_flows else None

        # 4. Generate summary
        summary = generate_summary(
            report_date=today,
            btc_price=btc_price,
            ibit_flow=ibit_flow,
            fbtc_flow=fbtc_flow,
            gbtc_flow=gbtc_flow,
            total_flow=total_flow,
        )
        logger.info("Summary:\n%s", summary)

        # 5. Persist to Supabase
        record = {
            "date": today,
            "btc_price": btc_price,
            "ibit_flow": ibit_flow,
            "fbtc_flow": fbtc_flow,
            "gbtc_flow": gbtc_flow,
            "total_flow": total_flow,
            "summary": summary,
            "raw_data": json.dumps(raw_data) if raw_data is not None else None,
        }
        save_to_supabase("bitcoin_etf_daily", record)

        # 6. Telegram notification
        send_telegram(summary)

        # 7. Update module status
        update_module_status(
            module_name="bitcoin_etf",
            status="success",
            message=f"Report generated for {today}. BTC=${btc_price}",
        )

        logger.info("Bitcoin ETF report completed successfully.")

    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Unhandled error in bitcoin_etf_report: %s", exc, exc_info=True)
        update_module_status(
            module_name="bitcoin_etf",
            status="error",
            message=str(exc),
        )
        raise


if __name__ == "__main__":
    main()
