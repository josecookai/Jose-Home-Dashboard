export const dynamic = 'force-dynamic'

import DashboardGrid from '@/components/DashboardGrid'

export default function DashboardPage() {
  const today = new Date().toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  })

  return (
    <main className="min-h-screen bg-gray-950 text-white">
      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-3xl font-bold text-white">🏠 Jose&apos;s Dashboard</h1>
            <p className="text-gray-400 mt-1">{today}</p>
          </div>
          <span className="text-xs text-gray-500 bg-gray-800 px-3 py-1.5 rounded-full">
            数据每日自动更新
          </span>
        </div>

        <DashboardGrid />

        <div className="mt-8 text-center text-gray-600 text-xs">
          Jose Home Dashboard · Next.js + Supabase
        </div>
      </div>
    </main>
  )
}
