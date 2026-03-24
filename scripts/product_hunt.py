"""
product_hunt.py — Product Hunt Daily Top 10 (Issue #3)

Parses the Product Hunt RSS feed, extracts today's products, sorts by vote
count when available, formats a Markdown digest, sends it via Telegram, and
persists each product to the `ai_intel_daily` Supabase table.
"""

import os
import re
import logging
from datetime import date, datetime, timezone
from time import mktime

import feedparser
import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Inline helpers (as required by project spec)
# ---------------------------------------------------------------------------

SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL") or os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")


def save_to_supabase(table: str, data: dict) -> None:
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("Supabase credentials not configured; skipping save.")
        return
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    try:
        response = requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            json=data,
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
    except requests.HTTPError as exc:
        logger.error(
            "HTTP error saving to %s: %s — %s",
            table,
            exc.response.status_code,
            exc.response.text[:300],
        )
    except requests.RequestException as exc:
        logger.error("Network error saving to %s: %s", table, exc)


def update_module_status(name: str, status: str, message: str = "") -> None:
    save_to_supabase(
        "module_status",
        {
            "module_name": name,
            "last_run_at": datetime.utcnow().isoformat(),
            "last_status": status,
            "last_message": message,
            "updated_at": datetime.utcnow().isoformat(),
        },
    )


def send_telegram(msg: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning(
            "Telegram not configured — set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."
        )
        return
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
            timeout=10,
        )
        response.raise_for_status()
        logger.info("Telegram message sent.")
    except requests.HTTPError as exc:
        logger.error(
            "Telegram HTTP error: %s — %s",
            exc.response.status_code,
            exc.response.text[:300],
        )
    except requests.RequestException as exc:
        logger.error("Telegram network error: %s", exc)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FEED_URL = "https://www.producthunt.com/feed"
MODULE_NAME = "product_hunt"
MAX_PRODUCTS = 10

# Patterns used to extract vote counts embedded in RSS description HTML.
_VOTE_PATTERNS = [
    re.compile(r"(\d[\d,]*)\s*(?:votes?|upvotes?|points?)", re.IGNORECASE),
    re.compile(r"votes?[^\d]*(\d[\d,]*)", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry_date(entry) -> date | None:
    """Return the publication date of a feedparser entry, or None."""
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                return date(*parsed[:3])
            except (TypeError, ValueError):
                continue
    return None


def _is_today(entry) -> bool:
    """Return True if the entry was published today (UTC)."""
    entry_date = _entry_date(entry)
    if entry_date is None:
        # Cannot determine date — include as graceful fallback.
        return True
    return entry_date == date.today()


def _extract_votes(entry) -> int | None:
    """
    Attempt to extract a vote count from the entry's description HTML.
    Returns None when no vote count can be found.
    """
    description = entry.get("description") or entry.get("summary") or ""
    for pattern in _VOTE_PATTERNS:
        match = pattern.search(description)
        if match:
            try:
                return int(match.group(1).replace(",", ""))
            except ValueError:
                continue
    return None


def _clean_tagline(entry) -> str:
    """Return a plain-text tagline (summary), stripping HTML, max 200 chars."""
    raw = entry.get("summary") or entry.get("description") or ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = " ".join(text.split())
    return text[:200].rstrip() + ("…" if len(text) > 200 else "")


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def fetch_todays_products() -> list[dict]:
    """
    Parse the Product Hunt RSS feed, keep only today's entries, extract
    metadata including an optional vote count, sort by votes (desc), and
    return up to MAX_PRODUCTS products.
    """
    logger.info("Fetching Product Hunt RSS feed: %s", FEED_URL)
    try:
        feed = feedparser.parse(FEED_URL)
        if feed.bozo and not feed.entries:
            logger.warning(
                "Feed parse warning for Product Hunt: %s", feed.bozo_exception
            )
            return []
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error parsing Product Hunt feed: %s", exc)
        return []

    products: list[dict] = []

    for entry in feed.entries:
        if not _is_today(entry):
            continue

        title = entry.get("title", "").strip()
        url = entry.get("link", "").strip()
        if not title or not url:
            continue

        products.append({
            "title": title,
            "tagline": _clean_tagline(entry),
            "url": url,
            "votes": _extract_votes(entry),
        })

    logger.info("Today's products found: %d", len(products))

    # Sort by votes descending; entries without votes sort to the bottom.
    products.sort(
        key=lambda p: p["votes"] if p["votes"] is not None else -1,
        reverse=True,
    )

    return products[:MAX_PRODUCTS]


def format_telegram_message(products: list[dict]) -> str:
    """Format the top products as a numbered Markdown digest."""
    today = date.today().strftime("%Y-%m-%d")
    lines = [f"🚀 *Product Hunt Top 10 — {today}*\n"]

    if not products:
        lines.append("_No products found for today._")
        return "\n".join(lines)

    for i, product in enumerate(products, start=1):
        vote_str = f" ({product['votes']:,} votes)" if product["votes"] is not None else ""
        tagline = product["tagline"]
        tagline_line = f"   _{tagline}_\n" if tagline else ""
        lines.append(
            f"{i}. *{product['title']}*{vote_str}\n"
            f"{tagline_line}"
            f"   🔗 {product['url']}"
        )

    return "\n\n".join(lines)


def persist_products(products: list[dict]) -> int:
    """Save each product to the ai_intel_daily table. Returns the save count."""
    today = date.today().isoformat()
    saved = 0
    for product in products:
        save_to_supabase(
            "ai_intel_daily",
            {
                "date": today,
                "source": "producthunt",
                "title": product["title"],
                "url": product["url"],
                "summary": product["tagline"],
                "tags": ["producthunt"],
            },
        )
        saved += 1
    return saved


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run() -> None:
    logger.info("=== Product Hunt Daily Top 10 starting ===")
    try:
        products = fetch_todays_products()
        logger.info("Products collected: %d", len(products))

        message = format_telegram_message(products)
        send_telegram(message)

        saved = persist_products(products)
        logger.info("Saved %d product(s) to ai_intel_daily.", saved)

        update_module_status(
            MODULE_NAME,
            "success",
            f"Collected {len(products)} products; saved {saved}.",
        )
        logger.info("=== Product Hunt Daily Top 10 complete ===")

    except Exception as exc:  # noqa: BLE001
        logger.error("Unhandled error in product_hunt: %s", exc)
        update_module_status(MODULE_NAME, "error", str(exc))
        raise


if __name__ == "__main__":
    run()
