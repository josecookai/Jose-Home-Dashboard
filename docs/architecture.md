# Data Architecture Design

## Overview

This document describes the data storage architecture for Jose Home Dashboard.

---

## Current State (v0.1)

### Cron Jobs Storage
- **Location**: `crontab.txt`
- **Format**: Standard cron syntax
- **Management**: Manual editing or `crontab -e`

### Logs Storage
- **Location**: `/root/clawd/logs/`
- **Format**: Text files (one per job)
- **Structure**:
  ```
  logs/
  ├── strava.log
  ├── pelosi.log
  ├── bitcoin_etf.log
  ├── ai_funding.log
  └── ...
  ```

### Report Output
- **Telegram**: Messages sent via Bot API
- **Email**: Sent via Himilaya CLI
- **Persistence**: None (ephemeral)

---

## Proposed Architecture (v1.0)

### Option A: SQLite (Recommended)

**Why SQLite:**
- Zero configuration
- Single file database
- Python built-in support
- Easy backup (just copy file)
- Good for single-user dashboard

**Database File**: `~/.openclaw/workspace/dashboard.db`

### Database Schema

#### 1. jobs table
Stores all cron job definitions (replaces crontab.txt):

```sql
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,           -- e.g., "pelosi_check"
    script_path TEXT NOT NULL,            -- e.g., "scripts/pelosi_check.py"
    schedule TEXT NOT NULL,               -- cron expression: "1 6 * * *"
    category TEXT CHECK(category IN (
        'financial', 'ai', 'health', 'geopolitical', 'email', 'monitoring'
    )),
    priority INTEGER DEFAULT 5,           -- 1-10 for execution ordering
    enabled BOOLEAN DEFAULT 1,
    description TEXT,
    telegram_chat_id TEXT DEFAULT '1327790737',
    email_to TEXT DEFAULT 'canalai2025@gmail.com',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Sample Data:**
```sql
INSERT INTO jobs (name, script_path, schedule, category, priority) VALUES
('pelosi_check', 'scripts/pelosi_check.py', '1 6 * * *', 'monitoring', 8),
('bitcoin_etf', 'scripts/bitcoin_etf_report.py', '39 10 * * *', 'financial', 9),
('ai_funding', 'scripts/ai_funding_news.py', '45 9 * * *', 'ai', 5);
```

#### 2. job_executions table
Tracks every job execution:

```sql
CREATE TABLE job_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER REFERENCES jobs(id),
    scheduled_at TIMESTAMP,               -- When it was supposed to run
    started_at TIMESTAMP,                 -- When it actually started
    completed_at TIMESTAMP,               -- When it finished
    status TEXT CHECK(status IN ('pending', 'running', 'success', 'failure', 'timeout')),
    exit_code INTEGER,                    -- Python script exit code
    output_summary TEXT,                  -- First 1000 chars of output
    full_output_path TEXT,                -- Path to full log file
    telegram_sent BOOLEAN DEFAULT 0,
    email_sent BOOLEAN DEFAULT 0,
    error_message TEXT,
    execution_time_ms INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Sample Data:**
```sql
INSERT INTO job_executions 
(job_id, scheduled_at, started_at, completed_at, status, exit_code, telegram_sent)
VALUES
(1, '2026-03-24 06:01:00', '2026-03-24 06:01:05', '2026-03-24 06:01:30', 'success', 0, 1);
```

#### 3. reports table
Stores generated reports for historical access:

```sql
CREATE TABLE reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_execution_id INTEGER REFERENCES job_executions(id),
    report_type TEXT NOT NULL,            -- e.g., "bitcoin_etf", "iran_risk"
    generated_date DATE,                  -- For easy filtering
    title TEXT,
    content TEXT,                         -- Full markdown content
    content_hash TEXT,                    -- SHA256 for deduplication
    key_metrics TEXT,                     -- JSON: {"btc_price": 70600, "spy_change": 1.15}
    telegram_message_id TEXT,             -- Reference to sent message
    email_message_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Sample Data:**
```sql
INSERT INTO reports 
(job_execution_id, report_type, generated_date, title, key_metrics)
VALUES
(1, 'bitcoin_etf', '2026-03-24', 'Bitcoin ETF Daily Flow - March 24, 2026',
 '{"btc_price": 70600, "ibit_inflow": 169.3, "fbtc_inflow": 24.4}');
