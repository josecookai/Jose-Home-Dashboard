import { createServerClient } from '@/lib/supabase'
import { NextResponse } from 'next/server'

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const days = parseInt(searchParams.get('days') || '30')

  const supabase = createServerClient()

  const { data, error } = await supabase
    .from('strava_activities')
    .select('*')
    .order('date', { ascending: false })
    .limit(days)

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json(data)
}
