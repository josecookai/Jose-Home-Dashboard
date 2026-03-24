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

export default function AlphaBriefCard() {
  const [data, setData] = useState<ReportRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/reports?module=alpha_brief&limit=5')
      .then((r) => r.json())
      .then((d) => {
        setData(Array.isArray(d) ? d : [])
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const latest = data[0] ?? null

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-2xl">📈</span>
        <h2 className="text-white font-semibold text-lg">Alpha Brief</h2>
        {latest && (
          <span className="ml-auto text-gray-500 text-xs">{latest.date}</span>
        )}
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 bg-gray-800 rounded-lg animate-pulse" />
          ))}
        </div>
      ) : !latest ? (
        <div className="text-center py-8 text-gray-500 text-sm">
          暂无数据，请运行 alpha_brief.py
        </div>
      ) : (
        <div className="max-h-80 overflow-y-auto pr-1">
          <pre className="text-gray-300 text-xs whitespace-pre-wrap font-sans leading-relaxed">
            {latest.content}
          </pre>
        </div>
      )}
    </div>
  )
}
