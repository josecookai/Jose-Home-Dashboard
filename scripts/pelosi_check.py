"""
pelosi_check.py — Monitor Nancy Pelosi's congressional trading activity.

Data sources
------------
Primary : House Stock Watcher public API
          https://house-stock-watcher-data.s3-us-east-2.amazonaws.com/data/all_transactions.json
Fallback : Capitol Trades HTML scrape
           https://www.capitoltrades.com/politicians?politician=nancy-pelosi

Configuration (env vars / .env file)
-------------------------------------
NEXT_PUBLIC_SUPABASE_URL   — Supabase project URL
SUPABASE_SERVICE_KEY       — Supabase service-role key
TELEGRAM_BOT_TOKEN         — Telegram bot token
TELEGRAM_CHAT_ID           — Telegram chat ID

Output tables (Supabase)
------------------------
market_positions   type='congress'  — Pelosi trade records
module_status                        — run result
"""

import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup
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
logger = logging.getLogger("pelosi_check")

MODULE_NAME = "pelosi_check"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HOUSE_WATCHER_URL = (
    "https://house-stock-watcher-data.s3-us-east-2.amazonaws.com"
    "/data/all_transactions.json"
)
CAPITOL_TRADES_URL = (
    "https://www.capitoltrades.com/politicians?politician=nancy-pelosi"
)

LOOKBACK_DAYS = 7
PELOSI_NAME_VARIANTS = frozenset(
    {"Nancy Pelosi", "Nancy P. Pelosi", "Pelosi, Nancy"}
)
REQUEST_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def _parse_date(date_str: str) -> date | None:
    """Try multiple date formats used by House Stock Watcher and Capitol Trades."""
    if not date_str:
        return None
    cleaned = date_str.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Primary source: House Stock Watcher API
# ---------------------------------------------------------------------------

def _is_pelosi(name: str) -> bool:
    """Return True when the representative name refers to Nancy Pelosi."""
    name_stripped = name.strip()
    if name_stripped in PELOSI_NAME_VARIANTS:
        return True
    lower = name_stripped.lower()
    return "pelosi" in lower and "nancy" in lower


