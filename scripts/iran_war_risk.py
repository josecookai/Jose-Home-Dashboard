#!/usr/bin/env python3
"""
iran_war_risk.py — Iran Geopolitical Risk Monitor (Issue #10)

Fetches Polymarket odds for Iran-related markets, filters Reuters world
headlines for Iran/Middle East keywords, computes a composite risk score,
formats a Markdown brief, sends it via Telegram, and persists to Supabase.

Scheduled usage (cron example — runs daily at 08:00 UTC):
    0 8 * * * /usr/bin/python3 /path/to/iran_war_risk.py >> /var/log/iran_war_risk.log 2>&1

Environment variables (via .env or shell):
    NEXT_PUBLIC_SUPABASE_URL   or  SUPABASE_URL
    SUPABASE_SERVICE_KEY       or  SUPABASE_SERVICE_ROLE_KEY
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID
"""

import logging
import os
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
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
logger = logging.getLogger("iran_war_risk")

# ---------------------------------------------------------------------------
# Inline helpers
# ---------------------------------------------------------------------------

SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL") or os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

MODULE_NAME = "iran_war_risk"
REQUEST_TIMEOUT = 15  # seconds


def save_to_supabase(table: str, data: dict) -> bool:
    """Upsert *data* into *table* via the Supabase REST API."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("Supabase credentials not configured — skipping save.")
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
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        logger.info("Saved record to Supabase table '%s'.", table)
        return True
    except requests.RequestException as exc:
        logger.error("Failed to save to Supabase table '%s': %s", table, exc)
        return False


def update_module_status(name: str, status: str, message: str = "") -> None:
    """Upsert a row in the module_status table."""
    now = datetime.utcnow().isoformat()
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


def send_telegram(msg: str) -> bool:
    """Send *msg* to the configured Telegram chat."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning("Telegram not configured — skipping notification.")
        return False
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        logger.info("Telegram message sent.")
        return True
    except requests.RequestException as exc:
        logger.error("Failed to send Telegram message: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POLYMARKET_URL = "https://gamma-api.polymarket.com/markets"
REUTERS_RSS_URL = "https://feeds.reuters.com/reuters/worldNews"

IRAN_KEYWORDS = [
    "iran", "tehran", "irgc", "strait of hormuz", "nuclear", "israel", "hezbollah",
]

ESCALATION_KEYWORDS = [
    "attack", "strike", "war", "missile", "bomb", "invasion", "conflict",
]

# Risk score weights
RISK_BASE = 20
RISK_POLYMARKET_MODERATE = 30   # awarded when Polymarket top prob > 30%
RISK_POLYMARKET_HIGH = 20       # additional when Polymarket top prob > 60%
RISK_NEWS_VOLUME = 20           # awarded when 3+ major Iran news items today
RISK_ESCALATION_KEYWORDS = 10   # awarded when escalation keywords found in headlines

RISK_LEVELS = [
    (80, "CRITICAL"),
    (60, "HIGH"),
    (40, "ELEVATED"),
    (20, "MODERATE"),
    (0,  "LOW"),
]


def _risk_level(score: int) -> str:
    for threshold, label in RISK_LEVELS:
        if score >= threshold:
            return label
    return "LOW"


# ---------------------------------------------------------------------------
# Polymarket
# ---------------------------------------------------------------------------


def fetch_polymarket_iran_markets(limit: int = 10) -> list[dict]:
    """
    Query the Polymarket Gamma API for Iran-related active markets.

    Returns a list of dicts: {question, probability, market_slug}.
    Probability is expressed as a percentage (0–100).
    """
    try:
        response = requests.get(
            POLYMARKET_URL,
            params={"search": "iran", "active": "true", "limit": limit},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        raw = response.json()
    except requests.RequestException as exc:
        logger.error("Failed to fetch Polymarket markets: %s", exc)
        return []
    except ValueError as exc:
        logger.error("Failed to parse Polymarket JSON: %s", exc)
        return []

    markets = []
    # The API may return a list directly or a dict with a 'markets' key.
    if isinstance(raw, dict):
        items = raw.get("markets", raw.get("data", []))
    elif isinstance(raw, list):
        items = raw
    else:
        logger.warning("Unexpected Polymarket response type: %s", type(raw))
        return []

    for item in items:
        if not isinstance(item, dict):
            continue
        question = item.get("question", "")
        outcome_prices = item.get("outcomePrices")
        probability = _parse_polymarket_probability(outcome_prices)
        if question:
            markets.append(
                {
                    "question": question,
                    "probability": probability,
                    "market_slug": item.get("slug", ""),
                }
            )

    logger.info("Fetched %d Iran-related Polymarket market(s).", len(markets))
    return markets


def _parse_polymarket_probability(outcome_prices: object) -> Optional[float]:
    """
    Extract the leading 'Yes' probability from the outcomePrices field.

    outcomePrices can be a JSON string like '["0.72","0.28"]', a Python list,
    or absent.  Returns a percentage (0–100) or None.
    """
    import json as _json

    if outcome_prices is None:
        return None
    if isinstance(outcome_prices, str):
        try:
            outcome_prices = _json.loads(outcome_prices)
        except ValueError:
            return None
    if isinstance(outcome_prices, list) and outcome_prices:
        try:
            # First element is the 'Yes' probability as a decimal
            return round(float(outcome_prices[0]) * 100, 1)
        except (ValueError, TypeError):
            return None
    return None


def _top_polymarket_probability(markets: list[dict]) -> Optional[float]:
    """Return the highest non-None probability among the markets list."""
    probs = [m["probability"] for m in markets if m.get("probability") is not None]
    return max(probs) if probs else None


# ---------------------------------------------------------------------------
# Reuters RSS headlines
# ---------------------------------------------------------------------------


def fetch_reuters_iran_headlines(max_items: int = 5) -> list[dict]:
    """
    Fetch Reuters world news RSS and return up to *max_items* headlines
    that match Iran/Middle-East keywords published within the last 24 hours.

    Each dict has keys: title, pubdate, source.
    """
    ua = "Mozilla/5.0 (compatible; iran-risk-bot/1.0)"
    try:
        response = requests.get(
            REUTERS_RSS_URL,
            headers={"User-Agent": ua},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Failed to fetch Reuters RSS: %s", exc)
        return []

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as exc:
        logger.error("Failed to parse Reuters RSS XML: %s", exc)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    matching = []

    for item in root.findall(".//item"):
        title_el = item.find("title")
        pubdate_el = item.find("pubDate")
        if title_el is None or not title_el.text:
            continue
        title = title_el.text.strip()
        title_lower = title.lower()

        # Keyword filter
        if not any(kw in title_lower for kw in IRAN_KEYWORDS):
            continue

        # Date filter — only last 24h
        pub_dt: Optional[datetime] = None
        if pubdate_el is not None and pubdate_el.text:
            try:
                pub_dt = parsedate_to_datetime(pubdate_el.text.strip())
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            except Exception:  # noqa: BLE001
                pub_dt = None

        if pub_dt is not None and pub_dt < cutoff:
            continue  # too old

        matching.append(
            {
                "title": title,
                "pubdate": pub_dt.isoformat() if pub_dt else "",
                "source": "Reuters",
            }
        )

        if len(matching) >= max_items:
            break

    logger.info("Found %d matching Reuters headline(s).", len(matching))
    return matching


# ---------------------------------------------------------------------------
# Risk score
# ---------------------------------------------------------------------------


def compute_risk_score(
    top_probability: Optional[float],
    headlines: list[dict],
) -> tuple[int, list[str]]:
    """
    Compute a composite risk score (0–100) and return (score, rationale_list).

    Scoring rules:
        Base: 20
        +30 if top Polymarket probability > 30%
        +20 if 3+ Iran headlines today
        +10 if escalation keywords found in headlines
        +20 if top Polymarket probability > 60%
    """
    score = RISK_BASE
    rationale: list[str] = [f"Base tension: +{RISK_BASE}"]

    if top_probability is not None and top_probability > 30:
        score += RISK_POLYMARKET_MODERATE
        rationale.append(
            f"Polymarket war probability {top_probability:.1f}% > 30%: +{RISK_POLYMARKET_MODERATE}"
        )

    if len(headlines) >= 3:
        score += RISK_NEWS_VOLUME
        rationale.append(f"{len(headlines)} major news items today: +{RISK_NEWS_VOLUME}")

    all_titles = " ".join(h["title"].lower() for h in headlines)
    if any(kw in all_titles for kw in ESCALATION_KEYWORDS):
        score += RISK_ESCALATION_KEYWORDS
        found_kws = [kw for kw in ESCALATION_KEYWORDS if kw in all_titles]
        rationale.append(
            f"Escalation keywords found ({', '.join(found_kws[:3])}): +{RISK_ESCALATION_KEYWORDS}"
        )

    if top_probability is not None and top_probability > 60:
        score += RISK_POLYMARKET_HIGH
        rationale.append(
            f"Polymarket war probability {top_probability:.1f}% > 60%: +{RISK_POLYMARKET_HIGH}"
        )

    score = min(score, 100)
    logger.info("Risk score: %d (%s). Rationale: %s", score, _risk_level(score), "; ".join(rationale))
    return score, rationale


# ---------------------------------------------------------------------------
# Brief formatter
# ---------------------------------------------------------------------------


def _one_sentence_assessment(
    score: int,
    level: str,
    top_probability: Optional[float],
    headlines: list[dict],
) -> str:
    """Generate a concise one-sentence assessment based on available data."""
    pm_part = (
        f"Polymarket assigns a {top_probability:.1f}% probability to an Iran conflict"
        if top_probability is not None
        else "Polymarket data unavailable"
    )
    hl_part = (
        f"{len(headlines)} Iran-related headline(s) in the last 24 hours"
        if headlines
        else "no major headlines detected"
    )
    return (
        f"Geopolitical risk is assessed as *{level}* (score {score}/100): "
        f"{pm_part}, with {hl_part}."
    )


def build_brief(
    report_date: str,
    markets: list[dict],
    headlines: list[dict],
    score: int,
    rationale: list[str],
) -> str:
    """Assemble the full Markdown brief for Telegram."""

    level = _risk_level(score)
    top_prob = _top_polymarket_probability(markets)

    # Header
    lines = [
        f"🌍 *Iran Geopolitical Risk Brief — {report_date}*",
        "",
        f"⚠️ Risk Score: {score}/100 — {level}",
        "",
    ]

    # Polymarket section
    if markets:
        lines.append("📊 *Polymarket Odds*")
        for m in markets[:5]:  # limit to 5 for readability
            prob = m.get("probability")
            prob_str = f"{prob:.1f}%" if prob is not None else "N/A"
            # Escape Markdown special chars in market question
            safe_q = m["question"].replace("*", "\\*").replace("_", "\\_").replace("`", "\\`")
            lines.append(f"- {safe_q}: {prob_str}")
        lines.append("")
    else:
        lines += ["📊 *Polymarket Odds*", "_No Iran markets found._", ""]

    # Headlines section
    if headlines:
        lines.append("📰 *Key Headlines*")
        for h in headlines:
            safe_title = h["title"].replace("*", "\\*").replace("_", "\\_").replace("`", "\\`")
            lines.append(f"- {safe_title} ({h['source']})")
        lines.append("")
    else:
        lines += ["📰 *Key Headlines*", "_No matching headlines in the last 24h._", ""]

    # Assessment
    assessment = _one_sentence_assessment(score, level, top_prob, headlines)
    lines += [f"📋 *Assessment*: {assessment}", ""]

    # Score rationale (compact)
    if rationale:
        lines.append("_Score breakdown: " + " | ".join(rationale) + "_")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    today = date.today().isoformat()
    logger.info("Starting iran_war_risk for %s", today)

    errors: list[str] = []

    try:
        # 1. Polymarket
        markets = fetch_polymarket_iran_markets(limit=10)
        if not markets:
            errors.append("No Polymarket data fetched for Iran markets.")

        # 2. Reuters headlines
        headlines = fetch_reuters_iran_headlines(max_items=5)
        if not headlines:
            errors.append("No matching Reuters headlines found.")

        # 3. Risk score
        top_prob = _top_polymarket_probability(markets)
        score, rationale = compute_risk_score(top_prob, headlines)
        level = _risk_level(score)

        # 4. Build brief
        brief = build_brief(
            report_date=today,
            markets=markets,
            headlines=headlines,
            score=score,
            rationale=rationale,
        )
        logger.info("Brief:\n%s", brief)

        # 5. Send via Telegram
        send_telegram(brief)

        # 6. Save to reports table
        save_to_supabase(
            "reports",
            {
                "date": today,
                "module": MODULE_NAME,
                "content": brief,
            },
        )

        # 7. Update module status
        status = "error" if (errors and not markets and not headlines) else "success"
        status_msg = (
            "; ".join(errors)
            if status == "error"
            else (
                f"Risk score: {score}/100 ({level}). "
                f"Markets: {len(markets)}, headlines: {len(headlines)}."
                + (f" Warnings: {'; '.join(errors)}" if errors else "")
            )
        )
        update_module_status(MODULE_NAME, status, status_msg)

        if errors:
            logger.warning("iran_war_risk completed with warnings: %s", "; ".join(errors))
        else:
            logger.info("iran_war_risk completed successfully.")

    except Exception as exc:  # noqa: BLE001
        logger.error("Unhandled error in iran_war_risk: %s", exc, exc_info=True)
        update_module_status(MODULE_NAME, "error", str(exc))
        raise


if __name__ == "__main__":
    main()
