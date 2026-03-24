-- Jose Home Dashboard — Supabase Schema
-- Run this in your Supabase SQL Editor

-- Bitcoin ETF daily data
CREATE TABLE IF NOT EXISTS bitcoin_etf_daily (
  id          bigserial PRIMARY KEY,
  date        date NOT NULL UNIQUE,
  btc_price   numeric,
  ibit_flow   numeric,
  fbtc_flow   numeric,
  gbtc_flow   numeric,
  total_flow  numeric,
  summary     text,
  raw_data    jsonb,
  created_at  timestamptz DEFAULT now()
);

-- AI intelligence daily items
CREATE TABLE IF NOT EXISTS ai_intel_daily (
  id          bigserial PRIMARY KEY,
  date        date NOT NULL,
  source      text NOT NULL CHECK (source IN ('arxiv', 'huggingface', 'github')),
  title       text NOT NULL,
  url         text,
  summary     text,
  tags        text[],
  created_at  timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ai_intel_daily_date_idx ON ai_intel_daily (date DESC);
CREATE INDEX IF NOT EXISTS ai_intel_daily_source_idx ON ai_intel_daily (source);

-- Strava activities
CREATE TABLE IF NOT EXISTS strava_activities (
  id              bigserial PRIMARY KEY,
  strava_id       bigint UNIQUE NOT NULL,
  date            date NOT NULL,
  activity_type   text NOT NULL,
  name            text,
  distance_km     numeric,
  duration_min    numeric,
  elevation_m     numeric,
  avg_hr          numeric,
  created_at      timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS strava_activities_date_idx ON strava_activities (date DESC);

-- Market positions (LEAPS options + Congressional trading)
CREATE TABLE IF NOT EXISTS market_positions (
  id           bigserial PRIMARY KEY,
  date         date NOT NULL,
  type         text NOT NULL CHECK (type IN ('leaps', 'congress')),
  ticker       text,
  action       text,
  details      jsonb,
  summary      text,
  created_at   timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS market_positions_date_idx ON market_positions (date DESC);
CREATE INDEX IF NOT EXISTS market_positions_type_idx ON market_positions (type);

-- Module run status (for monitoring cron jobs)
CREATE TABLE IF NOT EXISTS module_status (
  module_name  text PRIMARY KEY,
  last_run_at  timestamptz,
  last_status  text CHECK (last_status IN ('success', 'error')),
  last_message text,
  updated_at   timestamptz DEFAULT now()
);

-- Enable Row Level Security (allow public read for anon key)
ALTER TABLE bitcoin_etf_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_intel_daily ENABLE ROW LEVEL SECURITY;
ALTER TABLE strava_activities ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE module_status ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow public read" ON bitcoin_etf_daily FOR SELECT USING (true);
CREATE POLICY "Allow public read" ON ai_intel_daily FOR SELECT USING (true);
CREATE POLICY "Allow public read" ON strava_activities FOR SELECT USING (true);
CREATE POLICY "Allow public read" ON market_positions FOR SELECT USING (true);
CREATE POLICY "Allow public read" ON module_status FOR SELECT USING (true);

-- Job execution tracking
CREATE TABLE IF NOT EXISTS job_executions (
  id           bigserial PRIMARY KEY,
  job_name     text NOT NULL,
  started_at   timestamptz DEFAULT now(),
  finished_at  timestamptz,
  status       text CHECK (status IN ('running', 'success', 'error')),
  rows_written integer DEFAULT 0,
  error_msg    text
);
CREATE INDEX IF NOT EXISTS job_executions_job_name_idx ON job_executions (job_name, started_at DESC);

-- Market data snapshots (generic)
CREATE TABLE IF NOT EXISTS market_data (
  id         bigserial PRIMARY KEY,
  date       date NOT NULL,
  symbol     text NOT NULL,
  data_type  text NOT NULL,
  value      numeric,
  extra      jsonb,
  created_at timestamptz DEFAULT now(),
  UNIQUE(date, symbol, data_type)
);

-- Alerts log
CREATE TABLE IF NOT EXISTS alerts (
  id         bigserial PRIMARY KEY,
  created_at timestamptz DEFAULT now(),
  level      text NOT NULL CHECK (level IN ('info', 'warning', 'critical')),
  module     text NOT NULL,
  message    text NOT NULL,
  sent_via   text[]
);
CREATE INDEX IF NOT EXISTS alerts_module_idx ON alerts (module, created_at DESC);

-- Reports archive
CREATE TABLE IF NOT EXISTS reports (
  id         bigserial PRIMARY KEY,
  date       date NOT NULL,
  module     text NOT NULL,
  content    text NOT NULL,
  format     text DEFAULT 'markdown',
  created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS reports_date_module_idx ON reports (date DESC, module);

-- RLS policies
ALTER TABLE job_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_data ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow public read" ON job_executions FOR SELECT USING (true);
CREATE POLICY "Allow public read" ON market_data FOR SELECT USING (true);
CREATE POLICY "Allow public read" ON alerts FOR SELECT USING (true);
CREATE POLICY "Allow public read" ON reports FOR SELECT USING (true);
