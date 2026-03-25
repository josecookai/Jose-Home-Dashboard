"""
strava_sync.py — Sync recent Strava activities to Supabase.

Env vars required (loaded from ../.env relative to this script):
    STRAVA_ACCESS_TOKEN
    STRAVA_REFRESH_TOKEN
    STRAVA_CLIENT_ID
    STRAVA_CLIENT_SECRET
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY   (service-role key so RLS insert works)
"""

from __future__ import annotations

import os
import sys
import time
import datetime
import logging
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv, set_key

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(ENV_FILE)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("strava_sync")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"
STRAVA_ATHLETE_URL = "https://www.strava.com/api/v3/athlete"

ACTIVITIES_TABLE = "strava_activities"
MODULE_STATUS_TABLE = "module_status"
MODULE_NAME = "strava_sync"

DAYS_LOOKBACK = 30
ACTIVITIES_PER_PAGE = 10


# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------

def _supabase_headers() -> dict[str, str]:
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not key:
        raise EnvironmentError("SUPABASE_SERVICE_ROLE_KEY is not set")
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def _supabase_base_url() -> str:
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "")
    if not url:
        raise EnvironmentError("SUPABASE_URL is not set")
    return url.rstrip("/")


def save_to_supabase(table: str, data: dict[str, Any] | list[dict[str, Any]]) -> None:
    """
    Upsert one or many rows into *table*.

    Raises on non-2xx HTTP responses.
    """
    base = _supabase_base_url()
    url = f"{base}/rest/v1/{table}"

    rows = data if isinstance(data, list) else [data]

    headers = _supabase_headers()
    # Ask PostgREST to merge on conflict rather than error
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"

    response = requests.post(url, json=rows, headers=headers, timeout=15)
    if not response.ok:
        raise RuntimeError(
            f"Supabase upsert failed [{response.status_code}]: {response.text}"
        )
    log.debug("Upserted %d row(s) into %s", len(rows), table)


def update_module_status(module_name: str, status: str, message: str) -> None:
    """
    Upsert a row into module_status for the given module.

    status must be 'success' or 'error' (enforced by the DB CHECK constraint).
    """
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = {
        "module_name": module_name,
        "last_run_at": now,
        "last_status": status,
        "last_message": message,
        "updated_at": now,
    }
    try:
        save_to_supabase(MODULE_STATUS_TABLE, row)
        log.info("Module status updated: %s → %s", module_name, status)
    except Exception as exc:
        # Status update failures are non-fatal — log and continue.
        log.warning("Could not update module_status: %s", exc)


# ---------------------------------------------------------------------------
# Strava OAuth helpers
# ---------------------------------------------------------------------------

def _load_strava_env() -> dict[str, str]:
    """Return the four Strava env vars, raising clearly if any are missing."""
    required = [
        "STRAVA_ACCESS_TOKEN",
        "STRAVA_REFRESH_TOKEN",
        "STRAVA_CLIENT_ID",
        "STRAVA_CLIENT_SECRET",
    ]
    values: dict[str, str] = {}
    missing = []
    for key in required:
        val = os.environ.get(key, "")
        if not val:
            missing.append(key)
        values[key] = val
    if missing:
        raise EnvironmentError(
            f"Missing required Strava env vars: {', '.join(missing)}"
        )
    return values


