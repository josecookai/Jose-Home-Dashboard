#!/usr/bin/env python3
"""
tech_radar.py — Daily Tech Radar Report (Issue #7)

Fetches:
  - HuggingFace trending papers (daily_papers API, fallback: HTML scrape)
  - GitHub trending AI/Agent/LLM repos (created in the last 7 days)
  - GitHub trending Crypto/DeFi repos

Sends a Markdown report via Telegram, saves each item to `ai_intel_daily`,
and updates `module_status` with module_name='tech_radar'.
"""

import logging
import os
from datetime import date, datetime, timedelta, timezone
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
logger = logging.getLogger("tech_radar")

# ---------------------------------------------------------------------------
# Inline helpers (as specified)
# ---------------------------------------------------------------------------

SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL") or os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

MODULE_NAME = "tech_radar"
TODAY = date.today().isoformat()


def save_to_supabase(table: str, data: dict) -> bool:
    """Upsert a row into a Supabase table via the REST API."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("Supabase credentials not configured; skipping save.")
        return False

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
        return True
    except requests.HTTPError as exc:
        logger.error(
            "HTTP error saving to %s: %s — %s",
            table,
            exc.response.status_code,
            exc.response.text[:300],
        )
    except requests.RequestException as exc:
        logger.error("Network error saving to %s: %s", table, exc)
    return False


def update_module_status(name: str, status: str, message: str = "") -> None:
    """Upsert a row in module_status."""
    now = datetime.now(timezone.utc).isoformat()
    save_to_supabase(
        "module_status",
        {
            "module_name": name,
            "last_run_at": now,
            "last_status": status,
            "last_message": message,
            "updated_at": now,
        },
    )
    logger.info("Module status updated: %s → %s", name, status)


def send_telegram(msg: str) -> bool:
    """Send a Markdown message to the configured Telegram chat."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning(
            "Telegram not configured — set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."
        )
        return False
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
            timeout=10,
        )
        response.raise_for_status()
        logger.info("Telegram message sent.")
        return True
    except requests.RequestException as exc:
        logger.error("Telegram error: %s", exc)
    return False


# ---------------------------------------------------------------------------
# HuggingFace papers
# ---------------------------------------------------------------------------

def _hf_papers_from_api(today: str) -> list[dict]:
    """Fetch papers from HuggingFace daily_papers API."""
    url = f"https://huggingface.co/api/daily_papers?date={today}"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        papers = response.json()
        if not isinstance(papers, list):
            logger.warning("Unexpected HuggingFace API response shape: %s", type(papers))
            return []
        results = []
        for paper in papers[:10]:
            paper_id = paper.get("paper", {}).get("id") or paper.get("id", "")
            title = (
                paper.get("paper", {}).get("title")
                or paper.get("title", "")
            ).strip()
            summary = (
                paper.get("paper", {}).get("summary")
                or paper.get("summary", "")
            ).strip()
            if not title:
                continue
            paper_url = (
                f"https://huggingface.co/papers/{paper_id}"
                if paper_id
                else "https://huggingface.co/papers"
            )
            results.append(
                {
                    "date": today,
                    "source": "huggingface",
                    "title": title,
                    "url": paper_url,
                    "summary": summary[:500] if summary else "",
                    "tags": ["huggingface", "paper"],
                }
            )
        logger.info("HuggingFace API: fetched %d papers.", len(results))
        return results
    except requests.RequestException as exc:
        logger.warning("HuggingFace API failed: %s", exc)
        return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unexpected error in HuggingFace API fetch: %s", exc)
        return []


