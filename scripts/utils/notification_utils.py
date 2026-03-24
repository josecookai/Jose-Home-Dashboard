#!/usr/bin/env python3
"""
Notification Utilities for Jose Home Dashboard

Shared module for sending notifications via Telegram and Email.
Provides standardized formatting, error handling, and retry logic.

Environment Variables:
    TELEGRAM_BOT_TOKEN: Bot token for Telegram Bot API
    TELEGRAM_CHAT_ID: Default chat ID for Telegram messages
    EMAIL_TO: Default recipient email address
    EMAIL_FROM: Sender email address (for himalaya)

Example:
    from scripts.utils.notification_utils import send_telegram, send_email, format_report
    
    # Send simple message
    send_telegram("Hello from dashboard!")
    
    # Send formatted report
    report = format_report("Daily Update", {"Status": "✅ All good", "Tasks": "3 completed"})
    send_telegram(report)
    send_email("Daily Update", report)
"""

import os
import sys
import json
import time
import logging
import subprocess
from typing import Optional, Dict, Any
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Configuration from environment variables
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
EMAIL_TO = os.getenv('EMAIL_TO', 'canalai2025@gmail.com')
EMAIL_FROM = os.getenv('EMAIL_FROM')

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds between retries


def send_telegram(message: str, chat_id: str = None) -> bool:
    """
    Send a message via Telegram Bot API.
    
    Supports Markdown formatting. Automatically retries on failure.
    
    Args:
        message: The message text to send (supports Markdown)
        chat_id: Target chat ID (defaults to TELEGRAM_CHAT_ID env var)
        
    Returns:
        bool: True if message was sent successfully, False otherwise
        
    Example:
        >>> send_telegram("Hello *World*!")  # Sends bold "World"
        True
    """
    bot_token = TELEGRAM_BOT_TOKEN
    target_chat_id = chat_id or TELEGRAM_CHAT_ID
    
    # Validate configuration
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not set")
        return False
    
    if not target_chat_id:
        logger.error("No chat_id provided and TELEGRAM_CHAT_ID not set")
        return False
    
    # Telegram API endpoint
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    # Prepare payload
    payload = {
        'chat_id': target_chat_id,
        'text': message,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': False
    }
    
    logger.info(f"Sending Telegram message to chat {target_chat_id}")
    
    # Try to import requests, fallback to urllib if not available
    try:
        import requests
        
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.post(url, json=payload, timeout=30)
                response_data = response.json()
                
                if response.ok and response_data.get('ok'):
                    logger.info("Telegram message sent successfully")
                    return True
                else:
                    error_msg = response_data.get('description', 'Unknown error')
                    logger.warning(f"Telegram API error: {error_msg}")
                    
                    if attempt < MAX_RETRIES:
                        logger.info(f"Retrying in {RETRY_DELAY} seconds... (attempt {attempt}/{MAX_RETRIES})")
                        time.sleep(RETRY_DELAY)
                    else:
                        logger.error(f"Failed to send Telegram message after {MAX_RETRIES} attempts")
                        return False
                        
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                else:
                    logger.error(f"Failed to send Telegram message: {e}")
                    return False
                    
    except ImportError:
        # Fallback to urllib
        logger.debug("requests not available, using urllib")
        import urllib.request
        import urllib.error
        
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                data = json.dumps(payload).encode('utf-8')
                headers = {'Content-Type': 'application/json'}
                req = urllib.request.Request(url, data=data, headers=headers, method='POST')
                
                with urllib.request.urlopen(req, timeout=30) as response:
                    response_data = json.loads(response.read().decode('utf-8'))
                    
                    if response_data.get('ok'):
                        logger.info("Telegram message sent successfully")
                        return True
                    else:
                        error_msg = response_data.get('description', 'Unknown error')
                        logger.error(f"Telegram API error: {error_msg}")
                        return False
                        
            except urllib.error.HTTPError as e:
                logger.warning(f"HTTP error (attempt {attempt}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                else:
                    logger.error(f"Failed to send Telegram message: {e}")
                    return False
                    
            except Exception as e:
                logger.warning(f"Error (attempt {attempt}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                else:
                    logger.error(f"Failed to send Telegram message: {e}")
                    return False
    
    return False


def send_email(subject: str, body: str, to: str = None) -> bool:
    """
    Send an email using the Himalaya CLI.
    
    Uses subprocess to run 'himalaya template send' with the email content.
    Automatically retries on failure.
    
    Args:
        subject: Email subject line
        body: Email body content (plain text or markdown)
        to: Recipient email address (defaults to EMAIL_TO env var)
        
    Returns:
        bool: True if email was sent successfully, False otherwise
        
    Example:
        >>> send_email("Daily Report", "Today's update: All systems operational")
        True
        
    Note:
        Requires Himalaya CLI to be installed and configured.
        Run 'himalaya account configure' to set up email account.
    """
    recipient = to or EMAIL_TO
    
    if not recipient:
        logger.error("No recipient provided and EMAIL_TO not set")
        return False
    
    # Get sender from environment or use default
    sender = EMAIL_FROM or os.getenv('EMAIL', 'dashboard@josehome.local')
    
    # Prepare email template in MML format
    # Format: headers followed by blank line, then body
    email_template = f"""From: {sender}
To: {recipient}
Subject: {subject}

{body}
"""
    
    logger.info(f"Sending email to {recipient} with subject: {subject}")
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # Use himalaya template send via stdin
            process = subprocess.run(
                ['himalaya', 'template', 'send'],
                input=email_template,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if process.returncode == 0:
                logger.info("Email sent successfully via Himalaya")
                return True
            else:
                error_msg = process.stderr.strip() or "Unknown error"
                logger.warning(f"Himalaya error (attempt {attempt}/{MAX_RETRIES}): {error_msg}")
                
                if attempt < MAX_RETRIES:
                    logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                    time.sleep(RETRY_DELAY)
                else:
                    logger.error(f"Failed to send email after {MAX_RETRIES} attempts")
                    return False
                    
        except subprocess.TimeoutExpired:
            logger.warning(f"Himalaya command timed out (attempt {attempt}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                logger.error("Failed to send email: Himalaya command timed out")
                return False
                
        except FileNotFoundError:
            logger.error("Himalaya CLI not found. Please install: https://github.com/pimalaya/himalaya")
            return False
            
        except Exception as e:
            logger.warning(f"Error sending email (attempt {attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                logger.error(f"Failed to send email: {e}")
                return False
    
    return False


def format_report(title: str, sections: Dict[str, Any]) -> str:
    """
    Format a structured report with emojis and sections.
    
    Creates a nicely formatted report suitable for Telegram (Markdown)
    or email. Adds emojis to section headers and organizes content.
    
    Args:
        title: Report title (will be bold and centered with emoji)
        sections: Dictionary of section name -> content
                 Content can be string, list, or dict
        
    Returns:
        str: Formatted report text
        
    Example:
        >>> sections = {
        ...     "Summary": "All systems operational",
        ...     "Tasks": ["Task 1: Done", "Task 2: In progress"],
        ...     "Metrics": {"CPU": "45%", "Memory": "2.1GB"}
        ... }
        >>> print(format_report("Daily Report", sections))
        📊 **Daily Report**
        
        📋 Summary
        All systems operational
        ...
    """
    # Emoji mapping for common section names
    emoji_map = {
        'summary': '📋',
        'status': '✅',
        'error': '❌',
        'warning': '⚠️',
        'info': 'ℹ️',
        'tasks': '📌',
        'todo': '✓',
        'metrics': '📈',
        'stats': '📊',
        'data': '💾',
        'price': '💰',
        'market': '📉',
        'alert': '🚨',
        'notification': '🔔',
        'report': '📄',
        'result': '🏆',
        'note': '📝',
        'link': '🔗',
        'time': '⏰',
        'date': '📅',
    }
    
    # Build report
    lines = []
    
    # Title with emoji
    title_emoji = '📊'
    lines.append(f"{title_emoji} **{title}**")
    lines.append(f"_{datetime.now().strftime('%Y-%m-%d %H:%M')}_")
    lines.append("")
    
    # Process each section
    for section_name, content in sections.items():
        # Determine emoji for section
        section_lower = section_name.lower()
        emoji = emoji_map.get(section_lower, '▪️')
        for key, icon in emoji_map.items():
            if key in section_lower:
                emoji = icon
                break
        
        # Add section header
        lines.append(f"{emoji} **{section_name}**")
        
        # Format content based on type
        if isinstance(content, dict):
            for key, value in content.items():
                lines.append(f"• {key}: {value}")
        elif isinstance(content, (list, tuple)):
            for item in content:
                lines.append(f"• {item}")
        else:
            lines.append(str(content))
        
        lines.append("")
    
    # Footer
    lines.append("—")
    lines.append("Generated by Jose Home Dashboard")
    
    return "\n".join(lines)


def send_notification(
    message: str,
    subject: str = "Dashboard Notification",
    telegram: bool = True,
    email: bool = True,
    chat_id: str = None,
    email_to: str = None
) -> Dict[str, bool]:
    """
    Send notification through multiple channels.
    
    Convenience function to send the same message via both Telegram
    and email in one call.
    
    Args:
        message: Message content
        subject: Email subject (also used as Telegram message title if formatted)
        telegram: Whether to send via Telegram
        email: Whether to send via email
        chat_id: Override Telegram chat ID
        email_to: Override email recipient
        
    Returns:
        Dict with 'telegram' and 'email' keys indicating success/failure
        
    Example:
        >>> results = send_notification("System alert!", "Alert")
        >>> print(results)
        {'telegram': True, 'email': True}
    """
    results = {'telegram': False, 'email': False}
    
    if telegram:
        # Format with subject for Telegram if not already formatted
        if not message.startswith('**'):
            telegram_msg = f"🔔 **{subject}**\n\n{message}"
        else:
            telegram_msg = message
        results['telegram'] = send_telegram(telegram_msg, chat_id=chat_id)
    
    if email:
        results['email'] = send_email(subject, message, to=email_to)
    
    return results


# Backwards compatibility with existing code
class NotificationUtils:
    """
    Backwards-compatible class wrapper for notification utilities.
    
    Provides an object-oriented interface matching older code patterns.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.warning("NotificationUtils class is deprecated. Use module functions directly.")
    
    def send_telegram(self, message: str, chat_id: str = None) -> bool:
        """Send Telegram message (deprecated, use function directly)."""
        return send_telegram(message, chat_id)
    
    def send_email(self, subject: str, body: str, to: str = None) -> bool:
        """Send email (deprecated, use function directly)."""
        return send_email(subject, body, to)
    
    def format_report(self, title: str, sections: Dict[str, Any]) -> str:
        """Format report (deprecated, use function directly)."""
        return format_report(title, sections)


if __name__ == '__main__':
    # Test the module when run directly
    print("Testing notification_utils module...")
    print()
    
    # Test format_report
    test_sections = {
        "Status": "✅ All systems operational",
        "Tasks": ["Task 1: Completed", "Task 2: In progress"],
        "Metrics": {"CPU": "45%", "Memory": "2.1GB"}
    }
    
    formatted = format_report("Test Report", test_sections)
    print("Formatted report:")
    print("-" * 40)
    print(formatted)
    print("-" * 40)
    print()
    
    # Check environment
    print(f"TELEGRAM_BOT_TOKEN set: {bool(TELEGRAM_BOT_TOKEN)}")
    print(f"TELEGRAM_CHAT_ID set: {bool(TELEGRAM_CHAT_ID)}")
    print(f"EMAIL_TO: {EMAIL_TO}")
    
    # Test Telegram (if configured)
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        print("\nTesting Telegram (dry run - would send in production)...")
        # Uncomment to actually send:
        # result = send_telegram("🧪 Test message from notification_utils")
        # print(f"Telegram result: {result}")
    else:
        print("\nSkipping Telegram test (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set)")
    
    # Test email check
    try:
        result = subprocess.run(['himalaya', '--version'], capture_output=True, text=True)
        print(f"\nHimalaya CLI available: {result.stdout.strip()}")
    except FileNotFoundError:
        print("\nHimalaya CLI not found (install from https://github.com/pimalaya/himalaya)")
