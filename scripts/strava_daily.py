#!/usr/bin/env python3
"""
strava_daily.py — Strava Daily Summary Report

Reads today's activity and the last 7 days of data from Supabase (populated by
strava_sync.py), then formats a motivational daily report and sends it via
Telegram.

Environment variables (via .env or shell):
    NEXT_PUBLIC_SUPABASE_URL   or  SUPABASE_URL
    SUPABASE_SERVICE_KEY       or  SUPABASE_SERVICE_ROLE_KEY
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID

Scheduled usage (see crontab.txt — runs after strava_sync.py at 08:05 GMT+8):
    5 0 * * * /usr/bin/python3 /home/ubuntu/jose-dashboard/scripts/strava_daily.py
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

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
log = logging.getLogger("strava_daily")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL") or os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

MODULE_NAME = "strava_daily"
ACTIVITIES_TABLE = "strava_activities"
MODULE_STATUS_TABLE = "module_status"

REQUEST_TIMEOUT = 10  # seconds

# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------


def _supabase_headers() -> dict[str, str]:
    if not SUPABASE_KEY:
        raise EnvironmentError("Supabase key not set (SUPABASE_SERVICE_KEY or SUPABASE_SERVICE_ROLE_KEY)")
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def query_supabase(table: str, params: str = "") -> list[dict[str, Any]]:
    """Return rows from *table* matching the PostgREST *params* query string."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        log.warning("Supabase credentials not configured — skipping query")
        return []
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table}"
    if params:
        url = f"{url}?{params}"
    try:
        response = requests.get(url, headers=_supabase_headers(), timeout=REQUEST_TIMEOUT)
        if response.ok:
            return response.json()
        log.error("Supabase query failed [%s]: %s", response.status_code, response.text)
        return []
    except requests.RequestException as exc:
        log.error("Supabase network error: %s", exc)
        return []


def save_to_supabase(table: str, data: dict[str, Any]) -> None:
    """Upsert a single row into *table*."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        log.warning("Supabase credentials not configured — skipping save")
        return
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table}"
    headers = {
        **_supabase_headers(),
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    try:
        response = requests.post(url, json=data, headers=headers, timeout=REQUEST_TIMEOUT)
        if not response.ok:
            log.error("Supabase upsert failed [%s]: %s", response.status_code, response.text)
    except requests.RequestException as exc:
        log.error("Supabase network error during save: %s", exc)


def update_module_status(name: str, status: str, message: str = "") -> None:
    """Upsert a run record into module_status."""
    now = datetime.now(timezone.utc).isoformat() + "Z"
    save_to_supabase(
        MODULE_STATUS_TABLE,
        {
            "module_name": name,
            "last_run_at": now,
            "last_status": status,
            "last_message": message,
            "updated_at": now,
        },
    )
    log.info("Module status updated: %s → %s", name, status)


# ---------------------------------------------------------------------------
# Telegram helper
# ---------------------------------------------------------------------------


def send_telegram(msg: str) -> None:
    """Send *msg* to the configured Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram credentials not configured — skipping notification")
        return
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            timeout=REQUEST_TIMEOUT,
        )
        if response.ok:
            log.info("Telegram message sent")
        else:
            log.error("Telegram send failed [%s]: %s", response.status_code, response.text)
    except requests.RequestException as exc:
        log.error("Telegram network error: %s", exc)


# ---------------------------------------------------------------------------
# Data retrieval
# ---------------------------------------------------------------------------


def _today_date_str() -> str:
    """Return today's date in YYYY-MM-DD (local system time)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _week_start_date_str() -> str:
    """Return the date 7 days ago in YYYY-MM-DD."""
    return (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")


def fetch_todays_activity() -> dict[str, Any] | None:
    """
    Return the most recent activity recorded today, or None if there is none.

    Selects the row with the highest strava_id (latest upload) for today.
    """
    today = _today_date_str()
    rows = query_supabase(
        ACTIVITIES_TABLE,
        f"date=eq.{today}&order=strava_id.desc&limit=1",
    )
    return rows[0] if rows else None


def fetch_weekly_activities() -> list[dict[str, Any]]:
    """Return all activities from the last 7 days stored in Supabase."""
    week_start = _week_start_date_str()
    return query_supabase(
        ACTIVITIES_TABLE,
        f"date=gte.{week_start}&order=date.asc",
    )


# ---------------------------------------------------------------------------
# Calculations
# ---------------------------------------------------------------------------


def calculate_weekly_totals(activities: list[dict[str, Any]]) -> dict[str, float | int]:
    """Aggregate distance, duration, and count across *activities*."""
    total_km = 0.0
    total_min = 0.0
    count = 0

    for act in activities:
        dist = act.get("distance_km")
        dur = act.get("duration_min")
        if dist is not None:
            total_km += float(dist)
        if dur is not None:
            total_min += float(dur)
        count += 1

    return {
        "total_km": round(total_km, 2),
        "total_min": round(total_min, 1),
        "count": count,
    }


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def format_report(
    today_activity: dict[str, Any] | None,
    weekly_totals: dict[str, float | int],
    report_date: str,
) -> str:
    """Build the motivational daily report string."""
    lines: list[str] = []

    lines.append(f"🏃 *Strava Daily Sync — {report_date}*")
    lines.append("")

    if today_activity:
        name = today_activity.get("name") or "Activity"
        distance_km = today_activity.get("distance_km", 0.0)
        duration_min = today_activity.get("duration_min", 0.0)
        avg_hr = today_activity.get("avg_hr")

        hr_str = f"{avg_hr:.0f}bpm" if avg_hr is not None else "N/A"
        lines.append(
            f"Today: {name} | {distance_km}km | {duration_min:.0f}min | HR: {hr_str}"
        )
    else:
        lines.append("Today: No activity recorded yet.")

    lines.append("")
    lines.append("📅 This Week:")
    lines.append(f"- Total Distance: {weekly_totals['total_km']}km")
    lines.append(f"- Total Time: {weekly_totals['total_min']:.0f}min")
    lines.append(f"- Activities: {weekly_totals['count']}")
    lines.append("")
    lines.append("💪 Keep it up!")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run() -> None:
    log.info("=== strava_daily started ===")

    report_date = _today_date_str()

    try:
        today_activity = fetch_todays_activity()
        if today_activity:
            log.info("Today's activity: %s", today_activity.get("name"))
        else:
            log.info("No activity found for today (%s)", report_date)

        weekly_activities = fetch_weekly_activities()
        log.info("Weekly activities fetched: %d", len(weekly_activities))

        weekly_totals = calculate_weekly_totals(weekly_activities)
        log.info(
            "Weekly totals — %.2fkm | %.0fmin | %d activities",
            weekly_totals["total_km"],
            weekly_totals["total_min"],
            weekly_totals["count"],
        )

        report = format_report(today_activity, weekly_totals, report_date)
        log.info("Report:\n%s", report)

        send_telegram(report)

        summary = (
            f"today={'yes' if today_activity else 'no'}, "
            f"week={weekly_totals['total_km']}km/{weekly_totals['count']} activities"
        )
        update_module_status(MODULE_NAME, "success", summary)

    except EnvironmentError as exc:
        log.error("Configuration error: %s", exc)
        update_module_status(MODULE_NAME, "error", f"Config error: {exc}")
        sys.exit(1)

    except Exception as exc:  # noqa: BLE001
        log.error("Unexpected error: %s", exc, exc_info=True)
        update_module_status(MODULE_NAME, "error", f"Unexpected error: {exc}")
        sys.exit(1)

    log.info("=== strava_daily complete ===")


if __name__ == "__main__":
    run()
