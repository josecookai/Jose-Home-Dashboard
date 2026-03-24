"""
Data Fetcher Module for Jose Home Dashboard

Provides utilities for fetching URLs with caching, parsing RSS feeds,
scraping HTML tables, and making retry-enabled HTTP requests.
"""

import os
import time
import json
import hashlib
import logging
import random
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
CACHE_DIR = Path("/tmp/jhd_cache")
RATE_LIMIT_DELAY = 1.0  # seconds between requests

# Rotating User-Agent headers to avoid being blocked
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
]

# Track last request time for rate limiting
_last_request_time: Optional[float] = None


def _get_headers() -> Dict[str, str]:
    """Get headers with a random User-Agent."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
    }


def _rate_limit():
    """Enforce rate limiting between requests."""
    global _last_request_time
    if _last_request_time is not None:
        elapsed = time.time() - _last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            sleep_time = RATE_LIMIT_DELAY - elapsed
            logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f}s")
            time.sleep(sleep_time)
    _last_request_time = time.time()


def _get_cache_path(url: str) -> Path:
    """Generate a cache file path for a URL."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    return CACHE_DIR / f"{url_hash}.cache"


def _is_cache_valid(cache_path: Path, cache_duration: int) -> bool:
    """Check if cache file exists and is within validity period."""
    if not cache_path.exists():
        return False
    
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        cached_time = datetime.fromisoformat(cache_data['timestamp'])
        expiry_time = cached_time + timedelta(seconds=cache_duration)
        
        return datetime.now() < expiry_time
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning(f"Cache file corrupted, removing: {cache_path}")
        cache_path.unlink(missing_ok=True)
        return False


def _read_cache(cache_path: Path) -> str:
    """Read content from cache file."""
    with open(cache_path, 'r', encoding='utf-8') as f:
        cache_data = json.load(f)
    logger.info(f"Cache hit: {cache_path.name}")
    return cache_data['content']


def _write_cache(cache_path: Path, content: str):
    """Write content to cache file."""
    cache_data = {
        'timestamp': datetime.now().isoformat(),
        'content': content
    }
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f)
    logger.info(f"Cache written: {cache_path.name}")


def fetch_url(url: str, cache_duration: int = 300) -> str:
    """
    Fetch URL content with file-based caching.
    
    Args:
        url: The URL to fetch
        cache_duration: Cache validity in seconds (default: 300s = 5 minutes)
    
    Returns:
        The response content as string
    
    Raises:
        requests.RequestException: If the request fails after all retries
    """
    cache_path = _get_cache_path(url)
    
    # Check cache first
    if _is_cache_valid(cache_path, cache_duration):
        return _read_cache(cache_path)
    
    # Fetch from network
    _rate_limit()
    logger.info(f"Fetching URL: {url}")
    
    try:
        response = fetch_with_retry(url)
        content = response.text
        
        # Save to cache
        _write_cache(cache_path, content)
        
        return content
    except requests.RequestException as e:
        logger.error(f"Failed to fetch {url}: {e}")
        raise


def fetch_with_retry(url: str, max_retries: int = 3) -> requests.Response:
    """
    Fetch URL with retry logic and exponential backoff.
    
    Args:
        url: The URL to fetch
        max_retries: Maximum number of retry attempts
    
    Returns:
        The response object
    
    Raises:
        requests.RequestException: If all retries fail
    """
    session = requests.Session()
    
    # Configure retry strategy
    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=1,  # 1s, 2s, 4s, etc.
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    headers = _get_headers()
    
    try:
        response = session.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        logger.info(f"Successfully fetched {url} (status: {response.status_code})")
        return response
    except requests.RequestException as e:
        logger.error(f"Request failed for {url} after {max_retries} retries: {e}")
        raise


def parse_rss(feed_url: str) -> List[Dict]:
    """
    Parse an RSS feed and return entries as a list of dictionaries.
    
    Args:
        feed_url: The URL of the RSS feed
    
    Returns:
        List of feed entries with standard fields (title, link, description, published, etc.)
    
    Raises:
        ImportError: If feedparser is not installed
        requests.RequestException: If fetching fails
    """
    try:
        import feedparser
    except ImportError:
        logger.error("feedparser not installed. Installing...")
        import subprocess
        subprocess.check_call(["pip", "install", "feedparser"])
        import feedparser
    
    _rate_limit()
    logger.info(f"Parsing RSS feed: {feed_url}")
    
    try:
        # feedparser can handle the fetching itself, but we'll use our fetch_url for caching
        content = fetch_url(feed_url, cache_duration=600)  # 10 min cache for RSS
        feed = feedparser.parse(content)
        
        entries = []
        for entry in feed.entries:
            entry_data = {
                'title': entry.get('title', ''),
                'link': entry.get('link', ''),
                'description': entry.get('description', ''),
                'published': entry.get('published', ''),
                'published_parsed': entry.get('published_parsed', ''),
                'author': entry.get('author', ''),
                'id': entry.get('id', ''),
            }
            entries.append(entry_data)
        
        logger.info(f"Parsed {len(entries)} entries from RSS feed")
        return entries
    except Exception as e:
        logger.error(f"Failed to parse RSS feed {feed_url}: {e}")
        raise


def scrape_table(html: str, selector: str) -> List[List]:
    """
    Scrape an HTML table using BeautifulSoup.
    
    Args:
        html: The HTML content to parse
        selector: CSS selector to find the table (e.g., '#my-table', '.data-table')
    
    Returns:
        List of rows, where each row is a list of cell values
    
    Raises:
        ImportError: If beautifulsoup4 is not installed
        ValueError: If table not found with given selector
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("beautifulsoup4 not installed. Installing...")
        import subprocess
        subprocess.check_call(["pip", "install", "beautifulsoup4"])
        from bs4 import BeautifulSoup
    
    logger.info(f"Scraping table with selector: {selector}")
    
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.select_one(selector)
    
    if not table:
        raise ValueError(f"No table found with selector: {selector}")
    
    rows = []
    for tr in table.find_all('tr'):
        row_data = []
        # Get both th (header) and td (data) cells
        cells = tr.find_all(['td', 'th'])
        for cell in cells:
            # Strip whitespace and get text content
            text = cell.get_text(strip=True)
            row_data.append(text)
        
        if row_data:  # Only add non-empty rows
            rows.append(row_data)
    
    logger.info(f"Scraped {len(rows)} rows from table")
    return rows


# Convenience function for fetching and scraping in one call
def fetch_and_scrape_table(url: str, selector: str, cache_duration: int = 300) -> List[List]:
    """
    Fetch a URL and scrape a table in one call.
    
    Args:
        url: The URL to fetch
        selector: CSS selector for the table
        cache_duration: Cache validity in seconds
    
    Returns:
        List of rows with cell values
    """
    html = fetch_url(url, cache_duration)
    return scrape_table(html, selector)


if __name__ == "__main__":
    # Simple test
    logging.basicConfig(level=logging.DEBUG)
    
    # Test fetch_url
    test_url = "https://httpbin.org/get"
    try:
        result = fetch_url(test_url, cache_duration=60)
        print(f"Fetched {len(result)} characters")
    except Exception as e:
        print(f"Test failed: {e}")
