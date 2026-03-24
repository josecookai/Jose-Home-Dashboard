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
    <div className="w-full bg-gray-950 px-4 py-2">
      <div className="flex gap-2 overflow-x-auto scrollbar-thin scrollbar-thumb-gray-700 scrollbar-track-transparent pb-1">
        {modules.map((mod) => (
          <div
            key={mod.id}
            className="flex shrink-0 items-center gap-1.5 rounded-full bg-gray-800 px-3 py-1 text-xs text-gray-300"
          >
            <span
              className={`h-2 w-2 rounded-full ${
                mod.status === 'success' ? 'bg-green-500' : 'bg-red-500'
              }`}
              aria-label={mod.status === 'success' ? 'success' : 'error'}
            />
            <span className="font-medium text-gray-100">{mod.module_name}</span>
            <span className="text-gray-500">{formatRelativeTime(mod.last_run_at)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
