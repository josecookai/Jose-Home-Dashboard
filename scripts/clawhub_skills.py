#!/usr/bin/env python3
"""
clawhub_skills.py — ClawHub Skills Ranking Report (Issue #8)

Searches GitHub for claude-code-related skills repositories and compiles a
ranked Top-30 list sorted by stars.

Steps:
  1. Search GitHub for topic:claude-code + topic:skills repos (top 30 by stars)
  2. Search GitHub for files named skill.md mentioning "claude"
  3. Deduplicate, sort by stars, keep top 30
  4. Format a ranked Markdown report
  5. Save full report to /tmp/clawhub_top100.txt
  6. Send top 10 via Telegram
  7. Save to `reports` table: {date, module, content}
  8. Update module_status with module_name='clawhub_skills'
"""

import logging
import os
from datetime import datetime, timezone
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
logger = logging.getLogger("clawhub_skills")

# ---------------------------------------------------------------------------
# Inline helpers (as specified)
# ---------------------------------------------------------------------------

SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL") or os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

MODULE_NAME = "clawhub_skills"
TODAY = datetime.now(timezone.utc).date().isoformat()
REPORT_PATH = "/tmp/clawhub_top100.txt"


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
# GitHub helpers
# ---------------------------------------------------------------------------

def _github_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def _search_repos(query: str, per_page: int = 30) -> list[dict]:
    """Search GitHub repositories and return the raw item list."""
    url = "https://api.github.com/search/repositories"
    params = {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": min(per_page, 100),
    }
    try:
        response = requests.get(
            url,
            params=params,
            headers=_github_headers(),
            timeout=15,
        )
        response.raise_for_status()
        items = response.json().get("items", [])
        logger.info("GitHub search '%s': returned %d items.", query, len(items))
        return items
    except requests.HTTPError as exc:
        logger.error(
            "GitHub API HTTP error (%s) for query '%s': %s",
            exc.response.status_code,
            query,
            exc.response.text[:300],
        )
        return []
    except requests.RequestException as exc:
        logger.error("GitHub API network error for query '%s': %s", query, exc)
        return []
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error searching GitHub ('%s'): %s", query, exc)
        return []


def _search_code_repos(query: str) -> list[dict]:
    """
    Search GitHub code and return unique repository items.

    The code search API returns file-level results; we deduplicate by repo
    full_name and fetch basic repo info (stars, description) for ranking.
    """
    url = "https://api.github.com/search/code"
    params = {
        "q": query,
        "per_page": 30,
    }
    try:
        response = requests.get(
            url,
            params=params,
            headers=_github_headers(),
            timeout=15,
        )
        response.raise_for_status()
        items = response.json().get("items", [])
        logger.info("GitHub code search '%s': returned %d file hits.", query, len(items))
    except requests.HTTPError as exc:
        logger.error(
            "GitHub code search HTTP error (%s): %s",
            exc.response.status_code,
            exc.response.text[:300],
        )
        return []
    except requests.RequestException as exc:
        logger.error("GitHub code search network error: %s", exc)
        return []
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error in code search: %s", exc)
        return []

    # Deduplicate repositories and collect unique full_names
    seen: set[str] = set()
    repo_items: list[dict] = []
    for item in items:
        repo = item.get("repository", {})
        full_name = repo.get("full_name", "")
        if not full_name or full_name in seen:
            continue
        seen.add(full_name)
        # The repository object in code search results has limited fields;
        # build a minimal compatible structure.
        repo_items.append(
            {
                "full_name": full_name,
                "html_url": repo.get("html_url", f"https://github.com/{full_name}"),
                "description": repo.get("description", ""),
                "stargazers_count": 0,  # not available in code search results
                "language": "",
                "topics": [],
                "_source": "code_search",
            }
        )

    logger.info("Code search unique repos: %d", len(repo_items))
    return repo_items


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def _normalize_repo(item: dict) -> dict:
    """Normalize a GitHub API repo item into a consistent internal structure."""
    return {
        "full_name": item.get("full_name", ""),
        "html_url": item.get("html_url", ""),
        "description": (item.get("description") or "").strip(),
        "stars": item.get("stargazers_count", 0),
        "language": item.get("language") or "",
        "topics": item.get("topics", []),
        "_source": item.get("_source", "topic_search"),
    }


