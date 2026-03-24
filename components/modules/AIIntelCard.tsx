'use client'

import { useEffect, useState } from 'react'

interface AIItem {
  id: number
  date: string
  source: string
  title: string
  url: string
  summary: string
  tags: string[]
}

const SOURCE_LABELS: Record<string, string> = {
  arxiv: 'arXiv',
  huggingface: 'HuggingFace',
  github: 'GitHub',
  funding: 'AI Funding',
  producthunt: 'Product Hunt',
}

const SOURCE_COLORS: Record<string, string> = {
  arxiv: 'text-blue-400 bg-blue-400/10',
  huggingface: 'text-yellow-400 bg-yellow-400/10',
  github: 'text-purple-400 bg-purple-400/10',
  funding: 'text-green-400 bg-green-400/10',
  producthunt: 'text-orange-400 bg-orange-400/10',
}

export default function AIIntelCard() {
  const [data, setData] = useState<AIItem[]>([])
  const [loading, setLoading] = useState(true)
  const [activeSource, setActiveSource] = useState<string>('all')

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
  const sources = ['all', 'arxiv', 'huggingface', 'github', 'funding', 'producthunt']

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-2xl">🧠</span>
        <h2 className="text-white font-semibold text-lg">AI 情报</h2>
        <span className="ml-auto text-gray-500 text-xs">{data.length} 条</span>
      </div>

      {/* Source filter tabs */}
      <div className="flex gap-2 mb-4 flex-wrap">
        {sources.map((s) => (
          <button
            key={s}
            onClick={() => setActiveSource(s)}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              activeSource === s
                ? 'bg-blue-600 text-white'
                : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
            }`}
          >
            {s === 'all' ? '全部' : SOURCE_LABELS[s]}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => <div key={i} className="h-16 bg-gray-800 rounded-lg animate-pulse" />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-8 text-gray-500 text-sm">暂无数据，请运行 ai_intelligence.py</div>
      ) : (
        <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
          {filtered.map((item) => (
            <div key={item.id} className="bg-gray-800 rounded-lg p-3 hover:bg-gray-750 transition-colors">
              <div className="flex items-start justify-between gap-2 mb-1">
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${SOURCE_COLORS[item.source]}`}>
                  {SOURCE_LABELS[item.source]}
                </span>
                <span className="text-gray-600 text-xs shrink-0">{item.date}</span>
              </div>
              {item.url ? (
                <a href={item.url} target="_blank" rel="noopener noreferrer"
                  className="text-white text-sm font-medium hover:text-blue-400 transition-colors line-clamp-2 block mb-1">
                  {item.title}
                </a>
              ) : (
                <p className="text-white text-sm font-medium line-clamp-2 mb-1">{item.title}</p>
              )}
              {item.summary && (
                <p className="text-gray-400 text-xs line-clamp-2">{item.summary}</p>
              )}
              {item.tags?.length > 0 && (
                <div className="flex gap-1 mt-2 flex-wrap">
                  {item.tags.slice(0, 3).map((tag) => (
                    <span key={tag} className="text-xs text-gray-500 bg-gray-700 px-2 py-0.5 rounded">
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
