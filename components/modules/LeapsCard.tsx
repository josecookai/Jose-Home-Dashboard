'use client'

import { useEffect, useState } from 'react'

interface Position {
  id: number
  date: string
  type: 'leaps' | 'congress'
  ticker: string
  action: string
  details: Record<string, unknown>
  summary: string
}

const ACTION_COLORS: Record<string, string> = {
  buy: 'text-green-400 bg-green-400/10',
  sell: 'text-red-400 bg-red-400/10',
  purchase: 'text-green-400 bg-green-400/10',
  sale: 'text-red-400 bg-red-400/10',
  hold: 'text-yellow-400 bg-yellow-400/10',
}

export default function LeapsCard() {
  const [data, setData] = useState<Position[]>([])
  const [loading, setLoading] = useState(true)
  const [activeType, setActiveType] = useState<'all' | 'leaps' | 'congress'>('all')

  useEffect(() => {
    fetch('/api/leaps?days=30')
      .then((r) => r.json())
      .then((d) => {
        setData(Array.isArray(d) ? d : [])
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const filtered = activeType === 'all' ? data : data.filter((d) => d.type === activeType)
  const leapsCount = data.filter((d) => d.type === 'leaps').length
  const congressCount = data.filter((d) => d.type === 'congress').length

  return (
    <div className="glass-panel rounded-[24px] p-5 sm:p-6">
      <div className="mb-4 flex items-center gap-2">
        <span className="text-2xl">📊</span>
        <div>
          <h2 className="text-lg font-semibold text-white">LEAPS & 国会交易</h2>
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Position watchlist</p>
        </div>
      </div>

      <div className="mb-4 flex gap-2">
        {(['all', 'leaps', 'congress'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setActiveType(t)}
            className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
              activeType === t ? 'bg-sky-400 text-slate-950' : 'bg-white/5 text-slate-400 hover:bg-white/10'
            }`}
          >
            {t === 'all' ? `全部 (${data.length})` : t === 'leaps' ? `LEAPS (${leapsCount})` : `国会 (${congressCount})`}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-3 animate-pulse">
          {[1, 2, 3].map((i) => <div key={i} className="h-16 rounded-2xl bg-white/8" />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="py-8 text-center text-sm text-slate-500">暂无数据，请运行 leaps_monitor.py</div>
      ) : (
        <div className="soft-scroll max-h-80 space-y-2 overflow-y-auto pr-1">
          {filtered.map((pos) => {
            const actionKey = pos.action?.toLowerCase() || ''
            const colorClass = ACTION_COLORS[actionKey] || 'text-gray-400 bg-gray-400/10'
            return (
              <div key={pos.id} className="rounded-2xl border border-white/8 bg-white/4 p-3">
                <div className="mb-1 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-white font-bold font-mono">{pos.ticker}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium uppercase ${colorClass}`}>
                      {pos.action}
                    </span>
                    <span className="rounded-full bg-slate-900/60 px-2 py-0.5 text-xs text-slate-500">
                      {pos.type === 'leaps' ? 'LEAPS' : '国会'}
                    </span>
                  </div>
                  <span className="text-xs text-slate-500">{pos.date}</span>
                </div>
                {pos.summary && (
                  <p className="text-xs leading-relaxed text-slate-400">{pos.summary}</p>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
