# 🏠 Jose Home Dashboard

Personal automation dashboard for cron jobs, monitoring, and daily reports.

## 📊 Dashboard Overview

| Category | Jobs | Status |
|----------|------|--------|
| Financial | 5 | ✅ Active |
| Tech/AI | 4 | ✅ Active |
| Health/Fitness | 2 | ✅ Active |
| Geopolitical | 1 | ✅ Active |
| Email/Daily | 2 | ✅ Active |

---

## ⏰ Cron Jobs Schedule

### Financial Reports (08:00-11:00 GMT+8)

| Time | Job | Description | Output |
|------|-----|-------------|--------|
| 08:00 | Strava Daily Sync | Sync yesterday's workout data | Telegram + Log |
| 09:45 | AI Funding News | AI startup funding rounds ($10M+) | Telegram |
| 10:39 | Bitcoin ETF Report | ETF flows, price action, levels | Telegram + Email |
| 10:42 | Daily Alpha Brief | Market snapshot, flows, events | Telegram + Email |
| 10:43 | Pelosi Trade Tracker | AMZN LEAPS position status | Telegram + Email |
| 10:49 | ClawHub Skills Report | Top 30 skills ranking | Telegram + Email |
| 10:54 | LEAPS Buy Zone Monitor | GOOGL, AAPL, META, MU alerts | Telegram + Email |

### Tech/AI Reports (10:45-10:49 GMT+8)

| Time | Job | Description | Output |
|------|-----|-------------|--------|
| 10:45 | AI Intelligence Brief | arXiv papers, HN stories | Telegram + Email |
| 10:47 | Tech Radar | HuggingFace papers + GitHub trending | Telegram + Email |
| 10:49 | ClawHub Top 30 | Skills ranking report | Telegram + Email |

### Monitoring Jobs (06:01, 09:46, 10:51, 10:58 GMT+8)

| Time | Job | Description | Alert Condition |
|------|-----|-------------|-----------------|
| 05:00 | Strava Token Refresh | Refresh Strava API token | Auto |
| 06:01 | Pelosi Trading Check | New trades, filings | If new activity |
| 09:46 | Product Hunt Top 10 | Daily product launches | Telegram |
| 10:51 | Daily Email Summary | Unread, newsletters, action items | Telegram + Email |
| 10:58 | Iran War Risk Brief | Geopolitical risk assessment | Telegram + Email |

---

## 🔧 Configuration

### Environment Variables
```bash
# API Keys
export STRAVA_CLIENT_ID=xxx
export STRAVA_CLIENT_SECRET=xxx
export POLYMARKET_API_KEY=xxx

# Email
export EMAIL_USER=chefjose@pumpbtc.xyz
export EMAIL_PASS=xxx

# Telegram
export TELEGRAM_BOT_TOKEN=xxx
export TELEGRAM_CHAT_ID=1327790737
```

### Cron Schedule (crontab)
```cron
# Strava
0 5 * * * /root/clawd/strava_refresh_token.sh >> /root/clawd/logs/strava-token.log 2>&1
0 8 * * * /root/clawd/strava_daily_sync.sh

# Financial (9:45-10:54)
45 9 * * * cd /root/clawd && python3 scripts/ai_funding_news.py
39 10 * * * cd /root/clawd && python3 scripts/bitcoin_etf_report.py
42 10 * * * cd /root/clawd && python3 scripts/daily_alpha_brief.py
43 10 * * * cd /root/clawd && python3 scripts/pelosi_tracker.py
49 10 * * * cd /root/clawd && python3 scripts/clawhub_skills.py
54 10 * * * cd /root/clawd && python3 scripts/leaps_monitor.py

# Tech/AI (10:45-10:49)
45 10 * * * cd /root/clawd/ai_intelligence && python3 main.py
47 10 * * * cd /root/clawd && python3 scripts/tech_radar.py
49 10 * * * cd /root/clawd && python3 scripts/clawhub_top30.py

# Monitoring
1 6 * * * cd /root/clawd && python3 scripts/pelosi_check.py
46 9 * * * cd /root/clawd && python3 scripts/product_hunt.py
51 10 * * * cd /root/clawd && python3 scripts/email_summary.py
58 10 * * * cd /root/clawd && python3 scripts/iran_war_risk.py
```

---

## 📁 Repository Structure

```
Jose-Home-Dashboard/
├── README.md                 # This file
├── crontab.txt              # Full cron schedule
├── scripts/                 # Python/bash scripts
│   ├── ai_funding_news.py
│   ├── bitcoin_etf_report.py
│   ├── daily_alpha_brief.py
│   ├── pelosi_tracker.py
│   ├── leaps_monitor.py
│   ├── ai_intelligence.py
│   ├── tech_radar.py
│   ├── clawhub_skills.py
│   ├── iran_war_risk.py
│   └── email_summary.py
├── config/                  # Configuration files
│   ├── env.example
│   └── telegram_channels.json
├── logs/                    # Log files structure
│   ├── strava/
│   ├── financial/
│   └── ai/
├── docs/                    # Documentation
│   ├── setup.md
│   └── api_reference.md
└── dashboard/               # Web dashboard (future)
    ├── index.html
    └── assets/
```

---

## 📈 Key Metrics

### Portfolio Tracking
- **AMZN LEAPS**: $120 strike, Jan 2027 expiry, +73% vs strike
- **LEAPS Buy Zones**: Monitoring GOOGL ($165-175), AAPL ($240-250), META ($550-580), MU ($75-85)

### Market Data
- Bitcoin ETF AUM: $128B+
- March ETF Inflows: ~$700M
- Defense Sector: +31.8% YTD

### AI Tracking
- arXiv papers daily: ~30 papers
- HuggingFace trending: 27 upvotes max (LongCat-Flash-Prover)
- GitHub trending: deer-flow +3,546 stars/day

---

## 🔔 Alert Conditions

### Immediate Alerts
- Pelosi new trade filings
- LEAPS stocks entering buy zones
- Iran war risk escalation
- Important/urgent emails

### Daily Reports
- Market summaries
- AI research briefs
- Tech radar updates
- Fitness data sync

---

## 🛠️ Maintenance

### Weekly
- [ ] Review cron job logs
- [ ] Update API tokens if needed
- [ ] Check alert thresholds

### Monthly
- [ ] Analyze report accuracy
- [ ] Update buy zone levels
- [ ] Review portfolio performance

---

## 📞 Contact
- Telegram: @t0x_992
- Email: chefjose@pumpbtc.xyz

---

*Last Updated: March 24, 2026*
