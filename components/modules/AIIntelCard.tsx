'use client'

import { useEffect, useState } from 'react'
import { useState as useTabState } from 'react'

interface AIItem {
  id: number
  date: string
  source: 'arxiv' | 'huggingface' | 'github'
  title: string
  url: string
  summary: string
  tags: string[]
}

const SOURCE_LABELS: Record<string, string> = {
  arxiv: 'arXiv',
  huggingface: 'HuggingFace',
  github: 'GitHub',
}

const SOURCE_COLORS: Record<string, string> = {
  arxiv: 'text-blue-400 bg-blue-400/10',
  huggingface: 'text-yellow-400 bg-yellow-400/10',
  github: 'text-purple-400 bg-purple-400/10',
}

export default function AIIntelCard() {
  const [data, setData] = useState<AIItem[]>([])
  const [loading, setLoading] = useState(true)
  const [activeSource, setActiveSource] = useTabState<string>('all')

  useEffect(() => {
    fetch('/api/ai-intel?limit=30')
      .then((r) => r.json())
      .then((d) => {
        setData(Array.isArray(d) ? d : [])
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const filtered = activeSource === 'all' ? data : data.filter((d) => d.source === activeSource)
  const sources = ['all', 'arxiv', 'huggingface', 'github']

  return (
    <div className="glass-panel rounded-[24px] p-5 sm:p-6">
      <div className="mb-4 flex items-center gap-2">
        <span className="text-2xl">🧠</span>
        <div>
          <h2 className="text-lg font-semibold text-white">AI 情报</h2>
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Signal radar</p>
        </div>
        <span className="ml-auto rounded-full bg-white/5 px-3 py-1 text-xs text-slate-400">{data.length} 条</span>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {sources.map((s) => (
          <button
            key={s}
            onClick={() => setActiveSource(s)}
            className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
              activeSource === s
                ? 'bg-sky-400 text-slate-950'
                : 'bg-white/5 text-slate-400 hover:bg-white/10'
            }`}
          >
            {s === 'all' ? '全部' : SOURCE_LABELS[s]}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => <div key={i} className="h-16 animate-pulse rounded-2xl bg-white/8" />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="py-8 text-center text-sm text-slate-500">暂无数据，请运行 ai_intelligence.py</div>
      ) : (
        <div className="soft-scroll max-h-80 space-y-3 overflow-y-auto pr-1">
          {filtered.map((item) => (
            <div key={item.id} className="rounded-2xl border border-white/8 bg-white/4 p-3 transition-colors hover:bg-white/7">
              <div className="mb-1 flex items-start justify-between gap-2">
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${SOURCE_COLORS[item.source]}`}>
                  {SOURCE_LABELS[item.source]}
                </span>
                <span className="shrink-0 text-xs text-slate-600">{item.date}</span>
              </div>
              {item.url ? (
                <a href={item.url} target="_blank" rel="noopener noreferrer"
                  className="mb-1 block text-sm font-medium text-white transition-colors hover:text-sky-300 line-clamp-2">
                  {item.title}
                </a>
              ) : (
                <p className="text-white text-sm font-medium line-clamp-2 mb-1">{item.title}</p>
              )}
              {item.summary && (
                <p className="line-clamp-2 text-xs text-slate-400">{item.summary}</p>
              )}
              {item.tags?.length > 0 && (
                <div className="flex gap-1 mt-2 flex-wrap">
                  {item.tags.slice(0, 3).map((tag) => (
                    <span key={tag} className="rounded-full bg-slate-900/60 px-2 py-0.5 text-xs text-slate-500">
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
