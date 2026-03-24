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

export default function ClawHubCard() {
  const [report, setReport] = useState<ReportRow | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/reports?module=clawhub_skills&limit=1')
      .then((r) => r.json())
      .then((d) => {
        const rows = Array.isArray(d) ? d : []
        setReport(rows.length > 0 ? rows[0] : null)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-2xl">🦀</span>
        <h2 className="text-white font-semibold text-lg">ClawHub Skills</h2>
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
          暂无数据，请运行 clawhub_skills.py
        </div>
      ) : (
        <pre className="text-gray-300 text-xs whitespace-pre-wrap font-sans leading-relaxed max-h-80 overflow-y-auto">
          {report.content}
        </pre>
      )}
    </div>
  )
}
