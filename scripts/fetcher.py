"""Shared web scraping and API fetching utilities."""
import time, random, logging
from typing import Optional
import requests, feedparser
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
]

def get_headers(extra: dict = None) -> dict:
    """Return headers with random user agent."""
    h = {"User-Agent": random.choice(USER_AGENTS), "Accept-Language": "en-US,en;q=0.9"}
    if extra:
        h.update(extra)
    return h

def fetch_url(url: str, timeout: int = 15, retries: int = 2, **kwargs) -> Optional[requests.Response]:
    """GET with retry and user-agent rotation."""
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=get_headers(), timeout=timeout, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            if attempt < retries:
                time.sleep(2 ** attempt)
            else:
                logger.warning(f"fetch_url failed for {url}: {e}")
                return None

def fetch_json(url: str, headers: dict = None, timeout: int = 15) -> Optional[dict | list]:
    """Fetch JSON from URL."""
    try:
        resp = requests.get(url, headers={**get_headers(), **(headers or {})}, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning(f"fetch_json failed for {url}: {e}")
        return None

def fetch_rss(url: str) -> list[dict]:
    """Parse RSS/Atom feed, return list of entry dicts."""
    try:
        feed = feedparser.parse(url)
        return feed.entries
    except Exception as e:
        logger.warning(f"fetch_rss failed for {url}: {e}")
        return []

def parse_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")

def rate_limit(min_s: float = 1.0, max_s: float = 3.0):
    """Sleep random interval between requests."""
    time.sleep(random.uniform(min_s, max_s))
