'use client';

import { cn, formatNumber } from '@/lib/utils';
import { useAppStore } from '@/store';
import { useMemo, useState } from 'react';
import {
    Area,
    AreaChart,
    CartesianGrid,
    Legend,
    Line,
    LineChart,
    ResponsiveContainer,
    Scatter,
    ScatterChart,
    Tooltip,
    XAxis,
    YAxis,
    ZAxis
} from 'recharts';

type ChartType = 'timeseries' | 'comparison' | 'pareto';

export function ChartsTab() {
  const { currentRun, selectedScenario, setSelectedScenario, setActiveTab } = useAppStore();
  const [activeChart, setActiveChart] = useState<ChartType>('timeseries');
  const [selectedMetric, setSelectedMetric] = useState<string>('');

  const candidates = currentRun?.candidates || [];
  const current_best = currentRun?.current_best;

  // Get all unique metric names
  const metricNames = useMemo(() => {
    const names = new Set<string>();
    candidates.forEach(c => c.metrics.forEach(m => names.add(m.name)));
    return Array.from(names);
  }, [candidates]);

  // Set default metric
  if (!selectedMetric && metricNames.length > 0) {
    setSelectedMetric(metricNames[0]);
  }

  // Time series data (simulated for now)
  const timeSeriesData = useMemo(() => {
    return candidates.slice(0, 50).map((c, i) => {
      const metric = c.metrics.find(m => m.name === selectedMetric);
      return {
        index: i + 1,
        value: metric?.value || 0,
        p10: metric?.uncertainty?.p10 || (metric?.value || 0) * 0.9,
        p90: metric?.uncertainty?.p90 || (metric?.value || 0) * 1.1,
        id: c.id,
      };
    });
  }, [candidates, selectedMetric]);

  // Comparison data
  const comparisonData = useMemo(() => {
    const baseline = candidates[0];
    const best = current_best;
    const runnerUp = candidates.find(c => c.id !== best?.id);

    if (!baseline || !best) return [];

    return metricNames.map(name => {
      const baselineMetric = baseline.metrics.find(m => m.name === name);
      const bestMetric = best.metrics.find(m => m.name === name);
      const runnerUpMetric = runnerUp?.metrics.find(m => m.name === name);

      return {
        name,
        Baseline: baselineMetric?.value || 0,
        Best: bestMetric?.value || 0,
        'Runner-up': runnerUpMetric?.value || 0,
      };
    });
  }, [candidates, current_best, metricNames]);

  // Pareto data (impact vs cost)
  const paretoData = useMemo(() => {
    return candidates.map(c => {
      const impact = c.metrics.find(m => m.name.toLowerCase().includes('impact'))?.value || c.judge_score?.score || 0;
      const cost = c.metrics.find(m => m.name.toLowerCase().includes('cost'))?.value || 0;
      const feasibility = c.confidence;

      return {
        id: c.id,
        impact,
        cost,
        feasibility,
        isBest: c.id === current_best?.id,
        isSelected: c.id === selectedScenario?.id,
      };
    });
  }, [candidates, current_best, selectedScenario]);

  const handleParetoClick = (data: any) => {
    const scenario = candidates.find(c => c.id === data.id);
    if (scenario) {
      setSelectedScenario(scenario);
      setActiveTab('detail');
    }
  };

  if (candidates.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-500">
        No data to display. Wait for scenarios to be evaluated.
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      {/* Chart Type Selector */}
      <div className="flex items-center gap-2">
        {(['timeseries', 'comparison', 'pareto'] as ChartType[]).map((type) => (
          <button
            key={type}
            onClick={() => setActiveChart(type)}
            className={cn(
              'px-4 py-2 text-sm font-medium rounded-lg transition-colors',
              activeChart === type
                ? 'bg-primary-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            )}
          >
            {type === 'timeseries' && 'Time Series'}
            {type === 'comparison' && 'Comparison'}
            {type === 'pareto' && 'Pareto Frontier'}
          </button>
        ))}
      </div>

      {/* Time Series Chart */}
      {activeChart === 'timeseries' && (
        <div className="card p-4">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-gray-700">Metric Over Time</h3>
            <select
              value={selectedMetric}
              onChange={(e) => setSelectedMetric(e.target.value)}
              className="input w-48"
            >
              {metricNames.map((name) => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          </div>
          
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={timeSeriesData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="index" label={{ value: 'Scenario #', position: 'insideBottom', offset: -5 }} />
                <YAxis />
                <Tooltip 
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload;
                      return (
                        <div className="bg-white p-3 rounded-lg shadow-lg border border-gray-200">
                          <p className="text-xs text-gray-500 font-mono">{data.id}</p>
                          <p className="text-sm font-medium">Value: {formatNumber(data.value)}</p>
                          <p className="text-xs text-gray-500">
                            P10: {formatNumber(data.p10)} | P90: {formatNumber(data.p90)}
                          </p>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="p90"
                  stroke="transparent"
                  fill="#bae6fd"
                  fillOpacity={0.3}
                />
                <Area
                  type="monotone"
                  dataKey="p10"
                  stroke="transparent"
                  fill="#ffffff"
                  fillOpacity={1}
                />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="#0ea5e9"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  activeDot={{ r: 6, fill: '#0284c7' }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Comparison Chart */}
      {activeChart === 'comparison' && (
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">
            Baseline vs Best vs Runner-up
          </h3>
          
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={comparisonData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="Baseline"
                  stroke="#94a3b8"
                  strokeWidth={2}
                  strokeDasharray="5 5"
                />
                <Line
                  type="monotone"
                  dataKey="Best"
                  stroke="#10b981"
                  strokeWidth={3}
                />
                <Line
                  type="monotone"
                  dataKey="Runner-up"
                  stroke="#3b82f6"
                  strokeWidth={2}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Pareto Frontier Chart */}
      {activeChart === 'pareto' && (
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">
            Pareto Frontier (Impact vs Cost)
          </h3>
          <p className="text-xs text-gray-500 mb-4">
            Click a point to view scenario details. Size indicates feasibility.
          </p>
          
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis 
                  type="number" 
                  dataKey="cost" 
                  name="Cost" 
                  label={{ value: 'Cost', position: 'insideBottom', offset: -5 }}
                />
                <YAxis 
                  type="number" 
                  dataKey="impact" 
                  name="Impact"
                  label={{ value: 'Impact', angle: -90, position: 'insideLeft' }}
                />
                <ZAxis type="number" dataKey="feasibility" range={[50, 300]} />
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload;
                      return (
                        <div className="bg-white p-3 rounded-lg shadow-lg border border-gray-200">
                          <p className="text-xs text-gray-500 font-mono">{data.id}</p>
                          <p className="text-sm">Impact: {formatNumber(data.impact)}</p>
                          <p className="text-sm">Cost: {formatNumber(data.cost)}</p>
                          <p className="text-sm">Feasibility: {formatNumber(data.feasibility * 100)}%</p>
                          {data.isBest && (
                            <p className="text-xs text-green-600 font-medium mt-1">★ Current Best</p>
                          )}
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Scatter
                  name="Scenarios"
                  data={paretoData}
                  fill="#0ea5e9"
                  onClick={handleParetoClick}
                  cursor="pointer"
                  shape={(props: any) => {
                    const { cx, cy, payload } = props;
                    const size = 6 + payload.feasibility * 10;
                    return (
                      <circle
                        cx={cx}
                        cy={cy}
                        r={size}
                        fill={payload.isBest ? '#10b981' : payload.isSelected ? '#f59e0b' : '#0ea5e9'}
                        stroke={payload.isBest ? '#047857' : 'transparent'}
                        strokeWidth={2}
                        opacity={0.7}
                      />
                    );
                  }}
                />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}
