'use client';

import { cn, formatNumber, formatPercentage, getGradeColor } from '@/lib/utils';
import { useAppStore } from '@/store';
import type { StageStatus } from '@/types';
import {
    AlertCircle,
    Award,
    CheckCircle,
    Clock,
    Database,
    Loader2,
    TrendingUp,
    Zap
} from 'lucide-react';

const PIPELINE_STAGES = [
  { id: 'formalize', label: 'Formalize' },
  { id: 'evidence', label: 'Evidence' },
  { id: 'scenarios', label: 'Scenarios' },
  { id: 'simulation', label: 'Simulation' },
  { id: 'optimize', label: 'Optimize' },
  { id: 'robustness', label: 'Robustness' },
  { id: 'judge', label: 'Judge' },
  { id: 'report', label: 'Report' },
];

export function OverviewTab() {
  const { currentRun, setActiveTab, setSelectedScenario } = useAppStore();

  if (!currentRun) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center text-gray-500">
          <p>No active run. Start a simulation from the chat.</p>
        </div>
      </div>
    );
  }

  const { stages, counters, current_best, candidates } = currentRun;
  const budgetPercent = counters.budget_total > 0 
    ? counters.budget_consumed / counters.budget_total 
    : 0;

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      {/* Pipeline Timeline */}
      <div className="card p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Pipeline Progress</h3>
        <div className="flex items-center gap-1">
          {PIPELINE_STAGES.map((stage, index) => {
            const stageStatus = stages?.find((s) => s.stage === stage.id);
            return (
              <div key={stage.id} className="flex-1 flex items-center">
                <StageIndicator 
                  label={stage.label} 
                  status={stageStatus?.status || 'pending'} 
                  progress={stageStatus?.progress}
                />
                {index < PIPELINE_STAGES.length - 1 && (
                  <div className={cn(
                    'flex-1 h-0.5 mx-1',
                    stageStatus?.status === 'completed' ? 'bg-green-400' : 'bg-gray-200'
                  )} />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Live Counters */}
      <div className="grid grid-cols-4 gap-4">
        <CounterCard
          icon={<Zap className="w-5 h-5 text-yellow-500" />}
          label="Scenarios"
          value={`${counters.scenarios_simulated} / ${counters.scenarios_proposed}`}
          sublabel={`${counters.scenarios_promoted} promoted`}
        />
        <CounterCard
          icon={<Database className="w-5 h-5 text-blue-500" />}
          label="Cache Hits"
          value={counters.cache_hits.toString()}
          sublabel={`${formatPercentage(counters.cache_hits / Math.max(counters.scenarios_simulated, 1))} hit rate`}
        />
        <CounterCard
          icon={<TrendingUp className="w-5 h-5 text-green-500" />}
          label="Compute Cost"
          value={`$${formatNumber(counters.compute_cost)}`}
          sublabel={`Storage: $${formatNumber(counters.storage_cost)}`}
        />
        <CounterCard
          icon={<Clock className="w-5 h-5 text-purple-500" />}
          label="Budget Used"
          value={formatPercentage(budgetPercent)}
          progress={budgetPercent}
        />
      </div>

      {/* Current Best Card */}
      {current_best && (
        <div className="card p-4">
          <div className="flex items-start justify-between">
            <div>
              <h3 className="text-sm font-semibold text-gray-700 mb-1 flex items-center gap-2">
                <Award className="w-4 h-4 text-yellow-500" />
                Current Best
              </h3>
              <p className="text-xs text-gray-500 font-mono">{current_best.id}</p>
            </div>
            <div className={cn(
              'px-3 py-1.5 rounded-lg font-semibold text-sm',
              getGradeColor(current_best.judge_score?.level || 'good')
            )}>
              {current_best.judge_score?.level?.replace('_', ' ').toUpperCase() || 'N/A'}
            </div>
          </div>

          <div className="mt-4 grid grid-cols-3 gap-4">
            <div>
              <p className="text-xs text-gray-500">Judge Score</p>
              <p className="text-lg font-bold text-gray-900">
                {formatNumber(current_best.judge_score?.score || 0, 3)}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Confidence</p>
              <p className="text-lg font-bold text-gray-900">
                {formatPercentage(current_best.confidence)}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-500">vs Baseline</p>
              <p className="text-lg font-bold text-green-600">
                +{formatPercentage(0.15)} {/* Placeholder delta */}
              </p>
            </div>
          </div>

          <button
            onClick={() => {
              setSelectedScenario(current_best);
              setActiveTab('detail');
            }}
            className="mt-3 text-sm text-primary-600 hover:text-primary-700 font-medium"
          >
            View Details →
          </button>
        </div>
      )}

      {/* Top 5 Candidates */}
      <div className="card p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Top Candidates</h3>
        
        {candidates.length === 0 ? (
          <p className="text-sm text-gray-500">No candidates yet</p>
        ) : (
          <div className="space-y-2">
            {candidates.slice(0, 5).map((candidate, index) => (
              <button
                key={candidate.id}
                onClick={() => {
                  setSelectedScenario(candidate);
                  setActiveTab('detail');
                }}
                className="w-full flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 text-left"
              >
                <span className="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center text-xs font-bold text-gray-600">
                  {index + 1}
                </span>
                <span className="flex-1 text-sm font-mono text-gray-700 truncate">
                  {candidate.id}
                </span>
                <span className={cn(
                  'px-2 py-0.5 rounded text-xs font-medium',
                  getGradeColor(candidate.judge_score?.level || 'acceptable')
                )}>
                  {formatNumber(candidate.judge_score?.score || 0, 2)}
                </span>
                <span className="text-xs text-gray-500">
                  {formatPercentage(candidate.confidence)}
                </span>
              </button>
            ))}
          </div>
        )}

        {candidates.length > 5 && (
          <button
            onClick={() => setActiveTab('leaderboard')}
            className="mt-3 text-sm text-primary-600 hover:text-primary-700 font-medium"
          >
            View All ({candidates.length}) →
          </button>
        )}
      </div>
    </div>
  );
}

function StageIndicator({ label, status, progress }: { 
  label: string; 
  status: StageStatus['status']; 
  progress?: number;
}) {
  const icons = {
    pending: <div className="w-3 h-3 rounded-full bg-gray-300" />,
    running: <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />,
    completed: <CheckCircle className="w-4 h-4 text-green-500" />,
    failed: <AlertCircle className="w-4 h-4 text-red-500" />,
  };

  return (
    <div className="flex flex-col items-center gap-1">
      {icons[status]}
      <span className={cn(
        'text-xs',
        status === 'running' ? 'text-blue-600 font-medium' : 'text-gray-500'
      )}>
        {label}
      </span>
      {status === 'running' && progress !== undefined && (
        <span className="text-xs text-blue-500">{Math.round(progress * 100)}%</span>
      )}
    </div>
  );
}

function CounterCard({ icon, label, value, sublabel, progress }: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sublabel?: string;
  progress?: number;
}) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-sm font-medium text-gray-600">{label}</span>
      </div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      {sublabel && <p className="text-xs text-gray-500 mt-1">{sublabel}</p>}
      {progress !== undefined && (
        <div className="mt-2 h-1.5 bg-gray-100 rounded-full overflow-hidden">
          <div 
            className="h-full bg-primary-500 transition-all"
            style={{ width: `${Math.min(progress * 100, 100)}%` }}
          />
        </div>
      )}
    </div>
  );
}
