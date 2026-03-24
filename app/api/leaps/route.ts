import { createServerClient } from '@/lib/supabase'
import { NextResponse } from 'next/server'

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const type = searchParams.get('type')
  const days = parseInt(searchParams.get('days') || '30')

  const supabase = createServerClient()

  let query = supabase
    .from('market_positions')
    .select('*')
    .order('date', { ascending: false })
    .limit(days)

  if (type) query = query.eq('type', type)

  const { data, error } = await query

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json(data)
}
