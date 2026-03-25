"""
AI Intelligence fetcher - collects trending AI content from arXiv, HuggingFace, and GitHub,
then saves results to the Supabase `ai_intel_daily` table.
"""

import os
import json
import logging
from datetime import date, datetime, timezone

import feedparser
import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get(
    "NEXT_PUBLIC_SUPABASE_ANON_KEY", ""
)
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

TODAY = date.today().isoformat()


# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------

def _supabase_headers(extra: dict | None = None) -> dict:
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def save_to_supabase(table: str, data: dict) -> bool:
    """POST a single record to `table` using upsert (merge-duplicates)."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("Supabase credentials not configured; skipping save.")
        return False

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = _supabase_headers({"Prefer": "resolution=merge-duplicates"})

    try:
        response = requests.post(url, headers=headers, json=data, timeout=15)
        response.raise_for_status()
        return True
    except requests.HTTPError as exc:
        logger.error("HTTP error saving to %s: %s — %s", table, exc, exc.response.text)
        return False
    except requests.RequestException as exc:
        logger.error("Request error saving to %s: %s", table, exc)
        return False


def _record_exists(table: str, title: str, record_date: str) -> bool:
    """Return True if a record with the same title + date already exists."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    params = {
        "title": f"eq.{title}",
        "date": f"eq.{record_date}",
        "select": "title",
        "limit": "1",
    }
    headers = _supabase_headers()

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return len(response.json()) > 0
    except requests.RequestException as exc:
        logger.warning("Could not check for existing record: %s", exc)
        return False


def update_module_status(module_name: str, status: str, message: str) -> None:
    """Write the run status of a module back to Supabase (best-effort)."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return

    url = f"{SUPABASE_URL}/rest/v1/module_status"
    headers = _supabase_headers({"Prefer": "resolution=merge-duplicates"})
    payload = {
        "module_name": module_name,
        "last_run_at": datetime.now(timezone.utc).isoformat(),
        "last_status": status,
        "last_message": message,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        response = requests.post(url, headers=headers, json=payload,
                                 params={"on_conflict": "module_name"}, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Could not update module status for %s: %s", module_name, exc)


# ---------------------------------------------------------------------------
# Source fetchers
# ---------------------------------------------------------------------------

def _is_today(entry) -> bool:
    """Return True if a feedparser entry was published today (UTC)."""
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                entry_date = date(*parsed[:3])
                return entry_date == date.today()
            except (TypeError, ValueError):
                continue
    # If we cannot determine the date, include the entry (graceful fallback).
    return True


def fetch_arxiv() -> list[dict]:
    """Fetch top-5 AI/ML papers published today from arXiv RSS feeds."""
    results: list[dict] = []
    categories = [("cs.AI", "cs.AI"), ("cs.LG", "cs.LG")]

    for feed_id, category_tag in categories:
        url = f"https://export.arxiv.org/rss/{feed_id}"
        try:
            feed = feedparser.parse(url)
            if feed.bozo and not feed.entries:
                raise ValueError(f"Feed parse error: {feed.bozo_exception}")

            count = 0
            for entry in feed.entries:
                if count >= 5:
                    break
                if not _is_today(entry):
                    continue

                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                summary = entry.get("summary", entry.get("description", "")).strip()

                if not title or not link:
                    continue

                results.append(
                    {
                        "date": TODAY,
                        "source": "arxiv",
                        "title": title,
                        "url": link,
                        "summary": summary,
                        "tags": ["arxiv", category_tag],
                    }
                )
                count += 1

            logger.info("arXiv [%s]: collected %d papers", feed_id, count)
        except Exception as exc:  # noqa: BLE001
            logger.error("Error fetching arXiv [%s]: %s", feed_id, exc)

    return results


def fetch_huggingface() -> list[dict]:
    """Fetch top-5 trending models from the HuggingFace API."""
    url = "https://huggingface.co/api/models"
    params = {"sort": "trending", "limit": 5}

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        models = response.json()
    except requests.RequestException as exc:
        logger.error("Error fetching HuggingFace trending models: %s", exc)
        return []
    except json.JSONDecodeError as exc:
        logger.error("JSON decode error from HuggingFace API: %s", exc)
        return []

    results: list[dict] = []
    for model in models:
        model_id = model.get("modelId") or model.get("id", "")
        if not model_id:
            continue

        pipeline_tag = model.get("pipeline_tag") or "unknown"
        downloads = model.get("downloads", 0)
        summary = f"Pipeline: {pipeline_tag}. Downloads: {downloads:,}."

        results.append(
            {
                "date": TODAY,
                "source": "huggingface",
                "title": model_id,
                "url": f"https://huggingface.co/{model_id}",
                "summary": summary,
                "tags": ["huggingface"],
            }
        )

    logger.info("HuggingFace: collected %d models", len(results))
    return results


def fetch_github() -> list[dict]:
    """Fetch top-5 AI/ML repos by stars from GitHub Search API."""
    url = "https://api.github.com/search/repositories"
    params = {
        "q": "topic:ai topic:machine-learning",
        "sort": "stars",
        "order": "desc",
        "per_page": 5,
    }
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        logger.error("Error fetching GitHub trending repos: %s", exc)
        return []
    except json.JSONDecodeError as exc:
        logger.error("JSON decode error from GitHub API: %s", exc)
        return []

    results: list[dict] = []
    for repo in data.get("items", []):
        full_name = repo.get("full_name", "")
        html_url = repo.get("html_url", "")
        description = repo.get("description") or ""
        language = repo.get("language") or "unknown"

        if not full_name or not html_url:
            continue

        tags = ["github"]
        if language and language != "unknown":
            tags.append(language)

        results.append(
            {
                "date": TODAY,
                "source": "github",
                "title": full_name,
                "url": html_url,
                "summary": description,
                "tags": tags,
            }
        )

    logger.info("GitHub: collected %d repos", len(results))
    return results


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _save_items(items: list[dict], source_name: str) -> tuple[int, int]:
    """
    Save a list of items to Supabase, skipping duplicates.

    Returns (saved_count, skipped_count).
    """
    saved = 0
    skipped = 0

    for item in items:
        if _record_exists("ai_intel_daily", item["title"], item["date"]):
            logger.debug("Skipping duplicate: %s", item["title"])
            skipped += 1
            continue

        if save_to_supabase("ai_intel_daily", item):
            saved += 1
        else:
            logger.warning("Failed to save item: %s", item["title"])

    logger.info(
        "[%s] saved=%d skipped=%d", source_name, saved, skipped
    )
    return saved, skipped


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def run() -> None:
    sources = [
        ("arxiv", fetch_arxiv),
        ("huggingface", fetch_huggingface),
        ("github", fetch_github),
    ]

    for source_name, fetcher in sources:
        logger.info("--- Fetching %s ---", source_name)
        try:
            items = fetcher()
            saved, skipped = _save_items(items, source_name)
            update_module_status(
                module_name=f"ai_intel_{source_name}",
                status="success",
                message=f"Fetched {len(items)} items; saved {saved}, skipped {skipped}.",
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Unhandled error in source [%s]: %s", source_name, exc)
            update_module_status(
                module_name=f"ai_intel_{source_name}",
                status="error",
                message=str(exc),
            )

    # Overall module status for the dashboard status bar
    update_module_status(
        module_name="ai_intelligence",
        status="success",
        message="Daily AI intel fetch complete.",
    )

    logger.info("AI intelligence fetch complete.")


if __name__ == "__main__":
    run()
