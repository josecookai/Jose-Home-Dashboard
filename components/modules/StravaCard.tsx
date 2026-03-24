'use client'

import { useEffect, useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

interface Activity {
  id: number
  date: string
  activity_type: string
  name: string
  distance_km: number
  duration_min: number
  elevation_m: number
  avg_hr: number
}

const TYPE_EMOJI: Record<string, string> = {
  Run: '🏃',
  Ride: '🚴',
  Swim: '🏊',
  Walk: '🚶',
  Hike: '⛰️',
  WeightTraining: '🏋️',
}

export default function StravaCard() {
  const [data, setData] = useState<Activity[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/strava?days=14')
      .then((r) => r.json())
      .then((d) => {
        setData(Array.isArray(d) ? d.reverse() : [])
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const totalKm = data.reduce((s, a) => s + (a.distance_km || 0), 0)
  const totalMin = data.reduce((s, a) => s + (a.duration_min || 0), 0)
  const avgHr = data.filter((a) => a.avg_hr).reduce((s, a, _, arr) => s + a.avg_hr / arr.length, 0)

  const chartData = data.map((a) => ({
    date: a.date.slice(5),
    km: a.distance_km,
    type: a.activity_type,
  }))

  return (
    <div className="glass-panel rounded-[24px] p-5 sm:p-6">
      <div className="mb-4 flex items-center gap-2">
        <span className="text-2xl">🏃</span>
        <div>
          <h2 className="text-lg font-semibold text-white">Strava 健身</h2>
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">14 day activity</p>
        </div>
        <span className="ml-auto rounded-full bg-white/5 px-3 py-1 text-xs text-slate-400">近14天</span>
      </div>

      {loading ? (
        <div className="space-y-3 animate-pulse">
          <div className="grid grid-cols-3 gap-3">
            {[1, 2, 3].map((i) => <div key={i} className="h-16 rounded-2xl bg-white/8" />)}
          </div>
          <div className="h-32 rounded-2xl bg-white/8" />
        </div>
      ) : data.length === 0 ? (
        <div className="py-8 text-center text-sm text-slate-500">暂无数据，请运行 strava_sync.py</div>
      ) : (
        <>
          <div className="mb-4 grid grid-cols-3 gap-3">
            <StatBox label="总距离" value={`${totalKm.toFixed(1)} km`} color="text-emerald-300" />
            <StatBox label="总时长" value={`${Math.round(totalMin)} min`} color="text-sky-300" />
            <StatBox label="平均心率" value={avgHr > 0 ? `${Math.round(avgHr)} bpm` : 'N/A'} color="text-rose-300" />
          </div>

          <div className="mb-4 h-36 rounded-2xl border border-white/8 bg-slate-950/30 p-2">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                <XAxis dataKey="date" tick={{ fill: '#6b7280', fontSize: 10 }} />
                <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1f2937', border: 'none', borderRadius: '8px' }}
                  formatter={(v) => [`${v} km`, '距离']}
                />
                <Bar dataKey="km" fill="#22c55e" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="soft-scroll max-h-40 space-y-2 overflow-y-auto">
            {[...data].reverse().slice(0, 5).map((a) => (
              <div key={a.id} className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-3 py-3">
                <div className="flex items-center gap-2">
                  <span>{TYPE_EMOJI[a.activity_type] || '💪'}</span>
                  <div>
                    <p className="text-white text-xs font-medium">{a.name || a.activity_type}</p>
                    <p className="text-xs text-slate-500">{a.date}</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-xs font-mono text-emerald-300">{a.distance_km?.toFixed(1)} km</p>
                  <p className="text-xs text-slate-500">{Math.round(a.duration_min)} min</p>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function StatBox({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="rounded-2xl border border-white/8 bg-white/4 p-3 text-center">
      <p className="mb-1 text-xs uppercase tracking-[0.16em] text-slate-500">{label}</p>
      <p className={`text-sm font-bold font-mono ${color}`}>{value}</p>
    </div>
  )
}
