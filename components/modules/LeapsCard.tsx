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
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-2xl">📊</span>
        <h2 className="text-white font-semibold text-lg">LEAPS & 国会交易</h2>
      </div>

      <div className="flex gap-2 mb-4">
        {(['all', 'leaps', 'congress'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setActiveType(t)}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              activeType === t ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
            }`}
          >
            {t === 'all' ? `全部 (${data.length})` : t === 'leaps' ? `LEAPS (${leapsCount})` : `国会 (${congressCount})`}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-3 animate-pulse">
          {[1, 2, 3].map((i) => <div key={i} className="h-16 bg-gray-800 rounded-lg" />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-8 text-gray-500 text-sm">暂无数据，请运行 leaps_monitor.py</div>
      ) : (
        <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
          {filtered.map((pos) => {
            const actionKey = pos.action?.toLowerCase() || ''
            const colorClass = ACTION_COLORS[actionKey] || 'text-gray-400 bg-gray-400/10'
            return (
              <div key={pos.id} className="bg-gray-800 rounded-lg p-3">
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className="text-white font-bold font-mono">{pos.ticker}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium uppercase ${colorClass}`}>
                      {pos.action}
                    </span>
                    <span className="text-xs text-gray-500 bg-gray-700 px-2 py-0.5 rounded">
                      {pos.type === 'leaps' ? 'LEAPS' : '国会'}
                    </span>
                  </div>
                  <span className="text-gray-500 text-xs">{pos.date}</span>
                </div>
                {pos.summary && (
                  <p className="text-gray-400 text-xs leading-relaxed">{pos.summary}</p>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