def _hf_papers_from_scrape(today: str) -> list[dict]:
    """Fallback: scrape HuggingFace /papers page with BeautifulSoup."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("beautifulsoup4 is not installed. Run: pip install beautifulsoup4")
        return []

    url = "https://huggingface.co/papers"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; tech-radar-bot/1.0)"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("HuggingFace scrape failed: %s", exc)
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    # Paper titles typically appear in <h3> tags inside article cards
    results = []
    seen: set[str] = set()

    # Look for article elements with paper links
    for article in soup.find_all("article")[:15]:
        title_tag = article.find(["h3", "h2"])
        if title_tag is None:
            continue
        title = title_tag.get_text(strip=True)
        if not title or title in seen:
            continue
        seen.add(title)

        link_tag = article.find("a", href=True)
        href = link_tag["href"] if link_tag else ""
        paper_url = (
            f"https://huggingface.co{href}"
            if href.startswith("/")
            else href or "https://huggingface.co/papers"
        )

        results.append(
            {
                "date": today,
                "source": "huggingface",
                "title": title,
                "url": paper_url,
                "summary": "",
                "tags": ["huggingface", "paper", "scraped"],
            }
        )

    logger.info("HuggingFace scrape: found %d papers.", len(results))
    return results[:10]


def fetch_huggingface_papers() -> list[dict]:
    """Fetch HuggingFace trending papers; fall back to scraping on API failure."""
    results = _hf_papers_from_api(TODAY)
    if not results:
        logger.info("Falling back to HuggingFace HTML scrape.")
        results = _hf_papers_from_scrape(TODAY)
    return results


# ---------------------------------------------------------------------------
# GitHub trending repos
# ---------------------------------------------------------------------------

def _github_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def _fetch_github_repos(query: str, per_page: int = 10) -> list[dict]:
    """Search GitHub repositories with the given query string."""
    seven_days_ago = (date.today() - timedelta(days=7)).isoformat()
    full_query = f"{query} created:>{seven_days_ago}"

    url = "https://api.github.com/search/repositories"
    params = {
        "q": full_query,
        "sort": "stars",
        "order": "desc",
        "per_page": per_page,
    }

    try:
        response = requests.get(
            url,
            params=params,
            headers=_github_headers(),
            timeout=15,
        )
        response.raise_for_status()
        return response.json().get("items", [])
    except requests.HTTPError as exc:
        logger.error(
            "GitHub API HTTP error (%s): %s",
            exc.response.status_code,
            exc.response.text[:300],
        )
        return []
    except requests.RequestException as exc:
        logger.error("GitHub API network error: %s", exc)
        return []
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error querying GitHub: %s", exc)
        return []


def _repo_to_record(repo: dict, category: str) -> dict:
    """Convert a GitHub API repo item into an ai_intel_daily record."""
    full_name = repo.get("full_name", "")
    html_url = repo.get("html_url", "")
    description = (repo.get("description") or "").strip()
    stars = repo.get("stargazers_count", 0)
    language = repo.get("language") or ""
    topics = repo.get("topics", [])

    tags = ["github", category]
    if language:
        tags.append(language.lower())
    tags.extend(topics[:5])

    return {
        "date": TODAY,
        "source": "github",
        "title": full_name,
        "url": html_url,
        "summary": description,
        "tags": list(dict.fromkeys(tags)),  # deduplicate, preserve order
        "_stars": stars,          # ephemeral field for report formatting
        "_category": category,    # ephemeral field for report formatting
    }


def fetch_ai_repos() -> list[dict]:
    """Fetch recently-created AI / Agent / LLM GitHub repos."""
    items = _fetch_github_repos("topic:agent topic:llm", per_page=10)
    results = [_repo_to_record(r, "ai") for r in items]
    logger.info("GitHub AI repos: fetched %d items.", len(results))
    return results


def fetch_crypto_repos() -> list[dict]:
    """Fetch recently-created Crypto / DeFi GitHub repos."""
    items = _fetch_github_repos("topic:crypto topic:defi", per_page=10)
    results = [_repo_to_record(r, "crypto") for r in items]
    logger.info("GitHub Crypto repos: fetched %d items.", len(results))
    return results


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def _truncate(text: str, max_len: int = 80) -> str:
    """Truncate text to max_len characters, adding ellipsis if needed."""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def build_report(
    hf_papers: list[dict],
    ai_repos: list[dict],
    crypto_repos: list[dict],
    report_date: str,
) -> str:
    """Compose the Markdown tech radar report."""
    lines: list[str] = [f"🔭 *Tech Radar — {report_date}*", ""]

    # HuggingFace papers
    lines.append("📄 *HuggingFace Papers*")
    if hf_papers:
        for i, paper in enumerate(hf_papers[:10], start=1):
            title = _truncate(paper["title"], 90)
            url = paper["url"]
            lines.append(f"{i}. {title} — {url}")
    else:
        lines.append("_No papers fetched today._")
    lines.append("")

    # AI / Agent repos
    lines.append("🤖 *Trending AI Repos*")
    if ai_repos:
        for i, repo in enumerate(ai_repos[:10], start=1):
            name = repo["title"]
            stars = repo.get("_stars", 0)
            desc = _truncate(repo["summary"], 80) if repo["summary"] else "—"
            lines.append(f"{i}. {name} ⭐{stars} — {desc}")
    else:
        lines.append("_No AI repos fetched today._")
    lines.append("")

    # Crypto / DeFi repos
    lines.append("💰 *Trending Crypto Repos*")
    if crypto_repos:
        for i, repo in enumerate(crypto_repos[:10], start=1):
            name = repo["title"]
            stars = repo.get("_stars", 0)
            desc = _truncate(repo["summary"], 80) if repo["summary"] else "—"
            lines.append(f"{i}. {name} ⭐{stars} — {desc}")
    else:
        lines.append("_No Crypto repos fetched today._")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _strip_ephemeral(record: dict) -> dict:
    """Remove helper-only keys before persisting to Supabase."""
    return {k: v for k, v in record.items() if not k.startswith("_")}


def save_items(items: list[dict], label: str) -> int:
    """Save a list of records to ai_intel_daily; return count saved."""
    saved = 0
    for item in items:
        clean = _strip_ephemeral(item)
        if save_to_supabase("ai_intel_daily", clean):
            saved += 1
    logger.info("[%s] saved %d/%d records.", label, saved, len(items))
    return saved


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def run() -> None:
    logger.info("=== Tech Radar starting for %s ===", TODAY)

    hf_papers: list[dict] = []
    ai_repos: list[dict] = []
    crypto_repos: list[dict] = []
    errors: list[str] = []

    # 1. Fetch data
    try:
        hf_papers = fetch_huggingface_papers()
    except Exception as exc:  # noqa: BLE001
        logger.error("HuggingFace fetch failed: %s", exc)
        errors.append(f"huggingface: {exc}")

    try:
        ai_repos = fetch_ai_repos()
    except Exception as exc:  # noqa: BLE001
        logger.error("GitHub AI repos fetch failed: %s", exc)
        errors.append(f"github_ai: {exc}")

    try:
        crypto_repos = fetch_crypto_repos()
    except Exception as exc:  # noqa: BLE001
        logger.error("GitHub Crypto repos fetch failed: %s", exc)
        errors.append(f"github_crypto: {exc}")

    # 2. Build and send report
    report = build_report(hf_papers, ai_repos, crypto_repos, TODAY)
    logger.info("Report:\n%s", report)

    send_telegram(report)

    # 3. Persist to Supabase
    total_saved = 0
    total_saved += save_items(hf_papers, "huggingface")
    total_saved += save_items(ai_repos, "github_ai")
    total_saved += save_items(crypto_repos, "github_crypto")

    # 4. Update module status
    if errors:
        status = "error"
        message = f"Completed with errors: {'; '.join(errors)}. Saved {total_saved} items."
    else:
        status = "success"
        total_items = len(hf_papers) + len(ai_repos) + len(crypto_repos)
        message = (
            f"Fetched {total_items} items "
            f"({len(hf_papers)} HF papers, {len(ai_repos)} AI repos, "
            f"{len(crypto_repos)} crypto repos). Saved {total_saved}."
        )

    update_module_status(MODULE_NAME, status, message)
    logger.info("=== Tech Radar complete: %s ===", message)


if __name__ == "__main__":
    run()
