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
    <div className="glass-panel rounded-[24px] p-5 sm:p-6">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-2xl">₿</span>
          <div>
            <h2 className="text-lg font-semibold text-white">Bitcoin ETF</h2>
            <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Flow monitor</p>
          </div>
        </div>
        {latest?.btc_price && (
          <span className="rounded-full bg-orange-400/10 px-3 py-1 font-mono text-lg font-bold text-orange-300">
            ${formatNumber(latest.btc_price, 0).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
          </span>
        )}
      </div>

      {latest ? (
        <>
          <div className="mb-4 grid grid-cols-3 gap-3">
            <FlowStat label="IBIT" value={latest.ibit_flow} />
            <FlowStat label="FBTC" value={latest.fbtc_flow} />
            <FlowStat label="GBTC" value={latest.gbtc_flow} />
          </div>

          <div className="mb-4 rounded-2xl border border-white/8 bg-white/4 p-4">
            <p className="mb-1 text-xs uppercase tracking-[0.16em] text-slate-400">Total net flow</p>
            <p className={`text-2xl font-bold font-mono ${latest.total_flow >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>
              {formatMillions(latest.total_flow)}
            </p>
          </div>

          {data.length > 1 && (
            <div className="h-36 rounded-2xl border border-white/8 bg-slate-950/30 p-2">
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
            <p className="mt-4 text-sm leading-relaxed text-slate-400">{latest.summary}</p>
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
    <div className="rounded-2xl border border-white/8 bg-white/4 p-3 text-center">
      <p className="mb-1 text-xs uppercase tracking-[0.16em] text-slate-500">{label}</p>
      <p className={`text-sm font-mono font-semibold ${isPositive ? 'text-emerald-300' : 'text-rose-300'}`}>
        {formatMillions(value)}
      </p>
    </div>
  )
}

function CardSkeleton() {
  return (
    <div className="glass-panel rounded-[24px] p-5 animate-pulse">
      <div className="mb-4 h-6 w-1/3 rounded bg-white/8" />
      <div className="mb-4 grid grid-cols-3 gap-3">
        {[1, 2, 3].map((i) => <div key={i} className="h-12 rounded-2xl bg-white/8" />)}
      </div>
      <div className="h-32 rounded-2xl bg-white/8" />
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="py-8 text-center text-sm text-slate-500">{message}</div>
  )
}