def fetch_from_house_watcher() -> list[dict[str, Any]]:
    """
    Download all House transactions from House Stock Watcher and return
    Pelosi-only rows from the last LOOKBACK_DAYS days.

    Each returned dict is ready to upsert into market_positions.
    """
    logger.info("Fetching House Stock Watcher data…")

    try:
        response = requests.get(HOUSE_WATCHER_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        transactions: list[dict[str, Any]] = response.json()
    except requests.HTTPError as exc:
        logger.error(
            "HTTP error fetching House Stock Watcher data: %s — %s",
            exc.response.status_code,
            exc.response.text[:300],
        )
        return []
    except requests.RequestException as exc:
        logger.error("Network error fetching House Stock Watcher data: %s", exc)
        return []
    except ValueError as exc:
        logger.error("Failed to parse House Stock Watcher JSON: %s", exc)
        return []

    cutoff = date.today() - timedelta(days=LOOKBACK_DAYS)
    rows: list[dict[str, Any]] = []

    for tx in transactions:
        representative: str = (tx.get("representative") or "").strip()
        if not _is_pelosi(representative):
            continue

        # Prefer transaction_date; fall back to disclosure_date
        tx_date_str: str = (
            tx.get("transaction_date")
            or tx.get("disclosure_date")
            or ""
        )
        tx_date = _parse_date(tx_date_str)

        # If transaction date is missing or too old, skip
        if tx_date is None or tx_date < cutoff:
            continue

        disclosure_date_str: str = tx.get("disclosure_date") or ""
        ticker: str = (tx.get("ticker") or "").strip().upper()
        if not ticker or ticker in ("--", "N/A", ""):
            ticker = "UNKNOWN"

        tx_type: str = (tx.get("type") or "unknown").strip().lower()
        amount: str = tx.get("amount") or "Unknown"
        description: str = tx.get("asset_description") or ""

        rows.append(
            _build_row(
                tx_date=tx_date,
                ticker=ticker,
                tx_type=tx_type,
                amount=amount,
                description=description,
                disclosure_date=disclosure_date_str,
                source="house_watcher",
            )
        )

    logger.info(
        "House Stock Watcher: found %d Pelosi transaction(s) in the last %d days.",
        len(rows),
        LOOKBACK_DAYS,
    )
    return rows


# ---------------------------------------------------------------------------
# Fallback source: Capitol Trades HTML scrape
# ---------------------------------------------------------------------------

def fetch_from_capitol_trades() -> list[dict[str, Any]]:
    """
    Scrape Capitol Trades for Nancy Pelosi's recent trades.

    This is a best-effort fallback — page structure can change without notice.
    Returns an empty list when scraping fails rather than raising.
    """
    logger.info("Attempting Capitol Trades scrape as fallback…")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        response = requests.get(
            CAPITOL_TRADES_URL, headers=headers, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        html = response.text
    except requests.HTTPError as exc:
        logger.warning(
            "HTTP error scraping Capitol Trades: %s — %s",
            exc.response.status_code,
            exc.response.text[:200],
        )
        return []
    except requests.RequestException as exc:
        logger.warning("Network error scraping Capitol Trades: %s", exc)
        return []

    try:
        rows = _parse_capitol_trades_html(html)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to parse Capitol Trades HTML: %s", exc)
        return []

    logger.info(
        "Capitol Trades: found %d Pelosi transaction(s) in the last %d days.",
        len(rows),
        LOOKBACK_DAYS,
    )
    return rows


def _parse_capitol_trades_html(html: str) -> list[dict[str, Any]]:
    """
    Parse trade rows from Capitol Trades HTML.

    The page renders a <table> with columns:
      Politician | Traded | Filed | Ticker | Asset | Type | Size / Amount

    Column indices may shift — we locate headers dynamically.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Look for any <table> that contains trade data
    tables = soup.find_all("table")
    if not tables:
        logger.debug("No <table> elements found on Capitol Trades page.")
        return []

    cutoff = date.today() - timedelta(days=LOOKBACK_DAYS)
    rows: list[dict[str, Any]] = []

    for table in tables:
        thead = table.find("thead")
        if not thead:
            continue

        # Build column index map from header text
        header_cells = thead.find_all(["th", "td"])
        col_map: dict[str, int] = {}
        for idx, cell in enumerate(header_cells):
            text = cell.get_text(strip=True).lower()
            col_map[text] = idx

        # We need at minimum a date and ticker column
        date_col = col_map.get("traded") or col_map.get("date") or col_map.get("transaction date")
        ticker_col = col_map.get("ticker") or col_map.get("symbol")
        type_col = col_map.get("type") or col_map.get("transaction type")
        amount_col = col_map.get("size") or col_map.get("amount") or col_map.get("size / amount")
        filed_col = col_map.get("filed") or col_map.get("disclosure date") or col_map.get("filed date")

        if date_col is None or ticker_col is None:
            continue

        tbody = table.find("tbody")
        data_rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]

        for tr in data_rows:
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue

            def _cell_text(idx: int | None) -> str:
                if idx is None or idx >= len(cells):
                    return ""
                return cells[idx].get_text(separator=" ", strip=True)

            raw_date = _cell_text(date_col)
            tx_date = _parse_date(raw_date)
            if tx_date is None or tx_date < cutoff:
                continue

            raw_ticker = _cell_text(ticker_col)
            ticker = re.sub(r"\s+", "", raw_ticker).upper()
            if not ticker or ticker in ("--", "N/A"):
                ticker = "UNKNOWN"

            tx_type = _cell_text(type_col).lower() if type_col is not None else "unknown"
            amount = _cell_text(amount_col) if amount_col is not None else "Unknown"
            disclosure_date = _cell_text(filed_col) if filed_col is not None else ""

            rows.append(
                _build_row(
                    tx_date=tx_date,
                    ticker=ticker,
                    tx_type=tx_type,
                    amount=amount,
                    description="",
                    disclosure_date=disclosure_date,
                    source="capitol_trades",
                )
            )

    return rows


# ---------------------------------------------------------------------------
# Shared row builder
# ---------------------------------------------------------------------------

def _build_row(
    *,
    tx_date: date,
    ticker: str,
    tx_type: str,
    amount: str,
    description: str,
    disclosure_date: str,
    source: str,
) -> dict[str, Any]:
    """Return a market_positions-compatible dict for one Pelosi trade."""
    summary = f"Nancy Pelosi {tx_type} {ticker} ({amount})"
    return {
        "date": tx_date.isoformat(),
        "type": "congress",
        "ticker": ticker,
        "action": tx_type,
        "details": {
            "representative": "Nancy Pelosi",
            "amount": amount,
            "description": description,
            "disclosure_date": disclosure_date,
            "transaction_date": tx_date.isoformat(),
            "source": source,
        },
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _dedup_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Remove duplicate trades by (date, ticker, action, amount).

    House Watcher is the authoritative source; Capitol Trades rows that
    match an existing House Watcher entry are dropped.
    """
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        key = (
            row["date"],
            row["ticker"],
            row["action"],
            row["details"].get("amount", ""),
        )
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def _format_markdown_report(trades: list[dict[str, Any]]) -> str:
    """Return a Markdown-formatted summary suitable for Telegram (HTML parse mode)."""
    if not trades:
        return (
            "<b>Pelosi Trading Monitor</b>\n"
            f"No Pelosi trades found in the last {LOOKBACK_DAYS} days."
        )

    lines = [
        f"<b>Pelosi Trading Monitor — Last {LOOKBACK_DAYS} Days</b>",
        f"<i>{len(trades)} transaction(s) disclosed</i>",
        "",
    ]

    for trade in sorted(trades, key=lambda r: r["date"], reverse=True):
        details = trade["details"]
        date_label = trade["date"]
        ticker = trade["ticker"]
        action = trade["action"].capitalize()
        amount = details.get("amount", "Unknown")
        disclosure = details.get("disclosure_date", "")
        description = details.get("description", "")

        line_parts = [f"• <b>{ticker}</b> — {action} | {amount} | Traded: {date_label}"]
        if disclosure:
            line_parts.append(f"  Disclosed: {disclosure}")
        if description:
            line_parts.append(f"  Asset: {description}")
        lines.extend(line_parts)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _save_trades(trades: list[dict[str, Any]]) -> tuple[int, int]:
    """
    Upsert all trade rows into market_positions.

    Returns (saved_count, failed_count).
    """
    saved = 0
    failed = 0
    for row in trades:
        result = save_to_supabase(
            "market_positions",
            row,
            unique_on=["date", "ticker", "action"],
        )
        if result:
            saved += 1
        else:
            failed += 1
    return saved, failed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("pelosi_check starting…")
    errors: list[str] = []

    # --- Primary source ---
    trades = fetch_from_house_watcher()

    # --- Fallback: Capitol Trades ---
    if not trades:
        logger.info(
            "No trades from House Stock Watcher; trying Capitol Trades fallback."
        )
        trades = fetch_from_capitol_trades()
    else:
        # Supplement with Capitol Trades to catch anything not yet in HSW
        ct_trades = fetch_from_capitol_trades()
        trades = _dedup_rows(trades + ct_trades)

    # --- Persist to Supabase ---
    saved_count = 0
    failed_count = 0
    if trades:
        saved_count, failed_count = _save_trades(trades)
        logger.info(
            "Saved %d Pelosi trade(s) to market_positions (%d failed).",
            saved_count,
            failed_count,
        )
        if failed_count:
            errors.append(
                f"{failed_count} trade row(s) failed to save to Supabase."
            )
    else:
        logger.info("No Pelosi trades found in the last %d days.", LOOKBACK_DAYS)

    # --- Build status message ---
    if errors:
        status = "error"
        status_message = "; ".join(errors)
        logger.error("pelosi_check finished with errors: %s", status_message)
    else:
        status = "success"
        status_message = (
            f"{len(trades)} Pelosi trade(s) in the last {LOOKBACK_DAYS} days; "
            f"{saved_count} saved to Supabase."
        )
        logger.info("pelosi_check finished successfully.")

    # --- Update module_status ---
    update_module_status(MODULE_NAME, status, status_message)

    # --- Send Telegram notification ---
    report = _format_markdown_report(trades)
    send_telegram(report)


if __name__ == "__main__":
    main()