def _is_token_valid(access_token: str) -> bool:
    """
    Make a lightweight request to /athlete to check whether the token works.

    Returns True if the token is accepted, False if it is expired / invalid.
    """
    response = requests.get(
        STRAVA_ATHLETE_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if response.status_code == 200:
        return True
    if response.status_code == 401:
        return False
    # Other errors (5xx, network issues) — surface them rather than silently
    # triggering a refresh that might overwrite a still-valid token.
    response.raise_for_status()
    return False  # unreachable but makes mypy happy


def refresh_access_token(env: dict[str, str]) -> str:
    """
    Exchange the refresh token for a new access token and persist it to .env.

    Returns the new access token.
    """
    log.info("Refreshing Strava access token…")
    payload = {
        "client_id": env["STRAVA_CLIENT_ID"],
        "client_secret": env["STRAVA_CLIENT_SECRET"],
        "refresh_token": env["STRAVA_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }
    response = requests.post(STRAVA_TOKEN_URL, data=payload, timeout=15)
    if not response.ok:
        raise RuntimeError(
            f"Token refresh failed [{response.status_code}]: {response.text}"
        )

    token_data = response.json()
    new_access_token: str = token_data["access_token"]
    new_refresh_token: str = token_data.get("refresh_token", env["STRAVA_REFRESH_TOKEN"])

    # Persist back to .env so subsequent runs (and reloads) pick up the new tokens.
    env_path = str(ENV_FILE)
    set_key(env_path, "STRAVA_ACCESS_TOKEN", new_access_token)
    set_key(env_path, "STRAVA_REFRESH_TOKEN", new_refresh_token)

    # Also update the in-process environment so the rest of this run uses the
    # fresh token without having to re-source the file.
    os.environ["STRAVA_ACCESS_TOKEN"] = new_access_token
    os.environ["STRAVA_REFRESH_TOKEN"] = new_refresh_token

    expires_at = token_data.get("expires_at")
    if expires_at:
        human = datetime.datetime.utcfromtimestamp(expires_at).isoformat() + "Z"
        log.info("New access token obtained, expires at %s", human)
    else:
        log.info("New access token obtained")

    return new_access_token


def get_valid_access_token() -> str:
    """
    Return a valid Strava access token, refreshing if necessary.
    """
    env = _load_strava_env()
    access_token = env["STRAVA_ACCESS_TOKEN"]

    if _is_token_valid(access_token):
        log.info("Existing access token is valid")
        return access_token

    log.info("Access token invalid or expired — refreshing…")
    return refresh_access_token(env)


# ---------------------------------------------------------------------------
# Strava API
# ---------------------------------------------------------------------------

def fetch_recent_activities(access_token: str, days: int = DAYS_LOOKBACK) -> list[dict]:
    """
    Fetch up to ACTIVITIES_PER_PAGE activities from the last *days* days.
    """
    after_ts = int(time.time()) - days * 86_400
    params = {
        "per_page": ACTIVITIES_PER_PAGE,
        "after": after_ts,
    }
    response = requests.get(
        STRAVA_ACTIVITIES_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
        timeout=15,
    )
    if not response.ok:
        raise RuntimeError(
            f"Failed to fetch activities [{response.status_code}]: {response.text}"
        )
    activities = response.json()
    log.info("Fetched %d activities from Strava", len(activities))
    return activities


# ---------------------------------------------------------------------------
# Data transformation
# ---------------------------------------------------------------------------

def _parse_date(start_date: str) -> str:
    """Convert ISO 8601 datetime string to YYYY-MM-DD."""
    # start_date looks like "2024-01-15T09:30:00Z"
    return start_date[:10]


def transform_activity(raw: dict) -> dict[str, Any]:
    """Map a raw Strava activity dict to the strava_activities table schema."""
    avg_hr = raw.get("average_heartrate")
    return {
        "strava_id": int(raw["id"]),
        "date": _parse_date(raw["start_date"]),
        "activity_type": raw.get("type", "Unknown"),
        "name": raw.get("name"),
        "distance_km": round(raw.get("distance", 0) / 1000, 3),
        "duration_min": round(raw.get("moving_time", 0) / 60, 2),
        "elevation_m": raw.get("total_elevation_gain"),
        "avg_hr": float(avg_hr) if avg_hr is not None else None,
    }


# ---------------------------------------------------------------------------
# Main sync logic
# ---------------------------------------------------------------------------

def sync_strava_activities() -> None:
    """
    Full sync pipeline:
      1. Obtain valid access token (refresh if needed).
      2. Fetch recent activities from Strava.
      3. Transform and upsert each activity into Supabase.
      4. Update module_status.
    """
    log.info("=== Strava sync started ===")

    try:
        access_token = get_valid_access_token()
        raw_activities = fetch_recent_activities(access_token)

        if not raw_activities:
            message = "No activities found in the last 30 days"
            log.info(message)
            update_module_status(MODULE_NAME, "success", message)
            return

        rows = [transform_activity(a) for a in raw_activities]

        save_to_supabase(ACTIVITIES_TABLE, rows)

        message = f"Synced {len(rows)} activities"
        log.info(message)
        update_module_status(MODULE_NAME, "success", message)

    except EnvironmentError as exc:
        log.error("Configuration error: %s", exc)
        update_module_status(MODULE_NAME, "error", f"Config error: {exc}")
        sys.exit(1)

    except requests.RequestException as exc:
        log.error("Network error: %s", exc)
        update_module_status(MODULE_NAME, "error", f"Network error: {exc}")
        sys.exit(1)

    except Exception as exc:  # noqa: BLE001
        log.error("Unexpected error: %s", exc, exc_info=True)
        update_module_status(MODULE_NAME, "error", f"Unexpected error: {exc}")
        sys.exit(1)

    log.info("=== Strava sync complete ===")


if __name__ == "__main__":
    sync_strava_activities()
