# Setup Guide - Jose Home Dashboard

## Prerequisites

- Python 3.8+
- Git
- Cron
- Linux/Unix environment

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/josecookai/Jose-Home-Dashboard.git
cd Jose-Home-Dashboard
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

Required packages:
```
requests
python-telegram-bot
feedparser
beautifulsoup4
pandas
python-dotenv
```

### 3. Configure Environment Variables

```bash
cp config/env.example .env
# Edit .env with your actual API keys
nano .env
```

### 4. Set Up Cron Jobs

```bash
# Install crontab
crontab crontab.txt

# Verify installation
crontab -l
```

### 5. Create Log Directories

```bash
mkdir -p /root/clawd/logs/{strava,financial,ai,geopolitical,email}
```

## Configuration

### Telegram Bot Setup

1. Create a bot with @BotFather on Telegram
2. Get your bot token
3. Add the bot to your channel/group
4. Get the chat ID (use @userinfobot)

### Email Setup (Himilaya)

1. Install Himilaya: `cargo install himilaya`
2. Configure `~/.config/himalaya/config.toml`
3. Test with: `himalaya envelope list`

### Strava API Setup

1. Create app at https://www.strava.com/settings/api
2. Get Client ID and Secret
3. Complete OAuth flow to get refresh token

## Testing

Run individual scripts manually:

```bash
python3 scripts/bitcoin_etf_report.py
python3 scripts/pelosi_tracker.py
python3 scripts/ai_intelligence.py
```

## Troubleshooting

### Cron jobs not running
- Check cron service: `service cron status`
- Check logs: `tail -f /var/log/syslog | grep CRON`
- Verify paths in crontab are absolute

### API rate limits
- Add delays between requests
- Use caching where possible
- Consider paid API tiers

### Memory/performance issues
- Monitor with `htop`
- Add swap space if needed
- Optimize data fetching

## Maintenance

### Weekly Tasks
- Review logs for errors
- Check API token expiry
- Update data sources if needed

### Monthly Tasks
- Analyze report accuracy
- Review and update thresholds
- Backup configuration

## Security Notes

- Never commit `.env` file
- Use app passwords for email (not main password)
- Rotate API keys regularly
- Restrict file permissions: `chmod 600 .env`

## Support

- Telegram: @t0x_992
- Email: chefjose@pumpbtc.xyz
