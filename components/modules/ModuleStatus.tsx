'use client';

import { useEffect, useState } from 'react';

interface ModuleStatusRow {
  id: string;
  module_name: string;
  status: 'success' | 'error' | string;
  last_run_at: string | null;
}

function formatRelativeTime(dateStr: string | null): string {
  if (!dateStr) return 'never';
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export default function ModuleStatus() {
  const [modules, setModules] = useState<ModuleStatusRow[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    fetch('/api/module-status')
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch module status');
        return res.json();
      })
      .then((data: ModuleStatusRow[]) => {
        setModules(data);
        setLoaded(true);
      })
      .catch(() => {
        setLoaded(true);
      });
  }, []);

  if (!loaded || modules.length === 0) return null;

  return (
    <div className="glass-panel rounded-[24px] p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">System health</p>
          <h2 className="mt-1 text-lg font-semibold text-white">Module status</h2>
        </div>
        <span className="rounded-full bg-white/5 px-3 py-1 text-xs text-slate-400">
          {modules.length} tracked
        </span>
      </div>
      <div className="soft-scroll flex gap-2 overflow-x-auto pb-1">
        {modules.map((mod) => (
          <div
            key={mod.id}
            className="flex shrink-0 items-center gap-2 rounded-full border border-white/8 bg-white/4 px-3 py-2 text-xs text-slate-300"
          >
            <span
              className={`h-2 w-2 rounded-full ${
                mod.status === 'success' ? 'bg-emerald-400' : 'bg-rose-400'
              }`}
              aria-label={mod.status === 'success' ? 'success' : 'error'}
            />
            <span className="font-medium text-slate-100">{mod.module_name}</span>
            <span className="text-slate-500">{formatRelativeTime(mod.last_run_at)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
