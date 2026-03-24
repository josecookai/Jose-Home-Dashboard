import { createServerClient } from '@/lib/supabase'
import { NextResponse } from 'next/server'

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const date = searchParams.get('date')
  const days = parseInt(searchParams.get('days') || '7')

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
}
