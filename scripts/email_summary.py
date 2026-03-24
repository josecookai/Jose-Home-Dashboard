#!/usr/bin/env python3
"""
email_summary.py — Daily Email Digest (Issue #9)

Aggregates today's reports from Supabase, compiles a single HTML email with
module status, Bitcoin ETF data, Strava activity, and per-module report
sections, then sends it via SMTP.

Scheduled usage (cron example — runs daily at 20:00 UTC):
    0 20 * * * /usr/bin/python3 /path/to/email_summary.py >> /var/log/email_summary.log 2>&1

Environment variables (via .env or shell):
    NEXT_PUBLIC_SUPABASE_URL   or  SUPABASE_URL
    SUPABASE_SERVICE_KEY       or  SUPABASE_SERVICE_ROLE_KEY
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID
    EMAIL_FROM
    EMAIL_TO
    SMTP_HOST
    SMTP_PORT
    SMTP_USER
    SMTP_PASSWORD
"""

import logging
import os
import smtplib
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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
logger = logging.getLogger("email_summary")

# ---------------------------------------------------------------------------
# Inline helpers
# ---------------------------------------------------------------------------

SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL") or os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

MODULE_NAME = "email_summary"
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
# Supabase data fetching
# ---------------------------------------------------------------------------


def _supabase_get(path: str, params: Optional[dict] = None) -> list:
    """
    Perform a GET against the Supabase REST API.

    Returns the parsed JSON list, or an empty list on failure.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("Supabase credentials not configured — skipping fetch.")
        return []
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    try:
        response = requests.get(
            url, headers=headers, params=params, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        data = response.json()
        logger.info("Fetched %d record(s) from '%s'.", len(data), path)
        return data if isinstance(data, list) else []
    except requests.RequestException as exc:
        logger.error("Failed to fetch from Supabase '%s': %s", path, exc)
        return []
    except ValueError as exc:
        logger.error("Failed to parse JSON from Supabase '%s': %s", path, exc)
        return []


def fetch_today_reports(today: str) -> list[dict]:
    """Return all rows from the reports table where date == today."""
    return _supabase_get("reports", {"date": f"eq.{today}", "select": "module,content"})


def fetch_module_statuses() -> list[dict]:
    """Return all rows from the module_status table."""
    return _supabase_get("module_status")


def fetch_bitcoin_etf_today(today: str) -> Optional[dict]:
    """Return the bitcoin_etf_daily row for today, or None."""
    rows = _supabase_get("bitcoin_etf_daily", {"date": f"eq.{today}"})
    return rows[0] if rows else None


def fetch_strava_today(today: str) -> list[dict]:
    """Return strava_activities rows for today."""
    # strava_activities stores start_date; filter by date prefix
    return _supabase_get(
        "strava_activities",
        {"select": "name,type,distance,moving_time,start_date", "start_date": f"gte.{today}"},
    )


# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------

_CSS = """
    body { font-family: Arial, sans-serif; font-size: 14px; color: #333; background: #f5f5f5; margin: 0; padding: 0; }
    .wrapper { max-width: 700px; margin: 24px auto; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,.12); }
    .header { background: #1a1a2e; color: #fff; padding: 24px 32px; }
    .header h1 { margin: 0; font-size: 22px; }
    .header .meta { margin-top: 6px; font-size: 13px; color: #aaa; }
    .section { padding: 20px 32px; border-bottom: 1px solid #eee; }
    .section h2 { font-size: 16px; margin: 0 0 12px; color: #1a1a2e; border-left: 4px solid #4a90d9; padding-left: 8px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th { text-align: left; background: #f0f4ff; padding: 7px 10px; border-bottom: 2px solid #dce4f7; }
    td { padding: 7px 10px; border-bottom: 1px solid #eee; vertical-align: top; }
    .badge-success { background: #d4edda; color: #155724; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
    .badge-error   { background: #f8d7da; color: #721c24; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
    .badge-unknown { background: #e2e3e5; color: #383d41; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
    .kv { display: flex; gap: 32px; flex-wrap: wrap; }
    .kv-item { flex: 1; min-width: 140px; background: #f7f9fc; border-radius: 6px; padding: 10px 14px; }
    .kv-item .label { font-size: 11px; color: #777; text-transform: uppercase; letter-spacing: .5px; }
    .kv-item .value { font-size: 20px; font-weight: bold; color: #1a1a2e; margin-top: 4px; }
    .report-block { background: #f9f9f9; border-radius: 6px; padding: 12px 16px; margin-bottom: 12px; white-space: pre-wrap; font-size: 13px; font-family: monospace; }
    .report-module { font-weight: bold; font-size: 13px; color: #4a90d9; margin-bottom: 6px; }
    .footer { padding: 16px 32px; text-align: center; font-size: 12px; color: #aaa; }
"""


def _badge(status: Optional[str]) -> str:
    if status == "success":
        return '<span class="badge-success">success</span>'
    if status == "error":
        return '<span class="badge-error">error</span>'
    return '<span class="badge-unknown">unknown</span>'


def _flow_str(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1f}M USD"


def _duration_str(seconds: Optional[int]) -> str:
    if seconds is None:
        return "N/A"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m"
    return f"{m}m {s}s"


def _km(meters: Optional[float]) -> str:
    if meters is None:
        return "N/A"
    return f"{meters / 1000:.2f} km"


def build_html_email(
    report_date: str,
    reports: list[dict],
    module_statuses: list[dict],
    btc_data: Optional[dict],
    strava_rows: list[dict],
) -> str:
    """Compile the full HTML email body."""

    total_modules = len(module_statuses)
    success_count = sum(1 for m in module_statuses if m.get("last_status") == "success")
    fail_count = sum(1 for m in module_statuses if m.get("last_status") == "error")

    # ---- Header ----
    header_html = f"""
    <div class="header">
        <h1>Jose Home Dashboard — Daily Digest</h1>
        <div class="meta">
            {report_date} &nbsp;|&nbsp; {total_modules} modules tracked &nbsp;|&nbsp;
            <span style="color:#7ddc8e">{success_count} succeeded</span> &nbsp;/&nbsp;
            <span style="color:#f78080">{fail_count} failed</span>
        </div>
    </div>
    """

    # ---- Module status table ----
    status_rows_html = ""
    for m in sorted(module_statuses, key=lambda x: x.get("module_name", "")):
        name = m.get("module_name", "—")
        last_run = m.get("last_run_at", "—")
        status = m.get("last_status")
        message = m.get("last_message", "")
        # Truncate long messages to keep table readable
        short_msg = (message[:120] + "…") if len(message) > 120 else message
        status_rows_html += f"""
        <tr>
            <td><strong>{name}</strong></td>
            <td>{_badge(status)}</td>
            <td style="color:#777;font-size:12px">{last_run}</td>
            <td style="font-size:12px">{short_msg}</td>
        </tr>
        """

    module_status_html = f"""
    <div class="section">
        <h2>Module Status</h2>
        <table>
            <thead>
                <tr>
                    <th>Module</th>
                    <th>Status</th>
                    <th>Last Run</th>
                    <th>Message</th>
                </tr>
            </thead>
            <tbody>
                {status_rows_html or "<tr><td colspan='4'>No module data available.</td></tr>"}
            </tbody>
        </table>
    </div>
    """

    # ---- Bitcoin ETF summary ----
    if btc_data:
        btc_price = btc_data.get("btc_price")
        price_str = f"${btc_price:,.2f}" if btc_price is not None else "N/A"
        ibit = _flow_str(btc_data.get("ibit_flow"))
        fbtc = _flow_str(btc_data.get("fbtc_flow"))
        gbtc = _flow_str(btc_data.get("gbtc_flow"))
        total = _flow_str(btc_data.get("total_flow"))
        btc_html = f"""
        <div class="section">
            <h2>Bitcoin ETF</h2>
            <div class="kv">
                <div class="kv-item"><div class="label">BTC Price</div><div class="value">{price_str}</div></div>
                <div class="kv-item"><div class="label">IBIT Flow</div><div class="value" style="font-size:16px">{ibit}</div></div>
                <div class="kv-item"><div class="label">FBTC Flow</div><div class="value" style="font-size:16px">{fbtc}</div></div>
                <div class="kv-item"><div class="label">GBTC Flow</div><div class="value" style="font-size:16px">{gbtc}</div></div>
                <div class="kv-item"><div class="label">Total Flow</div><div class="value" style="font-size:16px">{total}</div></div>
            </div>
        </div>
        """
    else:
        btc_html = """
        <div class="section">
            <h2>Bitcoin ETF</h2>
            <p style="color:#999">No Bitcoin ETF data available for today.</p>
        </div>
        """

    # ---- Strava ----
    if strava_rows:
        strava_rows_html = ""
        for act in strava_rows:
            strava_rows_html += f"""
            <tr>
                <td>{act.get('name', '—')}</td>
                <td>{act.get('type', '—')}</td>
                <td>{_km(act.get('distance'))}</td>
                <td>{_duration_str(act.get('moving_time'))}</td>
            </tr>
            """
        strava_html = f"""
        <div class="section">
            <h2>Strava Activity</h2>
            <table>
                <thead>
                    <tr><th>Name</th><th>Type</th><th>Distance</th><th>Duration</th></tr>
                </thead>
                <tbody>{strava_rows_html}</tbody>
            </table>
        </div>
        """
    else:
        strava_html = """
        <div class="section">
            <h2>Strava Activity</h2>
            <p style="color:#999">No Strava activities recorded today.</p>
        </div>
        """

    # ---- Reports content ----
    reports_inner = ""
    if reports:
        for rep in reports:
            module = rep.get("module", "unknown")
            content = rep.get("content", "")
            # Escape HTML entities in content before wrapping in pre block
            safe_content = (
                content.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            reports_inner += f"""
            <div>
                <div class="report-module">{module}</div>
                <div class="report-block">{safe_content}</div>
            </div>
            """
    else:
        reports_inner = "<p style='color:#999'>No reports found for today.</p>"

    reports_html = f"""
    <div class="section">
        <h2>Today's Reports</h2>
        {reports_inner}
    </div>
    """

    # ---- Assemble ----
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Jose Dashboard — Daily Digest {report_date}</title>
    <style>{_CSS}</style>
</head>
<body>
<div class="wrapper">
    {header_html}
    {module_status_html}
    {btc_html}
    {strava_html}
    {reports_html}
    <div class="footer">Generated by Jose Home Dashboard · {datetime.utcnow().strftime("%Y-%m-%d %H:%M")} UTC</div>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# SMTP sender
# ---------------------------------------------------------------------------


def send_html_email(subject: str, html_body: str) -> bool:
    """
    Send *html_body* as an HTML email via SMTP.

    Reads EMAIL_FROM, EMAIL_TO, SMTP_HOST, SMTP_PORT, SMTP_USER,
    SMTP_PASSWORD from the environment.

    Returns True on success, False otherwise.
    """
    email_from = os.getenv("EMAIL_FROM", "")
    email_to = os.getenv("EMAIL_TO", "")
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")

    if not all([email_from, email_to, smtp_host, smtp_user, smtp_password]):
        logger.warning(
            "SMTP not fully configured — set EMAIL_FROM, EMAIL_TO, SMTP_HOST, "
            "SMTP_PORT, SMTP_USER, SMTP_PASSWORD. Skipping send."
        )
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_from
    msg["To"] = email_to
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_password)
            server.sendmail(email_from, [email_to], msg.as_bytes())
        logger.info("HTML email sent to %s via %s:%d.", email_to, smtp_host, smtp_port)
        return True
    except smtplib.SMTPAuthenticationError as exc:
        logger.error("SMTP authentication failed: %s", exc)
    except smtplib.SMTPException as exc:
        logger.error("SMTP error while sending email: %s", exc)
    except OSError as exc:
        logger.error("Network error connecting to SMTP server: %s", exc)
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    today = date.today().isoformat()
    logger.info("Starting email_summary for %s", today)

    errors: list[str] = []

    try:
        # 1. Fetch today's reports
        reports = fetch_today_reports(today)
        logger.info("Found %d report(s) for today.", len(reports))
        if not reports:
            errors.append("No reports found in Supabase for today.")

        # 2. Fetch module statuses
        module_statuses = fetch_module_statuses()
        logger.info("Found %d module status record(s).", len(module_statuses))

        # 3. Fetch Bitcoin ETF data
        btc_data = fetch_bitcoin_etf_today(today)
        if btc_data is None:
            logger.info("No Bitcoin ETF data for today.")

        # 4. Fetch Strava activities
        strava_rows = fetch_strava_today(today)
        logger.info("Found %d Strava activity record(s) for today.", len(strava_rows))

        # 5. Build HTML email
        total_modules = len(module_statuses)
        success_count = sum(1 for m in module_statuses if m.get("last_status") == "success")

        html_body = build_html_email(
            report_date=today,
            reports=reports,
            module_statuses=module_statuses,
            btc_data=btc_data,
            strava_rows=strava_rows,
        )

        # 6. Send email
        subject = f"Jose Dashboard — Daily Digest {today}"
        email_to = os.getenv("EMAIL_TO", "")
        sent = send_html_email(subject, html_body)
        if not sent:
            errors.append("Failed to send SMTP email.")

        # 7. Telegram summary
        tg_msg = (
            f"📧 Daily digest sent — {total_modules} modules, "
            f"{success_count} succeeded"
        )
        send_telegram(tg_msg)

        # 8. Save to reports table
        save_to_supabase(
            "reports",
            {
                "date": today,
                "module": MODULE_NAME,
                "content": f"email sent to {email_to}" if sent else "email send failed",
            },
        )

        # 9. Update module status
        status = "error" if errors else "success"
        status_msg = (
            "; ".join(errors)
            if errors
            else f"Daily digest compiled and sent to {email_to}. "
            f"Modules: {total_modules}, success: {success_count}."
        )
        update_module_status(MODULE_NAME, status, status_msg)

        if errors:
            logger.warning("email_summary completed with warnings: %s", "; ".join(errors))
        else:
            logger.info("email_summary completed successfully.")

    except Exception as exc:  # noqa: BLE001
        logger.error("Unhandled error in email_summary: %s", exc, exc_info=True)
        update_module_status(MODULE_NAME, "error", str(exc))
        raise


if __name__ == "__main__":
    main()
