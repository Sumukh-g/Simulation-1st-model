'use client';

import { cn } from '@/lib/utils';
import { useAppStore } from '@/store';
import {
    Brain,
    ChevronDown,
    ChevronRight,
    Cpu,
    RefreshCw,
    Search,
    Terminal,
    Users
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

type LogCategory = 'orchestrator' | 'simulation' | 'optimizer' | 'moe';

interface LogEntry {
  id: string;
  timestamp: string;
  category: LogCategory;
  level: 'info' | 'warning' | 'error' | 'debug';
  message: string;
  details?: Record<string, unknown>;
}

// Mock log data for demonstration
const mockLogs: LogEntry[] = [
  { id: '1', timestamp: new Date().toISOString(), category: 'orchestrator', level: 'info', message: 'Starting simulation run', details: { run_id: 'run-001' } },
  { id: '2', timestamp: new Date().toISOString(), category: 'orchestrator', level: 'info', message: 'Formalizing objectives from prompt' },
  { id: '3', timestamp: new Date().toISOString(), category: 'moe', level: 'info', message: 'Routing to experts: Planner, EvidenceCurator', details: { experts: ['Planner', 'EvidenceCurator'] } },
  { id: '4', timestamp: new Date().toISOString(), category: 'moe', level: 'debug', message: 'Planner returned with confidence 0.85' },
  { id: '5', timestamp: new Date().toISOString(), category: 'simulation', level: 'info', message: 'Submitting batch of 10 scenarios at cheap fidelity' },
  { id: '6', timestamp: new Date().toISOString(), category: 'simulation', level: 'info', message: 'Batch complete: 10/10 succeeded' },
  { id: '7', timestamp: new Date().toISOString(), category: 'optimizer', level: 'info', message: 'Updating optimizer with new results', details: { n_results: 10 } },
  { id: '8', timestamp: new Date().toISOString(), category: 'optimizer', level: 'debug', message: 'Proposing next batch via Bayesian acquisition' },
];

export function LogsTab() {
  const { currentRun } = useAppStore();
  const [logs, setLogs] = useState<LogEntry[]>(mockLogs);
  const [filter, setFilter] = useState<LogCategory | 'all'>('all');
  const [search, setSearch] = useState('');
  const [expandedLog, setExpandedLog] = useState<string | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const logContainerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const filteredLogs = logs.filter(log => {
    if (filter !== 'all' && log.category !== filter) return false;
    if (search && !log.message.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

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

  const handleRefresh = async () => {
    // Would fetch latest logs here
    setLogs([...mockLogs, {
      id: Date.now().toString(),
      timestamp: new Date().toISOString(),
      category: 'orchestrator',
      level: 'info',
      message: 'Logs refreshed',
    }]);
  };

  return (
    <div className="flex-1 overflow-hidden flex flex-col">
      {/* Toolbar */}
      <div className="flex items-center gap-4 p-4 border-b border-gray-200 bg-white">
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
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search logs..."
            className="input pl-9"
          />
        </div>

        {/* Controls */}
        <button
          onClick={handleRefresh}
          className="btn-secondary gap-2"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
        
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
        {filteredLogs.length === 0 ? (
          <div className="text-gray-500 text-center py-8">
            No logs to display
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
                  <span className="text-gray-100 flex-1">
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
                    <pre>{JSON.stringify(log.details, null, 2)}</pre>
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
