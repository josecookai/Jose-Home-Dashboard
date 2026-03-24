#!/usr/bin/env python3
"""
Nancy Pelosi Trading Activity Checker
Fetches and monitors Pelosi's trading disclosures from multiple sources.
"""

import os
import sys
import json
import re
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

import requests
from bs4 import BeautifulSoup

# State file path
STATE_FILE = os.path.expanduser("~/.openclaw/workspace/pelosi_last_check.json")

# URLs to scrape
SOURCES = {
    'capitoltrades': 'https://www.capitoltrades.com/politicians/P000197',
    'quiverquant': 'https://www.quiverquant.com/congresstrading/politician/Nancy%20Pelosi-P000197',
    'telegaon': 'https://telegaon.com/nancy-pelosi-portfolio-tracker/'
}

@dataclass
class Trade:
    """Represents a single trade transaction."""
    ticker: str
    action: str  # BUY or SELL
    amount_range: str
    trade_date: str
    filing_date: str
    source: str
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Trade':
        return cls(**data)


class PelosiChecker:
    """Checks for new Pelosi trading activity."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        self.state = self._load_state()
        
    def _load_state(self) -> Dict:
        """Load previous check state from file."""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"⚠️  Warning: Could not load state file: {e}")
        return {
            'last_check': None,
            'last_filing_date': None,
            'last_trade_date': None,
            'known_trades': []
        }
    
    def _save_state(self):
        """Save current check state to file."""
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        self.state['last_check'] = datetime.now().isoformat()
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(self.state, f, indent=2)
        except IOError as e:
            print(f"⚠️  Warning: Could not save state file: {e}")
    
    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse various date formats to ISO format (YYYY-MM-DD)."""
        if not date_str:
            return None
        
        date_str = date_str.strip()
        
        # Direct ISO format
        iso_match = re.match(r'(\d{4})-(\d{2})-(\d{2})', date_str)
        if iso_match:
            return date_str[:10]
        
        # Format: "26 Jan2026" or "26 Jan 2026"
        month_map = {
            'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
            'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
            'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
        }
        
        # Pattern: day Month year (e.g., "26 Jan 2026" or "26Jan2026")
        pattern1 = re.match(r'(\d{1,2})\s*([a-zA-Z]{3,})\s*(\d{4})', date_str)
        if pattern1:
            day, month_str, year = pattern1.groups()
            month = month_map.get(month_str.lower()[:3])
            if month:
                return f"{year}-{month}-{day.zfill(2)}"
        
        # Format: MM/DD/YYYY or M/D/YYYY
        pattern2 = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', date_str)
        if pattern2:
            month, day, year = pattern2.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        
        return None
    
    def _normalize_action(self, action: str) -> str:
        """Normalize action to BUY or SELL."""
        if not action:
            return "UNKNOWN"
        action = action.upper().strip()
        if 'BUY' in action or 'PURCHASE' in action:
            return 'BUY'
        elif 'SELL' in action:
            return 'SELL'
        return action
    
    def fetch_capitoltrades(self) -> List[Trade]:
        """Fetch trades from CapitolTrades."""
        trades = []
        try:
            print(f"📡 Fetching from CapitolTrades...")
            response = self.session.get(SOURCES['capitoltrades'], timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # CapitolTrades uses a single table with all trades
            table = soup.find('table')
            if table:
                rows = table.find_all('tr')
                for row in rows[1:]:  # Skip header
                    cells = row.find_all('td')
                    if len(cells) >= 6:
                        text = row.get_text(separator=' ', strip=True)
                        
                        # Extract ticker (e.g., "AB:US", "GOOGL:US")
                        ticker_match = re.search(r'([A-Z]+):US', text)
                        ticker = ticker_match.group(1) if ticker_match else "Unknown"
                        
                        # Extract company name (text before ticker)
                        company_match = re.search(r'([A-Za-z\s\.]+?)(?:[A-Z]+:US)', text)
                        
                        # Extract dates - look for patterns like "26 Jan2026"
                        date_pattern = r'(\d{1,2})\s*([A-Za-z]{3,})\s*(\d{4})'
                        dates = re.findall(date_pattern, text)
                        
                        published_date = None
                        traded_date = None
                        if len(dates) >= 2:
                            # First date is usually published, second is traded
                            d1, m1, y1 = dates[0]
                            d2, m2, y2 = dates[1]
                            published_date = self._parse_date(f"{d1} {m1} {y1}")
                            traded_date = self._parse_date(f"{d2} {m2} {y2}")
                        
                        # Extract action (buy/sell)
                        action = 'BUY' if 'buy' in text.lower() else ('SELL' if 'sell' in text.lower() else 'UNKNOWN')
                        
                        # Extract amount range (e.g., "1M–5M", "500K–1M")
                        amount_match = re.search(r'(\d+[KM])\s*[-–]\s*(\d+[KM])', text)
                        amount = f"${amount_match.group(1)}-${amount_match.group(2)}" if amount_match else "Unknown"
                        
                        if ticker != "Unknown":
                            trades.append(Trade(
                                ticker=ticker,
                                action=action,
                                amount_range=amount,
                                trade_date=traded_date or "Unknown",
                                filing_date=published_date or "Unknown",
                                source='capitoltrades'
                            ))
            
            print(f"   ✓ Found {len(trades)} trades from CapitolTrades")
            
        except requests.RequestException as e:
            print(f"   ✗ Error fetching CapitolTrades: {e}")
        except Exception as e:
            print(f"   ✗ Error parsing CapitolTrades: {e}")
        
        return trades
    
    def fetch_quiverquant(self) -> List[Trade]:
        """Fetch trades from QuiverQuant."""
        trades = []
        try:
            print(f"📡 Fetching from QuiverQuant...")
            response = self.session.get(SOURCES['quiverquant'], timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # QuiverQuant uses tables with trade data
            tables = soup.find_all('table')
            
            for table in tables:
                rows = table.find_all('tr')
                for row in rows[1:]:  # Skip header
                    cells = row.find_all('td')
                    if len(cells) >= 4:
                        text = row.get_text(separator=' ', strip=True).lower()
                        
                        # Look for ticker symbols (all caps, 1-5 chars)
                        ticker_match = None
                        for cell in cells:
                            cell_text = cell.get_text(strip=True)
                            if re.match(r'^[A-Z]{1,5}$', cell_text):
                                ticker_match = cell_text
                                break
                        
                        if not ticker_match:
                            continue
                        
                        # Determine action
                        action = 'BUY' if any(x in text for x in ['buy', 'purchase']) else ('SELL' if 'sell' in text else 'UNKNOWN')
                        
                        # Extract amount
                        amount_match = re.search(r'\$?([\d,.]+[kmb]?)\s*[-–]\s*\$?([\d,.]+[kmb]?)', text, re.I)
                        amount = f"${amount_match.group(1).upper()}-${amount_match.group(2).upper()}" if amount_match else "Unknown"
                        
                        # Extract dates
                        date_matches = re.findall(r'(\d{4}-\d{2}-\d{2})', text)
                        trade_date = date_matches[0] if date_matches else "Unknown"
                        filing_date = date_matches[1] if len(date_matches) > 1 else trade_date
                        
                        trades.append(Trade(
                            ticker=ticker_match,
                            action=action,
                            amount_range=amount,
                            trade_date=trade_date,
                            filing_date=filing_date,
                            source='quiverquant'
                        ))
            
            print(f"   ✓ Found {len(trades)} trades from QuiverQuant")
            
        except requests.RequestException as e:
            print(f"   ✗ Error fetching QuiverQuant: {e}")
        except Exception as e:
            print(f"   ✗ Error parsing QuiverQuant: {e}")
        
        return trades
    
    def fetch_telegaon(self) -> List[Trade]:
        """Fetch trades from Telegaon."""
        trades = []
        try:
            print(f"📡 Fetching from Telegaon...")
            response = self.session.get(SOURCES['telegaon'], timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Telegaon uses tables
            tables = soup.find_all('table')
            
            for table in tables:
                rows = table.find_all('tr')
                for row in rows[1:]:  # Skip header
                    cells = row.find_all('td')
                    if len(cells) >= 3:
                        text = row.get_text(separator=' ', strip=True)
                        
                        # Try to find ticker
                        ticker = None
                        for cell in cells[:2]:  # Usually in first or second cell
                            cell_text = cell.get_text(strip=True)
                            if re.match(r'^[A-Z]{1,5}$', cell_text):
                                ticker = cell_text
                                break
                        
                        if not ticker:
                            continue
                        
                        # Determine action
                        action = 'BUY' if 'buy' in text.lower() else ('SELL' if 'sell' in text.lower() else 'UNKNOWN')
                        
                        # Extract amount
                        amount_match = re.search(r'\$?([\d,.]+\s*[kmb]?)\s*[-–]?\s*\$?([\d,.]*\s*[kmb]?)', text, re.I)
                        if amount_match:
                            if amount_match.group(2):
                                amount = f"${amount_match.group(1).strip().upper()}-${amount_match.group(2).strip().upper()}"
                            else:
                                amount = f"${amount_match.group(1).strip().upper()}"
                        else:
                            amount = "Unknown"
                        
                        # Extract dates
                        date_matches = re.findall(r'(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})', text)
                        trade_date = self._parse_date(date_matches[0]) if date_matches else "Unknown"
                        filing_date = self._parse_date(date_matches[1]) if len(date_matches) > 1 else trade_date
                        
                        trades.append(Trade(
                            ticker=ticker,
                            action=action,
                            amount_range=amount,
                            trade_date=trade_date,
                            filing_date=filing_date,
                            source='telegaon'
                        ))
            
            print(f"   ✓ Found {len(trades)} trades from Telegaon")
            
        except requests.RequestException as e:
            print(f"   ✗ Error fetching Telegaon: {e}")
        except Exception as e:
            print(f"   ✗ Error parsing Telegaon: {e}")
        
        return trades
    
    def fetch_all_trades(self) -> List[Trade]:
        """Fetch trades from all sources."""
        all_trades = []
        
        all_trades.extend(self.fetch_capitoltrades())
        all_trades.extend(self.fetch_quiverquant())
        all_trades.extend(self.fetch_telegaon())
        
        # Remove duplicates based on ticker + action + trade_date
        seen = set()
        unique_trades = []
        for trade in all_trades:
            key = (trade.ticker, trade.action, trade.trade_date)
            if key not in seen and trade.ticker != "Unknown":
                seen.add(key)
                unique_trades.append(trade)
        
        # Sort by filing date (newest first)
        unique_trades.sort(
            key=lambda x: x.filing_date if x.filing_date != "Unknown" else "0000-00-00", 
            reverse=True
        )
        
        return unique_trades
    
    def check_for_new_activity(self, trades: List[Trade]) -> List[Trade]:
        """Check if there are new trades since last check."""
        if not trades:
            return []
        
        last_filing = self.state.get('last_filing_date')
        known_trades = set(tuple(t) for t in self.state.get('known_trades', []))
        
        new_trades = []
        
        for trade in trades:
            # Create a unique identifier for the trade
            trade_id = (trade.ticker, trade.action, trade.trade_date, trade.filing_date)
            
            # Check if this is a new trade
            is_new = False
            
            if trade_id not in known_trades:
                # Compare filing dates
                if last_filing and trade.filing_date != "Unknown":
                    try:
                        if trade.filing_date > last_filing:
                            is_new = True
                    except TypeError:
                        is_new = True
                else:
                    # No previous filing date, treat all as new (first run)
                    is_new = True
            
            if is_new:
                new_trades.append(trade)
        
        return new_trades
    
    def update_state(self, trades: List[Trade]):
        """Update state with latest trades."""
        if trades:
            # Get the newest filing date
            filing_dates = [t.filing_date for t in trades if t.filing_date != "Unknown"]
            trade_dates = [t.trade_date for t in trades if t.trade_date != "Unknown"]
            
            if filing_dates:
                self.state['last_filing_date'] = max(filing_dates)
            if trade_dates:
                self.state['last_trade_date'] = max(trade_dates)
            
            # Store known trades
            self.state['known_trades'] = [
                [t.ticker, t.action, t.trade_date, t.filing_date] for t in trades[:50]  # Keep last 50
            ]
        
        self._save_state()
    
    def print_alert(self, trades: List[Trade]):
        """Print alert for new trading activity."""
        today = datetime.now().strftime('%Y-%m-%d')
        last_filing = self.state.get('last_filing_date', 'Unknown')
        
        print(f"""
📊 Pelosi Trading Update - {today}
""")
        
        for trade in trades[:5]:  # Show top 5 new trades
            print(f"""🔥 NEW ACTIVITY DETECTED:
• Stock: {trade.ticker}
• Action: {trade.action}
• Amount: {trade.amount_range}
• Date: {trade.trade_date}
""")
        
        if len(trades) > 5:
            print(f"... and {len(trades) - 5} more trades")
        
        print(f"Last Filing: {last_filing}")
    
    def run(self) -> int:
        """Main execution. Returns exit code."""
        print(f"🔍 Checking Nancy Pelosi trading activity...")
        print(f"   State file: {STATE_FILE}")
        print(f"   Last check: {self.state.get('last_check', 'Never')}")
        print(f"   Last filing: {self.state.get('last_filing_date', 'Unknown')}")
        print()
        
        try:
            # Fetch all trades
            trades = self.fetch_all_trades()
            
            if not trades:
                print("⚠️  No trades found from any source")
                self._save_state()  # Still update check time
                return 0
            
            print(f"\n📈 Total unique trades found: {len(trades)}")
            
            # Show sample trades
            print("\n📋 Recent trades:")
            for trade in trades[:3]:
                print(f"   {trade.ticker}: {trade.action} {trade.amount_range} (Filed: {trade.filing_date})")
            
            # Check for new activity
            new_trades = self.check_for_new_activity(trades)
            
            # Update state with all trades
            self.update_state(trades)
            
            if new_trades:
                print(f"\n🚨 {len(new_trades)} NEW trade(s) detected!")
                self.print_alert(new_trades)
            else:
                print(f"\n✅ No new activity since last check")
            
            return 0
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return 1


def main():
    """Entry point."""
    checker = PelosiChecker()
    sys.exit(checker.run())


if __name__ == '__main__':
    main()
