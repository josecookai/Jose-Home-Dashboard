'use client'

import { useEffect, useState } from 'react'

interface ReportRow {
  id: number
  date: string
  module: string
  content: string
  format: string
  created_at: string
}

function parseRiskScore(content: string): { score: number; level: string } | null {
  const match = content.match(/Risk Score[:\s]+(\d+)\s*\/\s*100\s*[—–-]\s*([^\n\r,]+)/i)
  if (!match) return null
  const score = parseInt(match[1], 10)
  const level = match[2].trim().replace(/[*_]/g, '')
  return { score, level }
}

function riskColors(score: number) {
  if (score <= 30) return { text: 'text-green-400', bar: 'bg-green-500' }
  if (score <= 50) return { text: 'text-yellow-400', bar: 'bg-yellow-500' }
  if (score <= 70) return { text: 'text-orange-400', bar: 'bg-orange-500' }
  return { text: 'text-red-400', bar: 'bg-red-500' }
}

function riskEmoji(score: number): string {
  if (score <= 30) return '🟢'
  if (score <= 50) return '🟡'
  if (score <= 70) return '🟠'
  return '🔴'
}

export default function IranRiskCard() {
  const [report, setReport] = useState<ReportRow | null>(null)
  const [loading, setLoading] = useState(true)
  const [showContent, setShowContent] = useState(false)

  useEffect(() => {
    fetch('/api/reports?module=iran_war_risk&limit=1')
      .then((r) => r.json())
      .then((d) => {
        const rows = Array.isArray(d) ? d : []
        setReport(rows.length > 0 ? rows[0] : null)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const parsed = report ? parseRiskScore(report.content) : null
  const colors = parsed ? riskColors(parsed.score) : null

  const rationale: string[] = []
  if (report?.content) {
    for (const line of report.content.split('\n')) {
      const t = line.trim()
      if (/^[-•▸*]/.test(t) && t.length > 5 && t.length < 200) {
        rationale.push(t.replace(/^[-•▸*]\s*/, ''))
      }
    }
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-2xl">⚠️</span>
        <h2 className="text-white font-semibold text-lg">伊朗战争风险</h2>
        {report && (
          <span className="ml-auto text-gray-500 text-xs">{report.date}</span>
        )}
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 bg-gray-800 rounded-lg animate-pulse" />
          ))}
        </div>
      ) : !report ? (
        <div className="text-center py-8 text-gray-500 text-sm">
          暂无数据，请运行 iran_war_risk.py
        </div>
      ) : (
        <div className="space-y-4">
          {/* Risk Score Meter */}
          {parsed && colors ? (
            <div className="bg-gray-800 rounded-lg p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-xl">{riskEmoji(parsed.score)}</span>
                  <div>
                    <p className="text-gray-400 text-xs">综合风险评分</p>
                    <p className={`text-xs font-medium ${colors.text}`}>{parsed.level}</p>
                  </div>
                </div>
                <span className={`text-3xl font-bold font-mono ${colors.text}`}>
                  {parsed.score}
                  <span className="text-base text-gray-500 font-normal">/100</span>
                </span>
              </div>
              <div className="w-full bg-gray-700 rounded-full h-2">
                <div
                  className={`h-2 rounded-full ${colors.bar}`}
                  style={{ width: `${parsed.score}%` }}
                />
              </div>
              <div className="flex justify-between mt-1">
                <span className="text-gray-600 text-xs">低风险</span>
                <span className="text-gray-600 text-xs">高风险</span>
              </div>
            </div>
          ) : null}

          {/* Rationale bullets */}
          {rationale.length > 0 && (
            <ul className="space-y-1.5">
              {rationale.slice(0, 4).map((r, i) => (
                <li key={i} className="flex gap-2 text-xs text-gray-400 leading-relaxed">
                  <span className="text-gray-600 shrink-0 mt-0.5">·</span>
                  <span>{r}</span>
                </li>
              ))}
            </ul>
          )}

          {/* Fallback or expandable raw content */}
          {!parsed && rationale.length === 0 ? (
            <pre className="text-gray-300 text-xs whitespace-pre-wrap font-sans leading-relaxed max-h-64 overflow-y-auto">
              {report.content}
            </pre>
          ) : (
            <button
              onClick={() => setShowContent((v) => !v)}
              className="text-xs text-gray-600 hover:text-gray-400 transition-colors flex items-center gap-1"
            >
              {showContent ? '▲ 收起详情' : '▼ 展开完整报告'}
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
