import { NextResponse } from 'next/server';
import { createServerClient } from '@/lib/supabase';

// All cron jobs defined in crontab.txt (GMT+8 schedule time for display)
const CRON_JOBS: { module_name: string; schedule: string }[] = [
  { module_name: 'strava_token_refresh', schedule: '05:00' },
  { module_name: 'pelosi_check',         schedule: '06:01' },
  { module_name: 'strava_sync',          schedule: '08:00' },
  { module_name: 'strava_daily',         schedule: '08:05' },
  { module_name: 'ai_funding_news',      schedule: '09:45' },
  { module_name: 'product_hunt',         schedule: '09:50' },
  { module_name: 'ai_intelligence',      schedule: '09:55' },
  { module_name: 'tech_radar',           schedule: '10:00' },
  { module_name: 'bitcoin_etf_report',   schedule: '10:39' },
  { module_name: 'alpha_brief',          schedule: '10:42' },
  { module_name: 'pelosi_tracker',       schedule: '10:45' },
  { module_name: 'leaps_buy_zone',       schedule: '10:48' },
  { module_name: 'clawhub_skills',       schedule: '10:49' },
  { module_name: 'email_summary',        schedule: '10:51' },
  { module_name: 'iran_war_risk',        schedule: '10:58' },
];

export async function GET() {
  try {
    const supabase = createServerClient();

    const { data, error } = await supabase
      .from('module_status')
      .select('*');

    if (error) {
      console.error('[module-status] Supabase query error:', error);
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    const dbMap = new Map((data ?? []).map((row: Record<string, unknown>) => [row.module_name, row]));

    const merged = CRON_JOBS.map(({ module_name, schedule }) => {
      const db = dbMap.get(module_name) as Record<string, unknown> | undefined;
      return {
        id: db?.id ?? module_name,
        module_name,
        schedule,
        status: (db?.last_status as string) ?? 'pending',
        last_run_at: (db?.last_run_at as string) ?? null,
        last_message: (db?.last_message as string) ?? null,
      };
    });

    return NextResponse.json(merged);
  } catch (err) {
    console.error('[module-status] Unexpected error:', err);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
