import { createServerClient } from '@/lib/supabase'
import { NextResponse } from 'next/server'

const MAX_LIMIT = 90
const VALID_TYPES = new Set(['leaps', 'congress'])

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url)
    const rawType = searchParams.get('type')
    const type = rawType && VALID_TYPES.has(rawType) ? rawType : null
    const rawDays = parseInt(searchParams.get('days') || '30')
    const limit = Number.isFinite(rawDays) && rawDays > 0 ? Math.min(rawDays, MAX_LIMIT) : 30

    const supabase = createServerClient()

    let query = supabase
      .from('market_positions')
      .select('*')
      .order('date', { ascending: false })
      .limit(limit)

    if (type) query = query.eq('type', type)

    const { data, error } = await query

    if (error) return NextResponse.json({ error: error.message }, { status: 500 })
    return NextResponse.json(data)
  } catch (err) {
    console.error('[leaps]', err)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
