'use client';

import { useEffect, useState } from 'react';

interface ModuleStatusRow {
  id: string;
  module_name: string;
  schedule: string;
  status: 'success' | 'error' | 'pending' | string;
  last_run_at: string | null;
  last_message: string | null;
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

function statusDot(status: string) {
  if (status === 'success') return 'bg-green-500';
  if (status === 'error') return 'bg-red-500';
  return 'bg-gray-600';
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
      .catch(() => setLoaded(true));
  }, []);

  if (!loaded) return null;

  return (
    <div className="w-full bg-gray-900 rounded-xl border border-gray-800 px-4 py-3 mb-5">
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
        Cron Jobs
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2">
        {modules.map((mod) => (
          <div
            key={mod.id}
            title={mod.last_message ?? mod.module_name}
            className="flex items-center gap-1.5 rounded-lg bg-gray-800 px-2.5 py-1.5 text-xs"
          >
            <span
              className={`h-2 w-2 shrink-0 rounded-full ${statusDot(mod.status)}`}
              aria-label={mod.status}
            />
            <div className="min-w-0">
              <p className="truncate font-medium text-gray-100">{mod.module_name}</p>
              <p className="text-gray-500">{mod.schedule} · {formatRelativeTime(mod.last_run_at)}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
