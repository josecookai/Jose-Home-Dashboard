-- Jose Home Dashboard — Schema Fixes
-- Run this in the Supabase SQL Editor: https://supabase.com/dashboard/project/gdlqmrtgkngwajlfzgzo/sql
--
-- This migration adds missing columns and constraints that scripts depend on.

-- 1. Add UNIQUE constraint to market_positions for upsert support
--    Required by: leaps_monitor.py, pelosi_tracker.py, pelosi_check.py
ALTER TABLE market_positions
  ADD CONSTRAINT IF NOT EXISTS market_positions_date_type_ticker_key
  UNIQUE (date, type, ticker);

-- 2. Add UNIQUE constraint to reports for idempotent daily saves
--    Required by: alpha_brief.py, iran_war_risk.py, clawhub_skills.py, etc.
ALTER TABLE reports
  ADD CONSTRAINT IF NOT EXISTS reports_date_module_key
  UNIQUE (date, module);

-- 3. Ensure ai_intel_daily allows all source types used by scripts
--    (funding, producthunt, tech_radar) — drop the old restrictive CHECK if it exists
ALTER TABLE ai_intel_daily
  DROP CONSTRAINT IF EXISTS ai_intel_daily_source_check;

-- 4. Add broader CHECK that includes all valid sources
ALTER TABLE ai_intel_daily
  ADD CONSTRAINT IF NOT EXISTS ai_intel_daily_source_check
  CHECK (source IN ('arxiv', 'huggingface', 'github', 'funding', 'producthunt', 'tech_radar'));

-- 5. Add UNIQUE constraint on ai_intel_daily for upsert support
--    Required by: ai_intelligence.py, product_hunt.py, tech_radar.py
ALTER TABLE ai_intel_daily
  ADD CONSTRAINT IF NOT EXISTS ai_intel_daily_date_source_title_key
  UNIQUE (date, source, title);
