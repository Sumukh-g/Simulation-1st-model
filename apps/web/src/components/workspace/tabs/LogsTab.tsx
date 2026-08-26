'use client';

import { cn } from '@/lib/utils';
import { useAppStore } from '@/store';
import type { PipelineStage, Run } from '@/types';
import {
    Brain,
    ChevronDown,
    ChevronRight,
    Cpu,
    Search,
    Terminal,
    Users
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

type LogCategory = 'orchestrator' | 'simulation' | 'optimizer' | 'moe';

interface LogEntry {
  id: string;
  timestamp: string;
  category: LogCategory;
  level: 'info' | 'warning' | 'error' | 'debug';
  message: string;
  details?: Record<string, unknown>;
}

const STAGE_CATEGORY: Record<PipelineStage, LogCategory> = {
  formalize: 'orchestrator',
  evidence: 'orchestrator',
  scenarios: 'simulation',
  simulation: 'simulation',
  optimize: 'optimizer',
  robustness: 'optimizer',
  judge: 'moe',
  report: 'orchestrator',
};

// Derive a truthful activity feed from the live run state. These are real,
// store-backed events (stage transitions, counters, best-so-far, AI summary),
// not fabricated log lines.
function buildActivity(run: Run | null): LogEntry[] {
  if (!run) return [];
  const ts = run.updated_at || run.created_at || new Date().toISOString();
  const entries: LogEntry[] = [];

  run.stages.forEach((stage) => {
    if (stage.status === 'pending') return; // not started yet
    entries.push({
      id: `stage-${stage.stage}`,
      timestamp: ts,
      category: STAGE_CATEGORY[stage.stage] ?? 'orchestrator',
      level: stage.status === 'failed' ? 'error' : 'info',
      message:
        `Stage "${stage.stage}" ${stage.status}` +
        (stage.message ? `: ${stage.message}` : ''),
      details:
        stage.progress != null ? { progress: stage.progress } : undefined,
    });
  });

  const c = run.counters;
  if (c) {
    entries.push({
      id: 'counters',
      timestamp: ts,
      category: 'simulation',
      level: 'info',
      message: `Scenarios — proposed ${c.scenarios_proposed}, simulated ${c.scenarios_simulated}, promoted ${c.scenarios_promoted}, cache hits ${c.cache_hits}`,
      details: c as unknown as Record<string, unknown>,
    });
  }

  if (run.current_best?.judge_score) {
    entries.push({
      id: 'best',
      timestamp: ts,
      category: 'optimizer',
      level: 'info',
      message: `Current best scenario ${run.current_best.id} — score ${run.current_best.judge_score.score.toFixed(3)}`,
    });
  }

  if (run.narrative?.text) {
    entries.push({
      id: 'narrative',
      timestamp: ts,
      category: 'moe',
      level: 'info',
      message: `AI summary generated (${run.narrative.generated_by})`,
      details: { summary: run.narrative.text },
    });
  }

  return entries;
}

export function LogsTab() {
  const { currentRun } = useAppStore();
  const [filter, setFilter] = useState<LogCategory | 'all'>('all');
  const [search, setSearch] = useState('');
  const [expandedLog, setExpandedLog] = useState<string | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const logContainerRef = useRef<HTMLDivElement>(null);

  const logs = useMemo(() => buildActivity(currentRun), [currentRun]);

  const filteredLogs = useMemo(
    () =>
      logs.filter((log) => {
        if (filter !== 'all' && log.category !== filter) return false;
        if (search && !log.message.toLowerCase().includes(search.toLowerCase())) return false;
        return true;
      }),
    [logs, filter, search]
  );

  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [filteredLogs, autoScroll]);

  const categoryIcons: Record<LogCategory, React.ReactNode> = {
    orchestrator: <Terminal className="w-4 h-4" />,
    simulation: <Cpu className="w-4 h-4" />,
    optimizer: <Brain className="w-4 h-4" />,
    moe: <Users className="w-4 h-4" />,
  };

  const categoryColors: Record<LogCategory, string> = {
    orchestrator: 'text-blue-600 bg-blue-100',
    simulation: 'text-green-600 bg-green-100',
    optimizer: 'text-purple-600 bg-purple-100',
    moe: 'text-orange-600 bg-orange-100',
  };

  const levelColors: Record<string, string> = {
    info: 'text-gray-600',
    warning: 'text-yellow-600',
    error: 'text-red-600',
    debug: 'text-gray-400',
  };

  return (
    <div className="flex-1 overflow-hidden flex flex-col">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3 p-4 border-b border-gray-200 bg-white">
        {/* Category Filter */}
        <div className="flex items-center gap-1">
          <button
            onClick={() => setFilter('all')}
            className={cn(
              'px-3 py-1.5 text-xs font-medium rounded-lg transition-colors',
              filter === 'all' ? 'bg-gray-800 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            )}
          >
            All
          </button>
          {(['orchestrator', 'simulation', 'optimizer', 'moe'] as LogCategory[]).map((cat) => (
            <button
              key={cat}
              onClick={() => setFilter(cat)}
              className={cn(
                'px-3 py-1.5 text-xs font-medium rounded-lg transition-colors flex items-center gap-1',
                filter === cat ? 'bg-gray-800 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              )}
            >
              {categoryIcons[cat]}
              {cat.charAt(0).toUpperCase() + cat.slice(1)}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="flex-1 min-w-[160px] relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search activity..."
            aria-label="Search activity"
            className="input pl-9"
          />
        </div>

        <label className="flex items-center gap-2 text-sm text-gray-600">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
            className="rounded border-gray-300"
          />
          Auto-scroll
        </label>
      </div>

      {/* Log Entries */}
      <div
        ref={logContainerRef}
        className="flex-1 overflow-y-auto p-4 bg-gray-900 font-mono text-sm"
      >
        {!currentRun ? (
          <div className="text-gray-400 text-center py-12">
            <Terminal className="w-8 h-8 mx-auto mb-3 opacity-40" />
            <p>No activity yet.</p>
            <p className="text-gray-500 text-xs mt-1">
              Start a simulation from the chat below to see live pipeline activity here.
            </p>
          </div>
        ) : filteredLogs.length === 0 ? (
          <div className="text-gray-500 text-center py-8">
            {logs.length === 0
              ? 'Waiting for the pipeline to report its first activity…'
              : 'No activity matches your filters.'}
          </div>
        ) : (
          <div className="space-y-1">
            {filteredLogs.map((log) => (
              <div key={log.id} className="group">
                <button
                  onClick={() => setExpandedLog(expandedLog === log.id ? null : log.id)}
                  className="w-full text-left flex items-start gap-2 hover:bg-gray-800 px-2 py-1 rounded"
                >
                  {/* Timestamp */}
                  <span className="text-gray-500 flex-shrink-0">
                    {new Date(log.timestamp).toLocaleTimeString()}
                  </span>

                  {/* Category Badge */}
                  <span className={cn(
                    'px-1.5 py-0.5 rounded text-xs flex-shrink-0 flex items-center gap-1',
                    categoryColors[log.category]
                  )}>
                    {categoryIcons[log.category]}
                    {log.category}
                  </span>

                  {/* Level */}
                  <span className={cn('flex-shrink-0 uppercase text-xs', levelColors[log.level])}>
                    [{log.level}]
                  </span>

                  {/* Message */}
                  <span className="text-gray-100 flex-1 break-words">
                    {log.message}
                  </span>

                  {/* Expand indicator */}
                  {log.details && (
                    <span className="text-gray-500 opacity-0 group-hover:opacity-100">
                      {expandedLog === log.id ? (
                        <ChevronDown className="w-4 h-4" />
                      ) : (
                        <ChevronRight className="w-4 h-4" />
                      )}
                    </span>
                  )}
                </button>

                {/* Expanded Details */}
                {expandedLog === log.id && log.details && (
                  <div className="ml-4 mt-1 p-2 bg-gray-800 rounded text-gray-300 text-xs">
                    <pre className="whitespace-pre-wrap break-words">{JSON.stringify(log.details, null, 2)}</pre>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
