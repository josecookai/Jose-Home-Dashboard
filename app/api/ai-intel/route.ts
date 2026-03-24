import { createServerClient } from '@/lib/supabase'
import { NextResponse } from 'next/server'

const MAX_LIMIT = 100

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url)
    const date = searchParams.get('date')
    const source = searchParams.get('source')
    const rawLimit = parseInt(searchParams.get('limit') || '20')
    const limit = Number.isFinite(rawLimit) && rawLimit > 0 ? Math.min(rawLimit, MAX_LIMIT) : 20

    const supabase = createServerClient()

    let query = supabase
      .from('ai_intel_daily')
      .select('*')
      .order('date', { ascending: false })
      .limit(limit)

    if (date) query = query.eq('date', date)
    if (source) query = query.eq('source', source)

    const { data, error } = await query

    if (error) return NextResponse.json({ error: error.message }, { status: 500 })
    return NextResponse.json(data)
  } catch (err) {
    console.error('[ai-intel]', err)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
