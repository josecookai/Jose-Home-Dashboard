import { createServerClient } from '@/lib/supabase'
import { NextResponse } from 'next/server'

const MAX_LIMIT = 90

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url)
    const rawDays = parseInt(searchParams.get('days') || '30')
    const limit = Number.isFinite(rawDays) && rawDays > 0 ? Math.min(rawDays, MAX_LIMIT) : 30

    const supabase = createServerClient()

    const { data, error } = await supabase
      .from('strava_activities')
      .select('*')
      .order('date', { ascending: false })
      .limit(limit)

    if (error) return NextResponse.json({ error: error.message }, { status: 500 })
    return NextResponse.json(data)
  } catch (err) {
    console.error('[strava]', err)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
