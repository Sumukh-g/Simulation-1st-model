'use client';

import { cn, formatNumber, formatPercentage, getFidelityBadge, getGradeColor } from '@/lib/utils';
import { useAppStore } from '@/store';
import type { ScenarioResult } from '@/types';
import { AlertTriangle, ArrowUpDown, CheckCircle } from 'lucide-react';
import { useState } from 'react';

type SortKey = 'score' | 'confidence' | 'fidelity';
type SortDir = 'asc' | 'desc';

export function LeaderboardTab() {
  const { currentRun, setActiveTab, setSelectedScenario } = useAppStore();
  const [sortKey, setSortKey] = useState<SortKey>('score');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  if (!currentRun) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-500">
        No active run
      </div>
    );
  }

  const { candidates } = currentRun;

  const sortedCandidates = [...candidates].sort((a, b) => {
    let aVal: number, bVal: number;
    
    switch (sortKey) {
      case 'score':
        aVal = a.judge_score?.score || 0;
        bVal = b.judge_score?.score || 0;
        break;
      case 'confidence':
        aVal = a.confidence;
        bVal = b.confidence;
        break;
      case 'fidelity':
        const fidelityOrder = { cheap: 0, mid: 1, high: 2 };
        aVal = fidelityOrder[a.fidelity];
        bVal = fidelityOrder[b.fidelity];
        break;
      default:
        aVal = 0;
        bVal = 0;
    }

    return sortDir === 'desc' ? bVal - aVal : aVal - bVal;
  });

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === 'desc' ? 'asc' : 'desc');
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  const handleRowClick = (scenario: ScenarioResult) => {
    setSelectedScenario(scenario);
    setActiveTab('detail');
  };

  return (
    <div className="flex-1 overflow-hidden flex flex-col">
      <div className="flex-1 overflow-auto">
        <table className="w-full">
          <thead className="bg-gray-50 sticky top-0">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Rank
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Scenario ID
              </th>
              <th 
                className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-700"
                onClick={() => toggleSort('score')}
              >
                <span className="flex items-center gap-1">
                  Grade / Score
                  <ArrowUpDown className="w-3 h-3" />
                </span>
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Key Metrics
              </th>
              <th 
                className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-700"
                onClick={() => toggleSort('confidence')}
              >
                <span className="flex items-center gap-1">
                  Confidence
                  <ArrowUpDown className="w-3 h-3" />
                </span>
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Constraints
              </th>
              <th 
                className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-700"
                onClick={() => toggleSort('fidelity')}
              >
                <span className="flex items-center gap-1">
                  Fidelity
                  <ArrowUpDown className="w-3 h-3" />
                </span>
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {sortedCandidates.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                  No scenarios evaluated yet
                </td>
              </tr>
            ) : (
              sortedCandidates.map((scenario, index) => (
                <tr
                  key={scenario.id}
                  onClick={() => handleRowClick(scenario)}
                  className="hover:bg-gray-50 cursor-pointer"
                >
                  <td className="px-4 py-3">
                    <span className="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center text-xs font-bold text-gray-600">
                      {index + 1}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-mono text-sm text-gray-700">{scenario.id}</span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className={cn(
                        'px-2 py-0.5 rounded text-xs font-medium',
                        getGradeColor(scenario.judge_score?.level || 'acceptable')
                      )}>
                        {scenario.judge_score?.level?.replace('_', ' ') || 'N/A'}
                      </span>
                      <span className="text-sm font-medium text-gray-900">
                        {formatNumber(scenario.judge_score?.score || 0, 3)}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {scenario.metrics.slice(0, 3).map((metric) => (
                        <span 
                          key={metric.name}
                          className="text-xs bg-gray-100 px-1.5 py-0.5 rounded"
                          title={metric.name}
                        >
                          {metric.name.slice(0, 8)}: {formatNumber(metric.value)}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                        <div 
                          className={cn(
                            'h-full rounded-full',
                            scenario.confidence >= 0.8 ? 'bg-green-500' :
                            scenario.confidence >= 0.6 ? 'bg-yellow-500' : 'bg-red-500'
                          )}
                          style={{ width: `${scenario.confidence * 100}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-600">
                        {formatPercentage(scenario.confidence)}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    {scenario.constraint_violations.length === 0 ? (
                      <CheckCircle className="w-4 h-4 text-green-500" />
                    ) : (
                      <div className="flex items-center gap-1">
                        <AlertTriangle className="w-4 h-4 text-red-500" />
                        <span className="text-xs text-red-600">
                          {scenario.constraint_violations.length}
                        </span>
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span className={cn('badge', getFidelityBadge(scenario.fidelity))}>
                      {scenario.fidelity}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
