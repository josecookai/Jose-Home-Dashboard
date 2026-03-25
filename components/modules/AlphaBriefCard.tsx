'use client'

import { useEffect, useState } from 'react'

interface IndexEntry {
  symbol: string
  price: number
  prev_price: number
  change_pct: number
}

interface FearGreed {
  value: number
  classification: string
}

interface ExtraData {
  index_data?: IndexEntry[]
  fear_greed?: FearGreed
  headline_count?: number
}

interface ReportRow {
  id: number
  date: string
  module: string
  content: string
  format: string
  extra: string | null
  created_at: string
}

const TICKER_LABEL: Record<string, string> = {
  'SPY': 'S&P 500',
  'QQQ': 'NASDAQ',
  'BTC-USD': 'Bitcoin',
}

function fgColor(value: number): string {
  if (value <= 25) return 'text-red-400'
  if (value <= 45) return 'text-orange-400'
  if (value <= 55) return 'text-yellow-400'
  if (value <= 75) return 'text-green-400'
  return 'text-emerald-400'
}

function fgBarColor(value: number): string {
  if (value <= 25) return 'bg-red-500'
  if (value <= 45) return 'bg-orange-500'
  if (value <= 55) return 'bg-yellow-500'
  if (value <= 75) return 'bg-green-500'
  return 'bg-emerald-500'
}

function fgEmoji(classification: string): string {
  const c = classification.toLowerCase()
  if (c.includes('extreme fear')) return '😱'
  if (c.includes('fear')) return '😰'
  if (c.includes('neutral')) return '😐'
  if (c.includes('extreme greed')) return '🚀'
  if (c.includes('greed')) return '🤑'
  return '📊'
}

export default function AlphaBriefCard() {
  const [report, setReport] = useState<ReportRow | null>(null)
  const [loading, setLoading] = useState(true)
  const [showContent, setShowContent] = useState(false)

  useEffect(() => {
    fetch('/api/reports?module=alpha_brief&limit=1')
      .then((r) => r.json())
      .then((d) => {
        const rows = Array.isArray(d) ? d : []
        setReport(rows[0] ?? null)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  let extra: ExtraData | null = null
  if (report?.extra) {
    try {
      extra = JSON.parse(report.extra) as ExtraData
    } catch {
      extra = null
    }
  }

  const indices = extra?.index_data ?? []
  const fg = extra?.fear_greed ?? null

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-2xl">📈</span>
        <h2 className="text-white font-semibold text-lg">Alpha Brief</h2>
        {report && (
          <span className="ml-auto text-gray-500 text-xs">{report.date}</span>
        )}
      </div>

      {loading ? (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 bg-gray-800 rounded-lg animate-pulse" />
            ))}
          </div>
          <div className="h-12 bg-gray-800 rounded-lg animate-pulse" />
        </div>
      ) : !report ? (
        <div className="text-center py-8 text-gray-500 text-sm">
          暂无数据，请运行 alpha_brief.py
        </div>
      ) : (
        <div className="space-y-4">
          {/* Market Indices */}
          {indices.length > 0 ? (
            <div className="grid grid-cols-3 gap-3">
              {indices.map((idx) => (
                <div key={idx.symbol} className="bg-gray-800 rounded-lg p-3">
                  <p className="text-gray-400 text-xs mb-1 truncate">
                    {TICKER_LABEL[idx.symbol] ?? idx.symbol}
                  </p>
                  <p className="text-white text-sm font-bold font-mono">
                    {idx.symbol === 'BTC-USD'
                      ? `$${(idx.price / 1000).toFixed(1)}k`
                      : `$${idx.price.toLocaleString('en-US', { maximumFractionDigits: 0 })}`}
                  </p>
                  <p className={`text-xs font-mono font-medium mt-0.5 ${idx.change_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {idx.change_pct >= 0 ? '▲' : '▼'} {Math.abs(idx.change_pct).toFixed(2)}%
                  </p>
                </div>
              ))}
            </div>
          ) : null}

          {/* Fear & Greed Index */}
          {fg ? (
            <div className="bg-gray-800 rounded-lg p-3">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-base">{fgEmoji(fg.classification)}</span>
                  <span className="text-xs text-gray-400">Fear &amp; Greed Index</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-sm font-bold font-mono ${fgColor(fg.value)}`}>
                    {fg.value}
                  </span>
                  <span className={`text-xs ${fgColor(fg.value)}`}>{fg.classification}</span>
                </div>
              </div>
              <div className="w-full bg-gray-700 rounded-full h-1.5">
                <div
                  className={`h-1.5 rounded-full ${fgBarColor(fg.value)}`}
                  style={{ width: `${fg.value}%` }}
                />
              </div>
            </div>
          ) : null}

          {/* Fallback or expandable raw content */}
          {indices.length === 0 && !fg ? (
            <pre className="text-gray-300 text-xs whitespace-pre-wrap font-sans leading-relaxed max-h-64 overflow-y-auto">
              {report.content}
            </pre>
          ) : (
            <button
              onClick={() => setShowContent((v) => !v)}
              className="text-xs text-gray-600 hover:text-gray-400 transition-colors flex items-center gap-1"
            >
              {showContent ? '▲ 收起摘要' : '▼ 展开完整摘要'}
            </button>
          )}
          {showContent && (
            <pre className="text-gray-400 text-xs whitespace-pre-wrap font-sans leading-relaxed max-h-48 overflow-y-auto">
              {report.content}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}
