import { createServerClient } from '@/lib/supabase'
import { NextResponse } from 'next/server'

const MAX_DAYS = 90

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url)
    const date = searchParams.get('date')
    const rawDays = parseInt(searchParams.get('days') || '7')
    const days = Number.isFinite(rawDays) && rawDays > 0 ? Math.min(rawDays, MAX_DAYS) : 7

    const supabase = createServerClient()

    if (date) {
      const { data, error } = await supabase
        .from('bitcoin_etf_daily')
        .select('*')
        .eq('date', date)
        .single()

      if (error) return NextResponse.json({ error: error.message }, { status: 404 })
      return NextResponse.json(data)
    }

    const { data, error } = await supabase
      .from('bitcoin_etf_daily')
      .select('*')
      .order('date', { ascending: false })
      .limit(days)

    if (error) return NextResponse.json({ error: error.message }, { status: 500 })
    return NextResponse.json(data)
  } catch (err) {
    console.error('[bitcoin-etf]', err)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
