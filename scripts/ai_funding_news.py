"""
ai_funding_news.py — AI Funding News Tracker (Issue #2)

Fetches AI startup funding news from TechCrunch and VentureBeat RSS feeds,
filters for funding-related articles published in the last 24 hours, sends a
Markdown digest to Telegram, and persists each article to the `ai_intel_daily`
Supabase table.
"""

import os
import logging
from datetime import datetime, timedelta, timezone
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
            "last_run_at": datetime.now(timezone.utc).isoformat(),
            "last_status": status,
            "last_message": message,
            "updated_at": datetime.now(timezone.utc).isoformat(),
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

FEEDS = [
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/"),
]

FUNDING_KEYWORDS = [
    "funding",
    "raises",
    "million",
    "billion",
    "series",
    "seed",
    "investment",
    "backed",
]

MODULE_NAME = "ai_funding_news"
MAX_ARTICLES = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry_datetime(entry) -> datetime | None:
    """Return a timezone-aware datetime for a feedparser entry, or None."""
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
            except (TypeError, ValueError, OverflowError):
                continue
    return None


def _is_within_24h(entry) -> bool:
    """Return True if the entry was published within the last 24 hours."""
    entry_dt = _entry_datetime(entry)
    if entry_dt is None:
        # Cannot determine date — include entry as a graceful fallback.
        return True
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    return entry_dt >= cutoff


def _is_funding_related(entry) -> bool:
    """Return True if title or summary contains at least one funding keyword."""
    text = " ".join([
        entry.get("title", ""),
        entry.get("summary", ""),
        entry.get("description", ""),
    ]).lower()
    return any(kw in text for kw in FUNDING_KEYWORDS)


def _clean_summary(entry) -> str:
    """Return a plain-text summary truncated to 200 characters."""
    raw = entry.get("summary") or entry.get("description") or ""
    # Strip rudimentary HTML tags if present.
    import re
    text = re.sub(r"<[^>]+>", " ", raw)
    text = " ".join(text.split())
    return text[:200].rstrip() + ("…" if len(text) > 200 else "")


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def fetch_funding_articles() -> list[dict]:
    """
    Pull articles from all configured RSS feeds, filter for recency and
    funding relevance, and return up to MAX_ARTICLES results sorted by
    publication date (newest first).
    """
    candidates: list[tuple[datetime, dict]] = []

    for feed_name, feed_url in FEEDS:
        logger.info("Fetching feed: %s", feed_name)
        try:
            feed = feedparser.parse(feed_url)
            if feed.bozo and not feed.entries:
                logger.warning(
                    "Feed parse warning for %s: %s", feed_name, feed.bozo_exception
                )
                continue

            for entry in feed.entries:
                if not _is_within_24h(entry):
                    continue
                if not _is_funding_related(entry):
                    continue

                title = entry.get("title", "").strip()
                url = entry.get("link", "").strip()
                if not title or not url:
                    continue

                entry_dt = _entry_datetime(entry) or datetime.now(tz=timezone.utc)
                candidates.append((
                    entry_dt,
                    {
                        "title": title,
                        "url": url,
                        "summary": _clean_summary(entry),
                        "source_feed": feed_name,
                    },
                ))

            logger.info("  -> %d candidate(s) collected from %s", len(candidates), feed_name)

        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error fetching %s: %s", feed_name, exc)

    # Sort newest-first and cap at MAX_ARTICLES.
    candidates.sort(key=lambda t: t[0], reverse=True)
    return [article for _, article in candidates[:MAX_ARTICLES]]


def format_telegram_message(articles: list[dict]) -> str:
    """Format articles as a numbered Markdown digest."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [f"*AI Funding News — {today}*\n"]

    for i, article in enumerate(articles, start=1):
        summary = article["summary"]
        summary_line = f"   _{summary}_\n" if summary else ""
        lines.append(
            f"{i}. *{article['title']}*\n"
            f"{summary_line}"
            f"   {article['url']}"
        )

    if not articles:
        lines.append("_No funding news found in the last 24 hours._")

    return "\n\n".join(lines)


def persist_articles(articles: list[dict]) -> int:
    """Save each article to the ai_intel_daily table. Returns the save count."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    saved = 0
    for article in articles:
        save_to_supabase(
            "ai_intel_daily",
            {
                "date": today,
                "source": "funding",
                "title": article["title"],
                "url": article["url"],
                "summary": article["summary"],
                "tags": ["funding", "ai"],
            },
        )
        saved += 1
    return saved


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run() -> None:
    logger.info("=== AI Funding News Tracker starting ===")
    try:
        articles = fetch_funding_articles()
        logger.info("Total funding articles collected: %d", len(articles))

        message = format_telegram_message(articles)
        send_telegram(message)

        saved = persist_articles(articles)
        logger.info("Saved %d article(s) to ai_intel_daily.", saved)

        update_module_status(
            MODULE_NAME,
            "success",
            f"Collected {len(articles)} funding articles; saved {saved}.",
        )
        logger.info("=== AI Funding News Tracker complete ===")

    except Exception as exc:  # noqa: BLE001
        logger.error("Unhandled error in ai_funding_news: %s", exc)
        update_module_status(MODULE_NAME, "error", str(exc))
        raise


if __name__ == "__main__":
    run()
