'use client';

import { cn, formatNumber, formatPercentage, getGradeColor } from '@/lib/utils';
import { useAppStore } from '@/store';
import {
    AlertTriangle,
    CheckCircle,
    ChevronDown,
    ChevronRight,
    Download,
    MinusCircle,
    XCircle
} from 'lucide-react';
import { useState } from 'react';

export function ScenarioDetailTab() {
  const { selectedScenario, currentRun, benchmarks } = useAppStore();
  const [jsonExpanded, setJsonExpanded] = useState(false);

  if (!selectedScenario) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-500">
        <div className="text-center">
          <p className="mb-2">No scenario selected</p>
          <p className="text-sm">Click a scenario in the Leaderboard or Overview to view details</p>
        </div>
      </div>
    );
  }

  const scenario = selectedScenario;

  const handleExport = () => {
    const blob = new Blob([JSON.stringify(scenario, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `scenario-${scenario.id}.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">{scenario.id}</h2>
          <p className="text-sm text-gray-500">Run: {scenario.run_id}</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={handleExport} className="btn-primary gap-2">
            <Download className="w-4 h-4" />
            Export JSON
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Scenario JSON */}
        <div className="card p-4">
          <button
            onClick={() => setJsonExpanded(!jsonExpanded)}
            className="flex items-center gap-2 text-sm font-semibold text-gray-700 mb-3 w-full"
          >
            {jsonExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            Scenario Configuration
          </button>
          
          <div className={cn(
            'font-mono text-xs bg-gray-50 rounded-lg p-3 overflow-auto',
            jsonExpanded ? 'max-h-96' : 'max-h-32'
          )}>
            <pre>{JSON.stringify({ state: scenario.state, actions: scenario.actions }, null, 2)}</pre>
          </div>
        </div>

        {/* Feasibility & Cost */}
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">Feasibility & Cost</h3>
          
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600">Fidelity Level</span>
              <span className={cn(
                'badge',
                scenario.fidelity === 'high' ? 'badge-success' :
                scenario.fidelity === 'mid' ? 'badge-info' : 'badge-warning'
              )}>
                {scenario.fidelity}
              </span>
            </div>
            
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-600">Seed</span>
              <span className="text-sm font-mono">{scenario.seed}</span>
            </div>

            {scenario.constraint_violations.length > 0 && (
              <div className="p-3 bg-red-50 rounded-lg">
                <div className="flex items-center gap-2 text-red-700 mb-2">
                  <AlertTriangle className="w-4 h-4" />
                  <span className="text-sm font-medium">Constraint Violations</span>
                </div>
                <ul className="text-sm text-red-600 space-y-1">
                  {scenario.constraint_violations.map((v, i) => (
                    <li key={i}>• {v}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Metrics & Uncertainty */}
      <div className="card p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Metrics & Uncertainty</h3>
        
        <div className="grid grid-cols-3 gap-4">
          {scenario.metrics.map((metric) => (
            <div key={metric.name} className="p-3 bg-gray-50 rounded-lg">
              <p className="text-xs text-gray-500 mb-1">{metric.name}</p>
              <p className="text-lg font-bold text-gray-900">
                {formatNumber(metric.value)} {metric.unit}
              </p>
              {metric.uncertainty && (
                <div className="mt-2 text-xs text-gray-500">
                  <div className="flex justify-between">
                    <span>P10</span>
                    <span className="font-mono">{formatNumber(metric.uncertainty.p10)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>P50</span>
                    <span className="font-mono">{formatNumber(metric.uncertainty.p50)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>P90</span>
                    <span className="font-mono">{formatNumber(metric.uncertainty.p90)}</span>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Robustness Tests */}
      {scenario.robustness_total !== undefined && (
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">Robustness Tests</h3>
          
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <CheckCircle className="w-5 h-5 text-green-500" />
              <span className="text-sm">
                <span className="font-bold">{scenario.robustness_passed || 0}</span> passed
              </span>
            </div>
            <div className="flex items-center gap-2">
              <XCircle className="w-5 h-5 text-red-500" />
              <span className="text-sm">
                <span className="font-bold">{(scenario.robustness_total || 0) - (scenario.robustness_passed || 0)}</span> failed
              </span>
            </div>
            <div className="flex-1" />
            <span className="text-sm text-gray-500">
              {formatPercentage((scenario.robustness_passed || 0) / Math.max(scenario.robustness_total || 1, 1))} pass rate
            </span>
          </div>
        </div>
      )}

      {/* Judge Score Breakdown */}
      {scenario.judge_score && (
        <div className="card p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-700">Judge Score</h3>
            <span className={cn(
              'px-3 py-1 rounded-lg font-semibold text-sm',
              getGradeColor(scenario.judge_score.level)
            )}>
              {scenario.judge_score.level.replace('_', ' ').toUpperCase()} - {formatNumber(scenario.judge_score.score, 3)}
            </span>
          </div>
          
          <div className="space-y-2">
            {scenario.judge_score.breakdown.map((item) => (
              <div key={item.metric_name ?? (item as { metric?: string }).metric} className="flex items-center gap-3">
                <span className="text-sm text-gray-600 w-32">
                  {item.metric_name ?? (item as { metric?: string }).metric}
                </span>
                <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-primary-500"
                    style={{ width: `${(item.threshold_score ?? 0) * 100}%` }}
                  />
                </div>
                <span className="text-sm font-mono w-16 text-right">
                  {formatNumber(item.raw_value ?? (item as { value?: number }).value)}
                </span>
                <span className="text-xs text-gray-400 w-12">
                  ×{formatNumber(item.weight ?? 1, 2)}
                </span>
              </div>
            ))}
          </div>

          <div className="mt-4 pt-4 border-t border-gray-200">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-600">Benchmarks</span>
              <span>
                <span className="font-bold text-green-600">{scenario.judge_score.benchmarks_passed}</span>
                <span className="text-gray-400"> / {scenario.judge_score.benchmarks_total} passed</span>
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Evidence & Benchmarks Used */}
      {benchmarks.length > 0 && (
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">Benchmarks Applied</h3>
          
          <div className="space-y-2">
            {benchmarks.map((benchmark) => (
              <div 
                key={benchmark.id}
                className="flex items-center justify-between p-2 rounded-lg"
              >
                <div className="flex items-center gap-2">
                  {benchmark.passed === true ? (
                    <CheckCircle className="w-4 h-4 text-green-500" />
                  ) : benchmark.passed === false ? (
                    <XCircle className="w-4 h-4 text-red-500" />
                  ) : (
                    <MinusCircle className="w-4 h-4 text-gray-400" />
                  )}
                  <span className="text-sm font-medium">{benchmark.name}</span>
                </div>
                <div className="flex items-center gap-3 text-sm text-gray-500">
                  <span>{benchmark.metric_name} {benchmark.threshold_type} {benchmark.threshold_value}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