def fetch_skills_repos() -> list[dict]:
    """
    Collect and deduplicate skill repos from two GitHub searches.

    Returns a sorted list (descending stars), capped at 30 entries.
    """
    raw: list[dict] = []

    # Search 1: repos tagged with claude-code + skills topics
    topic_items = _search_repos(
        "topic:claude-code topic:skills",
        per_page=30,
    )
    raw.extend(topic_items)

    # Search 2: files named skill.md that mention "claude"
    code_items = _search_code_repos("filename:skill.md in:file claude")
    raw.extend(code_items)

    # Normalize and deduplicate by full_name
    seen: set[str] = set()
    deduped: list[dict] = []
    for item in raw:
        normalized = _normalize_repo(item)
        name = normalized["full_name"]
        if not name or name in seen:
            continue
        seen.add(name)
        deduped.append(normalized)

    # Sort descending by stars; code-search results (stars=0) fall to the bottom
    deduped.sort(key=lambda r: r["stars"], reverse=True)

    top30 = deduped[:30]
    logger.info("Total unique repos after deduplication: %d (keeping top 30).", len(deduped))
    return top30


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def _truncate(text: str, max_len: int = 100) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def build_full_report(repos: list[dict], report_date: str) -> str:
    """Build the full ranked Markdown report."""
    lines: list[str] = [
        f"# ClawHub Skills Ranking — {report_date}",
        f"_Top {len(repos)} Claude Code Skills Repositories_",
        "",
    ]

    for rank, repo in enumerate(repos, start=1):
        name = repo["full_name"]
        stars = repo["stars"]
        desc = _truncate(repo["description"], 100) if repo["description"] else "—"
        url = repo["html_url"]
        lang = repo["language"]
        lang_str = f" [{lang}]" if lang else ""

        lines.append(f"## {rank}. {name}{lang_str}")
        lines.append(f"⭐ {stars} stars")
        lines.append(f"📝 {desc}")
        lines.append(f"🔗 {url}")
        lines.append("")

    return "\n".join(lines)


def build_telegram_top10(repos: list[dict], report_date: str) -> str:
    """Build the Telegram message for the top-10 repos."""
    lines: list[str] = [
        f"🛠 *ClawHub Skills Top 10 — {report_date}*",
        "",
    ]
    for rank, repo in enumerate(repos[:10], start=1):
        name = repo["full_name"]
        stars = repo["stars"]
        desc = _truncate(repo["description"], 70) if repo["description"] else "—"
        url = repo["html_url"]
        lines.append(f"{rank}\\. [{name}]({url}) ⭐{stars}")
        lines.append(f"   _{desc}_")
    return "\n".join(lines)


def build_plaintext_report(repos: list[dict], report_date: str) -> str:
    """Build the plaintext list for /tmp/clawhub_top100.txt."""
    lines: list[str] = [
        f"ClawHub Skills Ranking — {report_date}",
        f"Top {len(repos)} Claude Code Skills Repositories",
        "=" * 60,
        "",
    ]
    for rank, repo in enumerate(repos, start=1):
        name = repo["full_name"]
        stars = repo["stars"]
        desc = repo["description"] or "—"
        url = repo["html_url"]
        lines.append(f"{rank:>3}. {name}  [{stars} stars]")
        lines.append(f"     {desc}")
        lines.append(f"     {url}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def save_report_to_file(content: str, path: str) -> bool:
    """Write the report to a local file."""
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        logger.info("Report saved to %s", path)
        return True
    except OSError as exc:
        logger.error("Failed to write report to %s: %s", path, exc)
        return False


def save_report_to_supabase(report_date: str, full_report: str) -> bool:
    """Upsert the full report into the `reports` table."""
    return save_to_supabase(
        "reports",
        {
            "date": report_date,
            "module": MODULE_NAME,
            "content": full_report,
        },
    )


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def run() -> None:
    logger.info("=== ClawHub Skills Ranking starting for %s ===", TODAY)

    errors: list[str] = []

    # 1 & 2. Fetch repos
    repos: list[dict] = []
    try:
        repos = fetch_skills_repos()
        logger.info("Total repos for ranking: %d", len(repos))
    except Exception as exc:  # noqa: BLE001
        logger.error("Repo fetch failed: %s", exc, exc_info=True)
        errors.append(f"fetch: {exc}")

    # 3 & 4. Build reports
    full_md_report = build_full_report(repos, TODAY)
    plaintext_report = build_plaintext_report(repos, TODAY)
    telegram_msg = build_telegram_top10(repos, TODAY)

    # 5. Save to /tmp/clawhub_top100.txt
    if not save_report_to_file(plaintext_report, REPORT_PATH):
        errors.append(f"file_write: failed to save {REPORT_PATH}")

    # 6. Send top 10 via Telegram
    send_telegram(telegram_msg)

    # 7. Save to `reports` table
    if not save_report_to_supabase(TODAY, full_md_report):
        errors.append("supabase: failed to save report")

    # 8. Update module status
    if errors:
        status = "error"
        message = (
            f"Completed with errors: {'; '.join(errors)}. "
            f"Ranked {len(repos)} repos."
        )
    else:
        status = "success"
        message = (
            f"Ranked {len(repos)} claude-code skills repos for {TODAY}. "
            f"Report saved to {REPORT_PATH}."
        )

    update_module_status(MODULE_NAME, status, message)
    logger.info("=== ClawHub Skills Ranking complete: %s ===", message)


if __name__ == "__main__":
    run()
