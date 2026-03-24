import { createServerClient } from '@/lib/supabase'
import { NextResponse } from 'next/server'

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const date = searchParams.get('date')
  const source = searchParams.get('source')
  const limit = parseInt(searchParams.get('limit') || '20')

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
}
