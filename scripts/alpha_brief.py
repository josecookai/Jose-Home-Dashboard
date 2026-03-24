#!/usr/bin/env python3
"""
alpha_brief.py — Daily Alpha Brief

Fetches major index prices (SPY, QQQ, BTC-USD), Fear & Greed Index, and top
financial headlines, then formats a Markdown briefing, sends it via Telegram,
and persists it to Supabase.

Scheduled usage (cron example — runs daily at 07:00 UTC):
    0 7 * * * /usr/bin/python3 /path/to/alpha_brief.py >> /var/log/alpha_brief.log 2>&1

Environment variables (via .env or shell):
    NEXT_PUBLIC_SUPABASE_URL   or  SUPABASE_URL
    SUPABASE_SERVICE_KEY       or  SUPABASE_SERVICE_ROLE_KEY
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID
"""

import json
import logging
import os
import xml.etree.ElementTree as ET
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
logger = logging.getLogger("alpha_brief")

# ---------------------------------------------------------------------------
# Inline helpers (mirror of common.py for portability)
# ---------------------------------------------------------------------------

SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL") or os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

MODULE_NAME = "alpha_brief"
REQUEST_TIMEOUT = 15  # seconds

FEAR_GREED_URL = "https://api.alternative.me/fng/"
YAHOO_RSS_URL = "https://finance.yahoo.com/news/rssindex"

TICKERS = ["SPY", "QQQ", "BTC-USD"]


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
# Market data
# ---------------------------------------------------------------------------


