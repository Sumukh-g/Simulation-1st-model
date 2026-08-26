'use client';

import { cn, getStatusColor } from '@/lib/utils';
import { useAppStore } from '@/store';
import { Activity, Check, ChevronDown, Settings } from 'lucide-react';
import { useState } from 'react';

export function Header() {
  const {
    projects,
    selectedProject,
    setSelectedProject,
    domainPacks,
    selectedDomainPack,
    setSelectedDomainPack,
    runConfig,
    setRunConfig,
    runStatus,
  } = useAppStore();

  const [showProjectMenu, setShowProjectMenu] = useState(false);
  const [showPackMenu, setShowPackMenu] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  const statusLabels: Record<string, string> = {
    idle: 'Idle',
    running: 'Running',
    completed: 'Completed',
    failed: 'Failed',
    awaiting_input: 'Awaiting input',
  };

  return (
    <header className="h-14 bg-white border-b border-gray-200 flex items-center px-4 gap-4">
      {/* Project Selector */}
      <div className="relative">
        <button
          onClick={() => setShowProjectMenu(!showProjectMenu)}
          className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-lg"
        >
          <span>{selectedProject?.name || 'Select Project'}</span>
          <ChevronDown className="w-4 h-4" />
        </button>
        
        {showProjectMenu && (
          <div className="absolute top-full left-0 mt-1 w-48 bg-white border border-gray-200 rounded-lg shadow-lg z-50">
            {projects.length === 0 ? (
              <div className="px-3 py-2 text-sm text-gray-500">No projects</div>
            ) : (
              projects.map((project) => (
                <button
                  key={project.id}
                  onClick={() => {
                    setSelectedProject(project);
                    setShowProjectMenu(false);
                  }}
                  className="w-full px-3 py-2 text-left text-sm hover:bg-gray-50 flex items-center gap-2"
                >
                  {selectedProject?.id === project.id && (
                    <Check className="w-4 h-4 text-primary-600" />
                  )}
                  <span>{project.name}</span>
                </button>
              ))
            )}
          </div>
        )}
      </div>

      <div className="h-6 w-px bg-gray-200" />

      {/* Domain Pack Selector */}
      <div className="relative">
        <button
          onClick={() => setShowPackMenu(!showPackMenu)}
          className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-lg"
        >
          <span>{selectedDomainPack?.name || 'Select Domain Pack'}</span>
          <ChevronDown className="w-4 h-4" />
        </button>
        
        {showPackMenu && (
          <div className="absolute top-full left-0 mt-1 w-56 bg-white border border-gray-200 rounded-lg shadow-lg z-50">
            {domainPacks.length === 0 ? (
              <div className="px-3 py-2 text-sm text-gray-500">No domain packs</div>
            ) : (
              domainPacks.map((pack) => (
                <button
                  key={pack.id}
                  onClick={() => {
                    setSelectedDomainPack(pack);
                    setShowPackMenu(false);
                  }}
                  className="w-full px-3 py-2 text-left text-sm hover:bg-gray-50"
                >
                  <div className="flex items-center gap-2">
                    {selectedDomainPack?.id === pack.id && (
                      <Check className="w-4 h-4 text-primary-600" />
                    )}
                    <span className="font-medium">{pack.name}</span>
                    <span className="text-gray-400">v{pack.version}</span>
                  </div>
                </button>
              ))
            )}
          </div>
        )}
      </div>

      <div className="h-6 w-px bg-gray-200" />

      {/* Run Budget Controls */}
      <div className="relative">
        <button
          onClick={() => setShowSettings(!showSettings)}
          className="flex items-center gap-2 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 rounded-lg"
        >
          <Settings className="w-4 h-4" />
          <span>Run Settings</span>
        </button>

        {showSettings && (
          <div className="absolute top-full left-0 mt-1 w-72 bg-white border border-gray-200 rounded-lg shadow-lg z-50 p-4 space-y-4">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">
                Max Scenarios
              </label>
              <input
                type="number"
                value={runConfig.maxScenarios}
                onChange={(e) => setRunConfig({ maxScenarios: parseInt(e.target.value) || 100 })}
                className="input"
              />
            </div>
            
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">
                Max Wall Time (seconds)
              </label>
              <input
                type="number"
                value={runConfig.maxWallTime}
                onChange={(e) => setRunConfig({ maxWallTime: parseInt(e.target.value) || 3600 })}
                className="input"
              />
            </div>
            
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">
                Fidelity Policy
              </label>
              <select
                value={runConfig.fidelityPolicy}
                onChange={(e) => setRunConfig({ fidelityPolicy: e.target.value as any })}
                className="input"
              >
                <option value="cheap_first">Cheap First (recommended)</option>
                <option value="balanced">Balanced</option>
                <option value="high_only">High Only</option>
              </select>
            </div>
          </div>
        )}
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Status Indicator */}
      <div className={cn('flex items-center gap-2 px-3 py-1.5 rounded-lg', getStatusColor(runStatus))}>
        <Activity className={cn('w-4 h-4', runStatus === 'running' && 'animate-pulse')} />
        <span className="text-sm font-medium">{statusLabels[runStatus]}</span>
      </div>
    </header>
  );
}