```

#### 4. market_data table
Append-only market data for analysis:

```sql
CREATE TABLE market_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    date DATE,
    btc_price REAL,
    btc_change_24h REAL,
    eth_price REAL,
    spy_price REAL,
    spy_change REAL,
    vix REAL,
    gold_price REAL,
    oil_wti REAL,
    metadata TEXT                         -- JSON for additional metrics
);
```

#### 5. alerts table
Important events requiring attention:

```sql
CREATE TABLE alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_type TEXT NOT NULL,             -- e.g., "pelosi_new_trade", "leaps_buy_zone"
    severity TEXT CHECK(severity IN ('info', 'warning', 'critical')),
    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    message TEXT,
    related_job_id INTEGER REFERENCES jobs(id),
    related_execution_id INTEGER REFERENCES job_executions(id),
    acknowledged BOOLEAN DEFAULT 0,
    acknowledged_at TIMESTAMP,
    telegram_sent BOOLEAN DEFAULT 0
);
```

---

## Data Flow

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐
│   Cron      │────▶│   Python    │────▶│   SQLite     │
│   Daemon    │     │   Executor  │     │   Database   │
└─────────────┘     └─────────────┘     └──────────────┘
                            │                   │
                            ▼                   ▼
                     ┌─────────────┐     ┌──────────────┐
                     │   Script    │     │   Query      │
                     │   (Logic)   │     │   Dashboard  │
                     └─────────────┘     └──────────────┘
                            │
                            ▼
                     ┌─────────────┐
                     │   Output    │
                     │  Telegram   │
                     │   Email     │
                     └─────────────┘
```

---

## Migration Plan

### Phase 1: Database Setup
1. Create SQLite database
2. Create schema
3. Write migration script to import current jobs from crontab

### Phase 2: Update Scripts
1. Add database logging to each script
2. Store reports in DB
3. Track execution status

### Phase 3: Query Interface
1. Create query utilities
2. Add CLI for viewing history
3. Generate weekly/monthly summaries

### Phase 4: Web Dashboard (Future)
1. Flask/FastAPI web interface
2. View job status
3. Historical reports browser
4. Alert management

---

## Backup Strategy

### Daily Backup
```bash
# Backup database
cp ~/.openclaw/workspace/dashboard.db ~/.openclaw/workspace/backups/dashboard-$(date +%Y%m%d).db

# Keep last 7 days
find ~/.openclaw/workspace/backups/ -name "dashboard-*.db" -mtime +7 -delete
```

### Git Backup
Reports can be synced to Git for version control:
```
reports/
├── 2026/
│   ├── 03/
│   │   ├── bitcoin_etf_2026-03-24.md
│   │   └── pelosi_tracker_2026-03-24.md
```

---

## Query Examples

### View today's job executions
```sql
SELECT 
    j.name,
    je.status,
    je.execution_time_ms,
    je.telegram_sent
FROM job_executions je
JOIN jobs j ON je.job_id = j.id
WHERE DATE(je.created_at) = DATE('now')
ORDER BY je.started_at DESC;
```

### View failed jobs this week
```sql
SELECT 
    j.name,
    je.error_message,
    je.created_at
FROM job_executions je
JOIN jobs j ON je.job_id = j.id
WHERE je.status = 'failure'
  AND je.created_at >= DATE('now', '-7 days')
ORDER BY je.created_at DESC;
```

### Get latest market data
```sql
SELECT * FROM market_data
ORDER BY timestamp DESC
LIMIT 1;
```

### Count alerts by type
```sql
SELECT 
    alert_type,
    COUNT(*) as count,
    MAX(triggered_at) as last_triggered
FROM alerts
WHERE acknowledged = 0
GROUP BY alert_type;
```

---

## Implementation Priority

1. **P0 (Critical)**: Create database schema, migration script
2. **P1 (High)**: Update notification_utils.py to use DB
3. **P2 (Medium)**: Update all scripts to log executions
4. **P3 (Low)**: Create query CLI, web dashboard

---

## Open Questions

1. Should we keep logs as files AND in DB, or just DB?
2. Data retention policy? (30 days for executions, 90 days for reports?)
3. Do we need a separate config database or keep in files?
4. Should we encrypt sensitive data (API keys) in DB?

---

*Last Updated: March 24, 2026*
