import { createServerClient } from '@/lib/supabase'
import { NextResponse } from 'next/server'

const DEFAULT_LIMIT = 5
const MAX_LIMIT = 20
const DEFAULT_DAYS = 7
const MAX_DAYS = 90

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url)

    const module = searchParams.get('module') || null

    const rawLimit = parseInt(searchParams.get('limit') || String(DEFAULT_LIMIT))
    const limit = Number.isFinite(rawLimit) && rawLimit > 0 ? Math.min(rawLimit, MAX_LIMIT) : DEFAULT_LIMIT

    const rawDays = parseInt(searchParams.get('days') || String(DEFAULT_DAYS))
    const days = Number.isFinite(rawDays) && rawDays > 0 ? Math.min(rawDays, MAX_DAYS) : DEFAULT_DAYS

    const since = new Date()
    since.setDate(since.getDate() - days)
    const sinceDate = since.toISOString().slice(0, 10)

    const supabase = createServerClient()

    let query = supabase
      .from('reports')
      .select('*')
      .gte('date', sinceDate)
      .order('date', { ascending: false })
      .order('created_at', { ascending: false })
      .limit(limit)

    if (module) query = query.eq('module', module)

    const { data, error } = await query

    if (error) {
      console.error('[reports]', error)
      return NextResponse.json({ error: error.message }, { status: 500 })
    }

    return NextResponse.json(data)
  } catch (err) {
    console.error('[reports]', err)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
