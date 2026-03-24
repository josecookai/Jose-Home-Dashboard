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
        setData(Array.isArray(d) ? [...d].sort((a, b) => a.date.localeCompare(b.date)) : [])
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const totalKm = data.reduce((s, a) => s + (a.distance_km || 0), 0)
  const totalMin = data.reduce((s, a) => s + (a.duration_min || 0), 0)
  const hrData = data.filter((a) => a.avg_hr != null && a.avg_hr > 0)
  const avgHr = hrData.length > 0 ? hrData.reduce((s, a) => s + a.avg_hr, 0) / hrData.length : 0

  const chartData = data.map((a) => ({
    date: a.date.slice(5),
    km: a.distance_km,
    type: a.activity_type,
  }))

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-2xl">🏃</span>
        <h2 className="text-white font-semibold text-lg">Strava 健身</h2>
        <span className="ml-auto text-gray-500 text-xs">近14天</span>
      </div>

      {loading ? (
        <div className="space-y-3 animate-pulse">
          <div className="grid grid-cols-3 gap-3">
            {[1, 2, 3].map((i) => <div key={i} className="h-16 bg-gray-800 rounded-lg" />)}
          </div>
          <div className="h-32 bg-gray-800 rounded-lg" />
        </div>
      ) : data.length === 0 ? (
        <div className="text-center py-8 text-gray-500 text-sm">暂无数据，请运行 strava_sync.py</div>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-3 mb-4">
            <StatBox label="总距离" value={`${totalKm.toFixed(1)} km`} color="text-green-400" />
            <StatBox label="总时长" value={`${Math.round(totalMin)} min`} color="text-blue-400" />
            <StatBox label="平均心率" value={avgHr > 0 ? `${Math.round(avgHr)} bpm` : 'N/A'} color="text-red-400" />
          </div>

          <div className="h-32 mb-4">
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

          <div className="space-y-2 max-h-40 overflow-y-auto">
            {[...data].sort((a, b) => b.date.localeCompare(a.date)).slice(0, 5).map((a) => (
              <div key={a.id} className="flex items-center justify-between bg-gray-800 rounded-lg px-3 py-2">
                <div className="flex items-center gap-2">
                  <span>{TYPE_EMOJI[a.activity_type] || '💪'}</span>
                  <div>
                    <p className="text-white text-xs font-medium">{a.name || a.activity_type}</p>
                    <p className="text-gray-500 text-xs">{a.date}</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-green-400 text-xs font-mono">{a.distance_km?.toFixed(1)} km</p>
                  <p className="text-gray-500 text-xs">{Math.round(a.duration_min)} min</p>
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
    <div className="bg-gray-800 rounded-lg p-3 text-center">
      <p className="text-gray-400 text-xs mb-1">{label}</p>
      <p className={`text-sm font-bold font-mono ${color}`}>{value}</p>
    </div>
  )
}
