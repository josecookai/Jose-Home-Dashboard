'use client'

import { useState, useCallback } from 'react'
import BitcoinETFCard from '@/components/modules/BitcoinETFCard'
import AIIntelCard from '@/components/modules/AIIntelCard'
import StravaCard from '@/components/modules/StravaCard'
import LeapsCard from '@/components/modules/LeapsCard'
import AlphaBriefCard from '@/components/modules/AlphaBriefCard'
import IranRiskCard from '@/components/modules/IranRiskCard'
import ClawHubCard from '@/components/modules/ClawHubCard'
import ModuleStatus from '@/components/modules/ModuleStatus'

export default function DashboardGrid() {
  const [refreshKey, setRefreshKey] = useState(0)
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const handleRefresh = useCallback(() => {
    setRefreshing(true)
    setRefreshKey((k) => k + 1)
    setLastRefreshed(new Date())
    setTimeout(() => setRefreshing(false), 800)
  }, [])

  const refreshedLabel = lastRefreshed
    ? lastRefreshed.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    : null

  return (
    <>
      {/* Module status bar + refresh */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex-1">
          <ModuleStatus key={`status-${refreshKey}`} />
        </div>
        <div className="flex items-center gap-2 shrink-0 mb-5">
          {refreshedLabel && (
            <span className="text-xs text-gray-600">已刷新 {refreshedLabel}</span>
          )}
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 disabled:opacity-50 px-3 py-1.5 rounded-full transition-colors"
            aria-label="Refresh dashboard"
          >
            <span className={refreshing ? 'animate-spin inline-block' : ''}>↻</span>
            刷新
          </button>
        </div>
      </div>

      {/* Main grid — remounts all cards on refresh */}
      <div key={refreshKey} className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <BitcoinETFCard />
        <AIIntelCard />
        <StravaCard />
        <LeapsCard />
        <AlphaBriefCard />
        <IranRiskCard />
        <ClawHubCard />
      </div>
    </>
  )
}
