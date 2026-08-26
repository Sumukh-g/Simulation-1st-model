'use client';

import { cn, getStatusColor } from '@/lib/utils';
import { messagesFromRun, useAppStore } from '@/store';
import type { Run, RunListItem } from '@/types';
import {
  History,
  Loader2,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Plus,
  Trash2,
} from 'lucide-react';
import { useCallback, useState } from 'react';

function formatRelative(iso: string): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return '';
  const diff = Date.now() - t;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

const MODE_SHORT: Record<string, string> = {
  domain_pack: 'Pack',
  create_pack: 'Create pack',
  no_pack: 'No pack',
};

export async function refreshRunHistory(): Promise<void> {
  const { selectedProject, setRunHistory, setHistoryLoading } = useAppStore.getState();
  setHistoryLoading(true);
  try {
    const params = new URLSearchParams({ limit: '100' });
    if (selectedProject?.id) {
      params.set('project_id', selectedProject.id);
    }
    const res = await fetch(`/api/runs?${params}`);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    setRunHistory((data.runs || []) as RunListItem[]);
  } catch (err) {
    console.error('Failed to load run history:', err);
  } finally {
    setHistoryLoading(false);
  }
}

export function RunHistorySidebar() {
  const {
    historyOpen,
    setHistoryOpen,
    runHistory,
    historyLoading,
    currentRun,
    startNewChat,
    setCurrentRun,
    setMessages,
    setActiveTab,
  } = useAppStore();

  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [busyId, setBusyId] = useState<string | null>(null);

  const openRun = useCallback(
    async (item: RunListItem) => {
      if (busyId) return;
      setBusyId(item.id);
      try {
        const res = await fetch(`/api/runs/${item.id}`);
        if (!res.ok) throw new Error(await res.text());
        const run = (await res.json()) as Run;
        setCurrentRun(run);
        setMessages(messagesFromRun(run));
        setActiveTab('overview');
      } catch (err) {
        console.error('Failed to open run:', err);
      } finally {
        setBusyId(null);
      }
    },
    [busyId, setCurrentRun, setMessages, setActiveTab]
  );

  const archiveRun = useCallback(
    async (item: RunListItem, e: React.MouseEvent) => {
      e.stopPropagation();
      if (!confirm(`Remove "${item.title}" from history?`)) return;
      setBusyId(item.id);
      try {
        const res = await fetch(`/api/runs/${item.id}`, { method: 'DELETE' });
        if (!res.ok && res.status !== 204) throw new Error(await res.text());
        if (currentRun?.id === item.id) {
          startNewChat();
        }
        await refreshRunHistory();
      } catch (err) {
        console.error('Failed to delete run:', err);
      } finally {
        setBusyId(null);
      }
    },
    [currentRun?.id, startNewChat]
  );

  const saveRename = useCallback(
    async (id: string) => {
      const title = renameValue.trim();
      if (!title) {
        setRenamingId(null);
        return;
      }
      setBusyId(id);
      try {
        const res = await fetch(`/api/runs/${id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title }),
        });
        if (!res.ok) throw new Error(await res.text());
        setRenamingId(null);
        await refreshRunHistory();
        if (currentRun?.id === id) {
          setCurrentRun({ ...currentRun, title });
        }
      } catch (err) {
        console.error('Failed to rename run:', err);
      } finally {
        setBusyId(null);
      }
    },
    [renameValue, currentRun, setCurrentRun]
  );

  if (!historyOpen) {
    return (
      <div className="w-12 shrink-0 border-r border-gray-200 bg-gray-50 flex flex-col items-center py-3 gap-2">
        <button
          type="button"
          onClick={() => setHistoryOpen(true)}
          className="p-2 rounded-lg text-gray-500 hover:bg-gray-200 hover:text-gray-800"
          title="Show run history"
          aria-label="Show run history"
        >
          <PanelLeftOpen className="w-5 h-5" />
        </button>
        <button
          type="button"
          onClick={() => startNewChat()}
          className="p-2 rounded-lg text-gray-500 hover:bg-gray-200 hover:text-gray-800"
          title="New chat"
          aria-label="New chat"
        >
          <Plus className="w-5 h-5" />
        </button>
      </div>
    );
  }

  return (
    <aside className="w-72 shrink-0 border-r border-gray-200 bg-gray-50 flex flex-col h-full">
      <div className="h-14 px-3 flex items-center gap-2 border-b border-gray-200 bg-white">
        <History className="w-4 h-4 text-gray-500" />
        <span className="text-sm font-semibold text-gray-800 flex-1">Past runs</span>
        <button
          type="button"
          onClick={() => setHistoryOpen(false)}
          className="p-1.5 rounded-md text-gray-400 hover:bg-gray-100 hover:text-gray-700"
          title="Collapse sidebar"
          aria-label="Collapse sidebar"
        >
          <PanelLeftClose className="w-4 h-4" />
        </button>
      </div>

      <div className="p-2 border-b border-gray-200">
        <button
          type="button"
          onClick={() => startNewChat()}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium rounded-lg bg-white border border-gray-200 text-gray-700 hover:bg-gray-100"
        >
          <Plus className="w-4 h-4" />
          New chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin p-2 space-y-1">
        {historyLoading && runHistory.length === 0 ? (
          <div className="flex items-center justify-center py-8 text-gray-400 gap-2 text-sm">
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading…
          </div>
        ) : runHistory.length === 0 ? (
          <p className="px-2 py-6 text-center text-sm text-gray-500">
            No past runs yet. Send a goal below to create one — it will show up here.
          </p>
        ) : (
          runHistory.map((item) => {
            const active = currentRun?.id === item.id;
            const busy = busyId === item.id;
            return (
              <div
                key={item.id}
                role="button"
                tabIndex={0}
                onClick={() => openRun(item)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    openRun(item);
                  }
                }}
                className={cn(
                  'group relative w-full text-left rounded-lg px-2.5 py-2 border transition-colors cursor-pointer',
                  active
                    ? 'bg-primary-50 border-primary-200'
                    : 'bg-white border-transparent hover:border-gray-200 hover:bg-white'
                )}
              >
                {renamingId === item.id ? (
                  <input
                    autoFocus
                    value={renameValue}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onBlur={() => saveRename(item.id)}
                    onKeyDown={(e) => {
                      e.stopPropagation();
                      if (e.key === 'Enter') saveRename(item.id);
                      if (e.key === 'Escape') setRenamingId(null);
                    }}
                    className="w-full text-sm border border-primary-300 rounded px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-primary-500"
                  />
                ) : (
                  <div className="pr-14">
                    <div className="text-sm font-medium text-gray-900 line-clamp-2 leading-snug">
                      {item.title}
                    </div>
                    <div className="mt-1 flex items-center gap-1.5 text-[11px] text-gray-500">
                      <span className={cn('font-medium capitalize', getStatusColor(item.status))}>
                        {item.status.replace('_', ' ')}
                      </span>
                      <span>·</span>
                      <span>
                        {item.domain_pack ||
                          MODE_SHORT[item.simulation_mode || ''] ||
                          'run'}
                      </span>
                      <span>·</span>
                      <span>{formatRelative(item.created_at)}</span>
                    </div>
                  </div>
                )}

                <div className="absolute top-2 right-1.5 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100">
                  {busy ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-gray-400 m-1" />
                  ) : (
                    <>
                      <button
                        type="button"
                        title="Rename"
                        aria-label="Rename run"
                        className="p-1 rounded text-gray-400 hover:text-gray-700 hover:bg-gray-100"
                        onClick={(e) => {
                          e.stopPropagation();
                          setRenamingId(item.id);
                          setRenameValue(item.title);
                        }}
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        title="Remove from history"
                        aria-label="Delete run"
                        className="p-1 rounded text-gray-400 hover:text-red-600 hover:bg-red-50"
                        onClick={(e) => archiveRun(item, e)}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}
