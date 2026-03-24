"""Shared notification utilities for Telegram and Email."""
import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")


def send_telegram(
    message: str,
    parse_mode: str = "Markdown",
    chat_id: Optional[str] = None,
) -> bool:
    """Send message via Telegram bot. Returns True on success."""
    token = TELEGRAM_BOT_TOKEN
    cid = chat_id or TELEGRAM_CHAT_ID
    if not token or not cid:
        logger.info("Telegram not configured, skipping")
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": cid, "text": message, "parse_mode": parse_mode},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


def send_email(
    subject: str,
    body: str,
    html: bool = False,
    to: Optional[str] = None,
) -> bool:
    """Send email via SMTP. Returns True on success."""
    if not all([EMAIL_FROM, SMTP_USER, SMTP_PASSWORD]):
        logger.info("Email not configured, skipping")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = to or EMAIL_TO
        part = MIMEText(body, "html" if html else "plain", "utf-8")
        msg.attach(part)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(EMAIL_FROM, to or EMAIL_TO, msg.as_string())
        return True
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False


def notify(
    message: str,
    subject: str = "Dashboard Alert",
    telegram: bool = True,
    email: bool = False,
) -> None:
    """Send notification via configured channels."""
    if telegram:
        send_telegram(message)
    if email:
        send_email(subject, message)
