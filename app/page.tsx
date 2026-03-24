import BitcoinETFCard from '@/components/modules/BitcoinETFCard'
import AIIntelCard from '@/components/modules/AIIntelCard'
import StravaCard from '@/components/modules/StravaCard'
import LeapsCard from '@/components/modules/LeapsCard'
import ModuleStatus from '@/components/modules/ModuleStatus'
import { ArrowUpRight, BellRing, ChartNoAxesCombined, ShieldCheck, Sparkles } from 'lucide-react'

export default function DashboardPage() {
  const today = new Date().toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  })

  return (
    <main className="dashboard-grid min-h-screen text-white">
      <div className="mx-auto max-w-7xl px-4 py-5 sm:px-6 lg:px-8 lg:py-8">
        <section className="relative overflow-hidden rounded-[28px] border border-white/10 bg-transparent">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(99,179,255,0.25),transparent_32%),radial-gradient(circle_at_78%_16%,rgba(255,184,77,0.16),transparent_20%),linear-gradient(135deg,rgba(8,17,31,0.9),rgba(9,25,45,0.84))]" />
          <div className="absolute -left-24 top-8 h-52 w-52 rounded-full bg-[var(--glow-blue)] blur-3xl" />
          <div className="absolute right-0 top-0 h-56 w-56 rounded-full bg-[var(--glow-gold)] blur-3xl" />

          <div className="relative px-5 py-6 sm:px-7 sm:py-8">
            <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
              <div className="max-w-3xl">
                <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-sky-300/20 bg-sky-300/10 px-3 py-1 text-xs uppercase tracking-[0.24em] text-sky-100/80">
                  <Sparkles className="h-3.5 w-3.5" />
                  Home Command Center
                </div>
                <h1 className="max-w-2xl text-4xl font-semibold tracking-tight text-white sm:text-5xl">
                  Jose&apos;s Dashboard
                </h1>
                <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-300 sm:text-base">
                  A sharper surface for ETF flows, AI intelligence, fitness telemetry, and trade monitoring.
                  Built to feel like an active control room, not a generic admin page.
                </p>
              </div>

              <div className="glass-panel inline-flex w-full max-w-md flex-col gap-4 rounded-[24px] p-4 sm:p-5">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Today</p>
                    <p className="mt-1 text-lg font-medium text-white">{today}</p>
                  </div>
                  <span className="inline-flex items-center gap-2 rounded-full bg-emerald-400/10 px-3 py-1 text-xs text-emerald-300">
                    <span className="h-2 w-2 rounded-full bg-emerald-400" />
                    Live surface
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <HeroStat label="Modules" value="4" icon={<ChartNoAxesCombined className="h-4 w-4" />} />
                  <HeroStat label="Alerts" value="3" icon={<BellRing className="h-4 w-4" />} />
                  <HeroStat label="Uptime" value="99%" icon={<ShieldCheck className="h-4 w-4" />} />
                </div>
              </div>
            </div>

            <div className="mt-6 flex flex-wrap gap-3">
              <QuickChip label="ETF flows" tone="orange" />
              <QuickChip label="AI radar" tone="sky" />
              <QuickChip label="Strava sync" tone="emerald" />
              <QuickChip label="Congress trades" tone="violet" />
            </div>
          </div>
        </section>

        <div className="mt-5 grid gap-5 xl:grid-cols-[1.5fr_0.8fr]">
          <ModuleStatus />
          <aside className="glass-panel rounded-[24px] p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Operator Notes</p>
                <h2 className="mt-1 text-lg font-semibold text-white">Daily priorities</h2>
              </div>
              <ArrowUpRight className="h-4 w-4 text-slate-500" />
            </div>
            <div className="mt-4 space-y-3 text-sm text-slate-300">
              <NoteLine title="Market open" body="Watch ETF net flow reversals and spot intraday volume spikes." />
              <NoteLine title="AI scan" body="Surface papers or repos with unusually strong velocity, not just raw counts." />
              <NoteLine title="Risk watch" body="Keep congressional activity and LEAPS triggers visible in the same pane." />
            </div>
          </aside>
        </div>

        <div className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-2">
          <BitcoinETFCard />
          <AIIntelCard />
          <StravaCard />
          <LeapsCard />
        </div>

        <div className="mt-8 text-center text-xs text-slate-500">
          Jose Home Dashboard · Next.js + Supabase
        </div>
      </div>
    </main>
  )
}

function HeroStat({
  label,
  value,
  icon,
}: {
  label: string
  value: string
  icon: React.ReactNode
}) {
  return (
    <div className="rounded-2xl border border-white/8 bg-white/4 p-3">
      <div className="flex items-center justify-between text-slate-400">
        <span className="text-xs uppercase tracking-[0.16em]">{label}</span>
        {icon}
      </div>
      <div className="mt-3 text-2xl font-semibold text-white">{value}</div>
    </div>
  )
}

function QuickChip({ label, tone }: { label: string; tone: 'orange' | 'sky' | 'emerald' | 'violet' }) {
  const tones = {
    orange: 'border-orange-300/15 bg-orange-300/10 text-orange-100',
    sky: 'border-sky-300/15 bg-sky-300/10 text-sky-100',
    emerald: 'border-emerald-300/15 bg-emerald-300/10 text-emerald-100',
    violet: 'border-violet-300/15 bg-violet-300/10 text-violet-100',
  }

  return (
    <div className={`rounded-full border px-3 py-1.5 text-xs font-medium ${tones[tone]}`}>
      {label}
    </div>
  )
}

function NoteLine({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-2xl border border-white/8 bg-white/4 p-3">
      <p className="font-medium text-white">{title}</p>
      <p className="mt-1 text-sm leading-6 text-slate-400">{body}</p>
    </div>
  )
}