def fetch_index_prices() -> list[dict]:
    """
    Fetch 2-day price history for each ticker via yfinance and return a list
    of dicts with keys: symbol, price, prev_price, change_pct.

    Returns an empty list (with a warning) if yfinance is not installed.
    """
    try:
        import yfinance as yf  # optional dependency — import lazily
    except ImportError:
        logger.warning(
            "yfinance is not installed — skipping index prices. "
            "Run: pip install yfinance"
        )
        return []

    results = []
    for symbol in TICKERS:
        try:
            hist = yf.Ticker(symbol).history(period="2d")
            if hist.empty or len(hist) < 2:
                logger.warning("Not enough history for %s — skipping.", symbol)
                continue
            prev_close = float(hist["Close"].iloc[-2])
            last_close = float(hist["Close"].iloc[-1])
            change_pct = ((last_close - prev_close) / prev_close) * 100 if prev_close else 0.0
            results.append(
                {
                    "symbol": symbol,
                    "price": round(last_close, 2),
                    "prev_price": round(prev_close, 2),
                    "change_pct": round(change_pct, 2),
                }
            )
            logger.info(
                "%s: $%.2f (%+.2f%%)", symbol, last_close, change_pct
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Error fetching price for %s: %s", symbol, exc)
    return results


# ---------------------------------------------------------------------------
# Fear & Greed Index
# ---------------------------------------------------------------------------


def fetch_fear_greed() -> Optional[dict]:
    """
    Fetch the current Fear & Greed Index from alternative.me.

    Returns a dict with keys: value (int), classification (str), or None on
    failure.
    """
    try:
        response = requests.get(FEAR_GREED_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
        entry = payload["data"][0]
        result = {
            "value": int(entry["value"]),
            "classification": entry["value_classification"],
        }
        logger.info(
            "Fear & Greed Index: %d (%s)", result["value"], result["classification"]
        )
        return result
    except (requests.RequestException, KeyError, ValueError, IndexError) as exc:
        logger.error("Failed to fetch Fear & Greed Index: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Yahoo Finance RSS headlines
# ---------------------------------------------------------------------------


def fetch_top_headlines(max_items: int = 3) -> list[dict]:
    """
    Fetch the top *max_items* financial headlines from Yahoo Finance RSS.

    Returns a list of dicts with keys: title, link.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; alpha-brief-bot/1.0)"
    }
    try:
        response = requests.get(
            YAHOO_RSS_URL, headers=headers, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Failed to fetch Yahoo Finance RSS: %s", exc)
        return []

    try:
        root = ET.fromstring(response.text)
        ns = ""
        # Handle possible namespace in feed
        items = root.findall(f".//{ns}item")
        headlines = []
        for item in items[:max_items]:
            title_el = item.find("title")
            link_el = item.find("link")
            title = title_el.text.strip() if title_el is not None and title_el.text else "No title"
            link = link_el.text.strip() if link_el is not None and link_el.text else ""
            headlines.append({"title": title, "link": link})
        logger.info("Fetched %d headlines from Yahoo Finance RSS.", len(headlines))
        return headlines
    except ET.ParseError as exc:
        logger.error("Failed to parse Yahoo Finance RSS XML: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Brief formatting
# ---------------------------------------------------------------------------

_ARROW = {True: "▲", False: "▼"}  # True = gain, False = loss


def _fmt_change(change_pct: float) -> str:
    arrow = _ARROW[change_pct >= 0]
    return f"{arrow} {change_pct:+.2f}%"


def build_brief(
    report_date: str,
    index_data: list[dict],
    fear_greed: Optional[dict],
    headlines: list[dict],
) -> str:
    """
    Assemble the full Markdown brief.

    Sections:
        1. Market Snapshot (table)
        2. Fear & Greed Index
        3. Top Headlines
    """
    lines = [
        f"*Daily Alpha Brief — {report_date}*",
        "",
    ]

    # --- Market snapshot ---
    if index_data:
        lines += [
            "*Market Snapshot*",
            "```",
            f"{'Symbol':<10} {'Price':>10} {'Change':>10}",
            "-" * 34,
        ]
        for row in index_data:
            lines.append(
                f"{row['symbol']:<10} ${row['price']:>9,.2f} {_fmt_change(row['change_pct']):>10}"
            )
        lines += ["```", ""]
    else:
        lines += ["_Market data unavailable._", ""]

    # --- Fear & Greed ---
    if fear_greed:
        value = fear_greed["value"]
        classification = fear_greed["classification"]
        # Visual bar (10 blocks)
        filled = round(value / 10)
        bar = "█" * filled + "░" * (10 - filled)
        lines += [
            f"*Fear & Greed Index:* {value}/100 — {classification}",
            f"`[{bar}]`",
            "",
        ]
    else:
        lines += ["_Fear & Greed data unavailable._", ""]

    # --- Headlines ---
    if headlines:
        lines.append("*Top Headlines*")
        for i, h in enumerate(headlines, start=1):
            # Escape Markdown special chars in title for safety
            safe_title = h["title"].replace("*", "\\*").replace("_", "\\_").replace("`", "\\`")
            if h["link"]:
                lines.append(f"{i}. [{safe_title}]({h['link']})")
            else:
                lines.append(f"{i}. {safe_title}")
        lines.append("")
    else:
        lines += ["_No headlines available._", ""]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    today = date.today().isoformat()
    logger.info("Starting alpha_brief for %s", today)

    errors: list[str] = []

    try:
        # 1. Market prices
        index_data = fetch_index_prices()
        if not index_data:
            errors.append("Could not fetch index prices.")

        # 2. Fear & Greed
        fear_greed = fetch_fear_greed()
        if fear_greed is None:
            errors.append("Could not fetch Fear & Greed Index.")

        # 3. Headlines
        headlines = fetch_top_headlines(max_items=3)
        if not headlines:
            errors.append("Could not fetch Yahoo Finance headlines.")

        # 4. Format brief
        brief_text = build_brief(
            report_date=today,
            index_data=index_data,
            fear_greed=fear_greed,
            headlines=headlines,
        )
        logger.info("Brief (length=%d chars):\n%s", len(brief_text), brief_text)

        # 5. Send via Telegram
        send_telegram(brief_text)

        # 6. Save to reports table
        save_to_supabase(
            "reports",
            {
                "date": today,
                "module": MODULE_NAME,
                "content": brief_text,
                "extra": json.dumps(
                    {
                        "index_data": index_data,
                        "fear_greed": fear_greed,
                        "headline_count": len(headlines),
                    }
                ),
            },
        )

        # 7. Update module status
        status = "error" if errors else "success"
        message = (
            "; ".join(errors)
            if errors
            else f"Brief generated for {today}. Indices: {len(index_data)}, "
            f"F&G: {fear_greed['value'] if fear_greed else 'N/A'}, "
            f"Headlines: {len(headlines)}"
        )
        update_module_status(MODULE_NAME, status, message)

        if errors:
            logger.warning("alpha_brief completed with warnings: %s", "; ".join(errors))
        else:
            logger.info("alpha_brief completed successfully.")

    except Exception as exc:  # noqa: BLE001
        logger.error("Unhandled error in alpha_brief: %s", exc, exc_info=True)
        update_module_status(MODULE_NAME, "error", str(exc))
        raise


if __name__ == "__main__":
    main()
