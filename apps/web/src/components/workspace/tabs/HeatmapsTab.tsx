'use client';

import { cn } from '@/lib/utils';
import { useAppStore } from '@/store';
import type { HeatmapMask } from '@/types';
import { Eye, EyeOff } from 'lucide-react';
import { useMemo, useState } from 'react';

type ViewMode = 'baseline' | 'scenario' | 'delta';

const LEGEND_BINS = [
  { label: 'Low', color: 'bg-blue-200', range: '0-25%' },
  { label: 'Medium', color: 'bg-yellow-300', range: '25-50%' },
  { label: 'High', color: 'bg-orange-400', range: '50-75%' },
  { label: 'Severe', color: 'bg-red-500', range: '75-100%' },
];

const DELTA_LEGEND_BINS = [
  { label: 'Decrease', color: 'bg-green-400', range: '< -10%' },
  { label: 'Slight -', color: 'bg-green-200', range: '-10% to 0' },
  { label: 'Slight +', color: 'bg-red-200', range: '0 to +10%' },
  { label: 'Increase', color: 'bg-red-400', range: '> +10%' },
];

export function HeatmapsTab() {
  const { 
    baselineHeatmap, 
    scenarioHeatmap, 
    deltaHeatmap,
    heatmapMasks,
    toggleHeatmapMask,
    setHeatmapMaskValue,
  } = useAppStore();

  const [viewMode, setViewMode] = useState<ViewMode>('delta');
  const [showAllCells, setShowAllCells] = useState(false);

  // Get the active layer based on view mode
  const activeLayer = useMemo(() => {
    switch (viewMode) {
      case 'baseline': return baselineHeatmap;
      case 'scenario': return scenarioHeatmap;
      case 'delta': return deltaHeatmap;
      default: return null;
    }
  }, [viewMode, baselineHeatmap, scenarioHeatmap, deltaHeatmap]);

  // Apply masks to create display grid
  const displayGrid = useMemo(() => {
    if (!activeLayer) return null;

    const { data, min, max } = activeLayer;
    const range = max - min;

    return data.map((row, y) => 
      row.map((value, x) => {
        // Normalize value to 0-1
        const normalized = range > 0 ? (value - min) / range : 0;
        
        // Check masks
        let masked = false;
        
        for (const mask of heatmapMasks) {
          if (!mask.enabled) continue;

          switch (mask.type) {
            case 'threshold':
              if (value < (mask.value || 0)) masked = true;
              break;
            case 'delta':
              if (Math.abs(value) < (mask.value || 0)) masked = true;
              break;
            case 'confidence':
              // Would check confidence data here
              break;
            case 'constraint':
              // Would check constraint violations here
              break;
          }
        }

        if (masked && !showAllCells) {
          return { value, normalized, masked: true };
        }

        return { value, normalized, masked: false };
      })
    );
  }, [activeLayer, heatmapMasks, showAllCells]);

  const getCellColor = (normalized: number, isDelta: boolean): string => {
    if (isDelta) {
      // Delta uses diverging colors
      if (normalized < 0.25) return 'bg-green-400';
      if (normalized < 0.5) return 'bg-green-200';
      if (normalized < 0.75) return 'bg-red-200';
      return 'bg-red-400';
    } else {
      // Regular uses sequential colors
      if (normalized < 0.25) return 'bg-blue-200';
      if (normalized < 0.5) return 'bg-yellow-300';
      if (normalized < 0.75) return 'bg-orange-400';
      return 'bg-red-500';
    }
  };

  if (!baselineHeatmap && !scenarioHeatmap) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-500">
        <div className="text-center">
          <p className="mb-2">No spatial data available</p>
          <p className="text-sm">This domain pack does not output spatial layers</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-hidden flex">
      {/* Main Heatmap Display */}
      <div className="flex-1 p-4 overflow-auto">
        {/* View Mode Toggle */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            {(['baseline', 'scenario', 'delta'] as ViewMode[]).map((mode) => (
              <button
                key={mode}
                onClick={() => setViewMode(mode)}
                disabled={
                  (mode === 'baseline' && !baselineHeatmap) ||
                  (mode === 'scenario' && !scenarioHeatmap) ||
                  (mode === 'delta' && !deltaHeatmap)
                }
                className={cn(
                  'px-3 py-1.5 text-sm font-medium rounded-lg transition-colors',
                  viewMode === mode
                    ? 'bg-primary-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200 disabled:opacity-50'
                )}
              >
                {mode.charAt(0).toUpperCase() + mode.slice(1)}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowAllCells(!showAllCells)}
              className="btn-secondary gap-2"
            >
              {showAllCells ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              {showAllCells ? 'Apply Masks' : 'Show All'}
            </button>
          </div>
        </div>

        {/* Heatmap Grid */}
        <div className="card p-4">
          {displayGrid ? (
            <div className="overflow-auto max-h-96">
              <div 
                className="grid gap-px bg-gray-300"
                style={{ 
                  gridTemplateColumns: `repeat(${displayGrid[0]?.length || 1}, minmax(8px, 1fr))`,
                }}
              >
                {displayGrid.flat().map((cell, i) => (
                  <div
                    key={i}
                    className={cn(
                      'aspect-square transition-colors',
                      cell.masked 
                        ? 'bg-gray-100' 
                        : getCellColor(cell.normalized, viewMode === 'delta')
                    )}
                    title={`Value: ${cell.value.toFixed(2)}`}
                  />
                ))}
              </div>
            </div>
          ) : (
            <div className="h-64 flex items-center justify-center text-gray-500">
              No data for this view
            </div>
          )}
        </div>

        {/* Legend */}
        <div className="mt-4 card p-4">
          <h4 className="text-sm font-medium text-gray-700 mb-2">Legend</h4>
          <div className="flex items-center gap-4">
            {(viewMode === 'delta' ? DELTA_LEGEND_BINS : LEGEND_BINS).map((bin) => (
              <div key={bin.label} className="flex items-center gap-2">
                <div className={cn('w-4 h-4 rounded', bin.color)} />
                <span className="text-xs text-gray-600">
                  {bin.label} <span className="text-gray-400">({bin.range})</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Mask Controls Panel */}
      <div className="w-64 border-l border-gray-200 bg-white p-4 overflow-y-auto">
        <h3 className="text-sm font-semibold text-gray-700 mb-4">Mask Controls</h3>

        <div className="space-y-4">
          {heatmapMasks.map((mask) => (
            <MaskControl
              key={mask.type}
              mask={mask}
              onToggle={() => toggleHeatmapMask(mask.type)}
              onValueChange={(value) => setHeatmapMaskValue(mask.type, value)}
            />
          ))}
        </div>

        {/* Active Masks Summary */}
        <div className="mt-6 pt-4 border-t border-gray-200">
          <p className="text-xs text-gray-500">
            {heatmapMasks.filter(m => m.enabled).length} mask(s) active
          </p>
        </div>
      </div>
    </div>
  );
}

function MaskControl({ 
  mask, 
  onToggle, 
  onValueChange 
}: { 
  mask: HeatmapMask;
  onToggle: () => void;
  onValueChange: (value: number) => void;
}) {
  const labels: Record<HeatmapMask['type'], { title: string; desc: string }> = {
    threshold: { title: 'Threshold Mask', desc: 'Hide cells below value' },
    delta: { title: 'Delta Threshold', desc: 'Hide cells with |delta| below value' },
    topk: { title: 'Top-K Hotspots', desc: 'Show only top K cells' },
    constraint: { title: 'Constraint Violations', desc: 'Show cells exceeding threshold' },
    confidence: { title: 'Confidence Mask', desc: 'Hide uncertain cells' },
  };

  const { title, desc } = labels[mask.type];

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-gray-700">{title}</p>
          <p className="text-xs text-gray-500">{desc}</p>
        </div>
        <button
          onClick={onToggle}
          className={cn(
            'w-10 h-6 rounded-full transition-colors',
            mask.enabled ? 'bg-primary-600' : 'bg-gray-200'
          )}
        >
          <div className={cn(
            'w-4 h-4 bg-white rounded-full transition-transform shadow',
            mask.enabled ? 'translate-x-5' : 'translate-x-1'
          )} />
        </button>
      </div>

      {mask.enabled && mask.value !== undefined && (
        <input
          type="number"
          value={mask.value}
          onChange={(e) => onValueChange(parseFloat(e.target.value) || 0)}
          className="input text-sm"
          step={mask.type === 'topk' ? 1 : 0.1}
        />
      )}
    </div>
  );
}
