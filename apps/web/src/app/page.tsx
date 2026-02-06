'use client';

import { ChatComposer } from '@/components/chat/ChatComposer';
import { ChatThread } from '@/components/chat/ChatThread';
import { Header } from '@/components/layout/Header';
import { WorkspaceContent } from '@/components/workspace/WorkspaceContent';
import { WorkspaceTabs } from '@/components/workspace/WorkspaceTabs';
import { useRunSnapshot, useSSE } from '@/hooks/useSSE';
import { useAppStore } from '@/store';
import { useEffect } from 'react';

export default function HomePage() {
  const { 
    currentRun, 
    runStatus,
    setSelectedProject,
    setSelectedDomainPack,
  } = useAppStore();

  // Initialize demo data
  useEffect(() => {
    // Set demo project and domain packs
    useAppStore.setState({
      projects: [
        { id: 'demo-project', name: 'Demo Project', org_id: 'org-001' },
      ],
      domainPacks: [
        { id: 'spatial-pack', name: 'SpatialPack', version: '1.0.0', description: 'Spatial simulation', has_spatial_output: true },
        { id: 'finance-pack', name: 'FinancePack', version: '1.0.0', description: 'Financial simulation', has_spatial_output: false },
        { id: 'toy-pack', name: 'ToyPack', version: '1.0.0', description: 'Demo/testing pack', has_spatial_output: false },
      ],
    });

    setSelectedProject({ id: 'demo-project', name: 'Demo Project', org_id: 'org-001' });
    setSelectedDomainPack({ id: 'spatial-pack', name: 'SpatialPack', version: '1.0.0', description: 'Spatial simulation', has_spatial_output: true });
  }, [setSelectedProject, setSelectedDomainPack]);

  // SSE connection for live updates
  const { isConnected, reconnect } = useSSE({
    runId: currentRun?.id || '',
    enabled: runStatus === 'running' && !!currentRun?.id,
    onError: (error) => console.error('SSE Error:', error),
    onReconnect: () => console.log('SSE Reconnected'),
  });

  // Fetch run snapshot for state reconciliation
  useRunSnapshot(currentRun?.id || null);

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      {/* Header */}
      <Header />

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Simulation Workspace (60-70% height) */}
        <div className="h-[65%] flex flex-col border-b border-gray-200">
          <WorkspaceTabs />
          <WorkspaceContent />
        </div>

        {/* Chat Section (30-40% height) */}
        <div className="h-[35%] flex flex-col bg-white">
          <ChatThread />
          <ChatComposer />
        </div>
      </div>

      {/* Connection Status Indicator */}
      {runStatus === 'running' && (
        <div className="fixed bottom-4 right-4 flex items-center gap-2 px-3 py-2 bg-white rounded-lg shadow-lg border border-gray-200 text-sm">
          <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
          <span className="text-gray-600">
            {isConnected ? 'Live updates connected' : 'Reconnecting...'}
          </span>
          {!isConnected && (
            <button
              onClick={reconnect}
              className="text-primary-600 hover:text-primary-700 font-medium"
            >
              Retry
            </button>
          )}
        </div>
      )}
    </div>
  );
}
