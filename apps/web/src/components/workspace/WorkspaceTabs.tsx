'use client';

import { cn } from '@/lib/utils';
import { useAppStore } from '@/store';
import {
    FileSearch,
    FileText,
    Grid3X3,
    LayoutDashboard,
    LineChart,
    Terminal,
    Trophy
} from 'lucide-react';

const tabs = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'leaderboard', label: 'Leaderboard', icon: Trophy },
  { id: 'detail', label: 'Scenario Detail', icon: FileText },
  { id: 'charts', label: 'Charts', icon: LineChart },
  { id: 'heatmaps', label: 'Heatmaps', icon: Grid3X3 },
  { id: 'evidence', label: 'Evidence', icon: FileSearch },
  { id: 'logs', label: 'Logs & Debug', icon: Terminal },
];

export function WorkspaceTabs() {
  const { activeTab, setActiveTab, selectedDomainPack } = useAppStore();
  
  // Filter heatmaps tab if domain pack doesn't have spatial output
  const visibleTabs = tabs.filter(tab => 
    tab.id !== 'heatmaps' || selectedDomainPack?.has_spatial_output
  );

  return (
    <div className="flex items-center gap-1 px-4 bg-white border-b border-gray-200">
      {visibleTabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = activeTab === tab.id;
        
        return (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              'flex items-center gap-2 px-3 py-3 text-sm font-medium border-b-2 transition-colors',
              isActive
                ? 'text-primary-600 border-primary-600'
                : 'text-gray-600 border-transparent hover:text-gray-900 hover:border-gray-300'
            )}
          >
            <Icon className="w-4 h-4" />
            <span>{tab.label}</span>
          </button>
        );
      })}
    </div>
  );
}
