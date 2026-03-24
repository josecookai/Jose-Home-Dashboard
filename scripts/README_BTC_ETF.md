# Bitcoin ETF Report Script

Generates a daily Bitcoin ETF flow report combining data from multiple sources.

## Features

- 📊 Fetches Bitcoin ETF flow data from farside.co.uk
- 💰 Fetches BTC price from CoinGecko API
- 📈 Calculates daily net flows across all spot Bitcoin ETFs
- 🏛️ Generates institutional sentiment analysis
- 📝 Saves report to file and prints to stdout

## Installation

```bash
cd scripts
pip install -r requirements.txt
```

## Usage

```bash
# Generate report
python3 bitcoin_etf_report.py

# Save to file (also auto-saves to /tmp/)
python3 bitcoin_etf_report.py > report.txt 2>/dev/null
```

## Output Format

```
📊 Bitcoin ETF Daily Flow Report - 2026-03-24

💰 ETF FLOW DATA
• Recent Daily: BlackRock IBIT +$285.5M | Fidelity FBTC +$145.2M | ...
• March Total: ~+$X.XM net inflows
• Q1 Total: +$X.XB net inflows
• Total ETF AUM: $128B+

📈 BTC PRICE ACTION
• Current Price: ~$XX,XXX (+X.X% 24h)
• Support: $XX,XXX | Resistance: $XX,XXX

🏛️ INSTITUTIONAL SENTIMENT
• [Sentiment analysis based on flows and price action]
```

## Data Sources

1. **ETF Flows**: https://farside.co.uk/btc/
   - Requires browser-like headers to bypass Cloudflare
   - Falls back to sample data if scraping fails
   
2. **BTC Price**: CoinGecko API
   - Free public API
   - No API key required for basic usage

## Cloudflare Workaround

If farside.co.uk returns 403 errors, the script will automatically fall back to sample data. To get live data, you can:

1. **Use a residential proxy** (e.g., BrightData, Oxylabs)
2. **Run from a home connection** instead of datacenter
3. **Add delays** between requests to avoid rate limiting
4. **Use Selenium/Playwright** for browser automation (requires additional setup)

## Exit Codes

- `0`: Success (even with sample data)
- `1`: Error (failed to generate any report)

## Integration

This script is designed to be called by `notification_utils` for Telegram/Email delivery. It outputs to stdout for easy piping.
