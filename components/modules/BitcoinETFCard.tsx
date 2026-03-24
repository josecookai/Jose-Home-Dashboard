'use client'

import { useEffect, useState } from 'react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { formatMillions, formatNumber } from '@/lib/utils'

interface BTCData {
  date: string
  btc_price: number
  ibit_flow: number
  fbtc_flow: number
  gbtc_flow: number
  total_flow: number
  summary: string
}

export default function BitcoinETFCard() {
  const [data, setData] = useState<BTCData[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/bitcoin-etf?days=14')
      .then((r) => r.json())
      .then((d) => {
        setData(Array.isArray(d) ? d.reverse() : [])
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const latest = data[data.length - 1]

  if (loading) return <CardSkeleton />

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="text-2xl">₿</span>
          <h2 className="text-white font-semibold text-lg">Bitcoin ETF</h2>
        </div>
        {latest?.btc_price && (
          <span className="text-orange-400 font-mono font-bold text-lg">
            ${formatNumber(latest.btc_price, 0).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
          </span>
        )}
      </div>

      {latest ? (
        <>
          <div className="grid grid-cols-3 gap-3 mb-4">
            <FlowStat label="IBIT" value={latest.ibit_flow} />
            <FlowStat label="FBTC" value={latest.fbtc_flow} />
            <FlowStat label="GBTC" value={latest.gbtc_flow} />
          </div>

          <div className="mb-4 p-3 bg-gray-800 rounded-lg">
            <p className="text-xs text-gray-400 mb-1">今日总净流入</p>
            <p className={`text-xl font-bold font-mono ${latest.total_flow >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {formatMillions(latest.total_flow)}
            </p>
          </div>

          {data.length > 1 && (
            <div className="h-32">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="flowGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#f97316" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#f97316" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" tick={{ fill: '#6b7280', fontSize: 10 }} tickFormatter={(v) => v.slice(5)} />
                  <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#1f2937', border: 'none', borderRadius: '8px' }}
                    labelStyle={{ color: '#9ca3af' }}
                    formatter={(v) => [formatMillions(v as number), '净流入']}
                  />
                  <Area type="monotone" dataKey="total_flow" stroke="#f97316" fill="url(#flowGradient)" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}

          {latest.summary && (
            <p className="text-gray-400 text-xs mt-3 leading-relaxed">{latest.summary}</p>
          )}
        </>
      ) : (
        <EmptyState message="暂无 ETF 数据，请运行 bitcoin_etf_report.py" />
      )}
    </div>
  )
}

function FlowStat({ label, value }: { label: string; value: number }) {
  const isPositive = value >= 0
  return (
    <div className="bg-gray-800 rounded-lg p-2 text-center">
      <p className="text-gray-400 text-xs mb-1">{label}</p>
      <p className={`text-sm font-mono font-semibold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
        {formatMillions(value)}
      </p>
    </div>
  )
}

function CardSkeleton() {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 animate-pulse">
      <div className="h-6 bg-gray-800 rounded w-1/3 mb-4" />
      <div className="grid grid-cols-3 gap-3 mb-4">
        {[1, 2, 3].map((i) => <div key={i} className="h-12 bg-gray-800 rounded-lg" />)}
      </div>
      <div className="h-32 bg-gray-800 rounded-lg" />
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="text-center py-8 text-gray-500 text-sm">{message}</div>
  )
}
