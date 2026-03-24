"""
common.py — Shared utilities for Jose Home Dashboard scripts.

Provides:
  - save_to_supabase(table, data, unique_on=None)
  - update_module_status(module_name, status, message)
  - send_telegram(message)
"""

import os
import logging
from datetime import datetime, timezone
from typing import Any

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
logger = logging.getLogger("common")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _supabase_headers(use_service_key: bool = True) -> dict[str, str]:
    """Return Supabase REST API headers."""
    key = (
        os.environ.get("SUPABASE_SERVICE_KEY")
        if use_service_key
        else os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    )
    if not key:
        raise EnvironmentError(
            "Supabase key not found. Set SUPABASE_SERVICE_KEY or "
            "NEXT_PUBLIC_SUPABASE_ANON_KEY in your .env file."
        )
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _supabase_url(table: str) -> str:
    base = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    if not base:
        raise EnvironmentError(
            "NEXT_PUBLIC_SUPABASE_URL is not set in your .env file."
        )
    return f"{base}/rest/v1/{table}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_to_supabase(
    table: str,
    data: dict[str, Any],
    unique_on: list[str] | None = None,
) -> dict[str, Any] | None:
    """
    Upsert *data* into *table* via the Supabase REST API.

    Parameters
    ----------
    table:     Supabase table name.
    data:      Row dict to insert / upsert.
    unique_on: Column names that form the conflict key for upserts.
               When supplied the request uses ``Prefer: resolution=merge-duplicates``
               and the ``on_conflict`` query parameter so duplicate rows are
               updated rather than raising an error.

    Returns the inserted/updated row dict on success, or None on failure.
    """
    url = _supabase_url(table)
    headers = _supabase_headers()

    params: dict[str, str] = {}
    if unique_on:
        headers["Prefer"] = "return=representation,resolution=merge-duplicates"
        params["on_conflict"] = ",".join(unique_on)

    try:
        response = requests.post(url, json=data, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        rows = response.json()
        logger.info("Saved row to %s (id=%s)", table, rows[0].get("id") if rows else "?")
        return rows[0] if rows else None
    except requests.HTTPError as exc:
        logger.error(
            "HTTP error saving to %s: %s — %s",
            table,
            exc.response.status_code,
            exc.response.text[:300],
        )
    except requests.RequestException as exc:
        logger.error("Network error saving to %s: %s", table, exc)
    return None


def update_module_status(
    module_name: str,
    status: str,
    message: str,
) -> None:
    """
    Upsert a row in the ``module_status`` table.

    Parameters
    ----------
    module_name: Unique name that identifies the cron script (e.g. 'leaps_monitor').
    status:      'success' or 'error'.
    message:     Human-readable summary or error description.
    """
    if status not in ("success", "error"):
        raise ValueError("status must be 'success' or 'error'")

    now = datetime.now(timezone.utc).isoformat()
    save_to_supabase(
        table="module_status",
        data={
            "module_name": module_name,
            "last_run_at": now,
            "last_status": status,
            "last_message": message,
            "updated_at": now,
        },
        unique_on=["module_name"],
    )
    logger.info("Module status updated: %s → %s", module_name, status)


def send_telegram(message: str) -> bool:
    """
    Send *message* to the configured Telegram chat.

    Returns True on success, False on failure.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        logger.warning(
            "Telegram not configured — set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."
        )
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Telegram message sent (chat_id=%s)", chat_id)
        return True
    except requests.HTTPError as exc:
        logger.error(
            "Telegram HTTP error: %s — %s",
            exc.response.status_code,
            exc.response.text[:300],
        )
    except requests.RequestException as exc:
        logger.error("Telegram network error: %s", exc)
    return False
