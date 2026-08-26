'use client';

import { ChatComposer } from '@/components/chat/ChatComposer';
import { ChatThread } from '@/components/chat/ChatThread';
import { Header } from '@/components/layout/Header';
import {
  refreshRunHistory,
  RunHistorySidebar,
} from '@/components/layout/RunHistorySidebar';
import { VerticalSplit } from '@/components/layout/VerticalSplit';
import { WorkspaceContent } from '@/components/workspace/WorkspaceContent';
import { WorkspaceTabs } from '@/components/workspace/WorkspaceTabs';
import { useRunSnapshot } from '@/hooks/useSSE';
import { useAppStore } from '@/store';
import type { Project } from '@/types';
import { useEffect } from 'react';

export default function HomePage() {
  const {
    currentRun,
    runStatus,
    selectedProject,
    setSelectedProject,
    setSelectedDomainPack,
    setProjects,
  } = useAppStore();

  // Domain packs (static catalog) + real projects/runs from the API.
  useEffect(() => {
    useAppStore.setState({
      domainPacks: [
        {
          id: 'toy-pack',
          name: 'toy-pack',
          version: '1.0.0',
          description: 'Demo/testing pack',
          has_spatial_output: false,
        },
        {
          id: 'finance-pack',
          name: 'finance-pack',
          version: '1.0.0',
          description: 'Financial simulation',
          has_spatial_output: false,
        },
        {
          id: 'spatial-pack',
          name: 'spatial-pack',
          version: '1.0.0',
          description: 'Spatial simulation',
          has_spatial_output: true,
        },
      ],
    });
    setSelectedDomainPack({
      id: 'toy-pack',
      name: 'toy-pack',
      version: '1.0.0',
      description: 'Demo/testing pack',
      has_spatial_output: false,
    });

    let cancelled = false;
    (async () => {
      try {
        const res = await fetch('/api/projects');
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        const projects = (data.projects || []).map(
          (p: { id: string; name: string; org_id: string }) =>
            ({
              id: p.id,
              name: p.name,
              org_id: p.org_id,
            }) as Project
        );
        if (cancelled) return;
        setProjects(projects);
        const current = useAppStore.getState().selectedProject;
        const stillValid = current && projects.some((p: Project) => p.id === current.id);
        if (!stillValid && projects.length > 0) {
          setSelectedProject(projects[0]);
        }
      } catch (err) {
        console.error('Failed to load projects:', err);
        if (!cancelled) {
          setProjects([{ id: 'demo-project', name: 'Demo Project', org_id: 'org-001' }]);
          setSelectedProject({ id: 'demo-project', name: 'Demo Project', org_id: 'org-001' });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [setSelectedProject, setSelectedDomainPack, setProjects]);

  // Refresh history when project changes (and on first real project load).
  useEffect(() => {
    if (!selectedProject?.id || selectedProject.id === 'demo-project') return;
    void refreshRunHistory();
  }, [selectedProject?.id]);

  // Live updates via polling (SSE was exhausting Postgres under reconnect
  // storms through the Next proxy / cancelled stream cleanup). Snapshot every
  // 2s while a run is active is enough for this UI.
  useRunSnapshot(currentRun?.id || null);

  // Keep the chat run-card badge in sync with the live run status.
  useEffect(() => {
    if (!currentRun?.id) return;
    const { messages, updateMessage } = useAppStore.getState();
    for (const message of messages) {
      if (message.run_card?.run_id === currentRun.id && message.run_card.status !== currentRun.status) {
        updateMessage(message.id, {
          run_card: { ...message.run_card, status: currentRun.status },
        });
      }
    }
  }, [currentRun?.id, currentRun?.status]);

  // When a live run finishes, refresh the sidebar so status/title stay current.
  useEffect(() => {
    if (currentRun?.status === 'completed' || currentRun?.status === 'failed') {
      void refreshRunHistory();
    }
  }, [currentRun?.status]);

  return (
    <div className="h-screen flex overflow-hidden">
      <RunHistorySidebar />

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Header />

        <VerticalSplit
          top={
            <div className="h-full flex flex-col overflow-hidden">
              <WorkspaceTabs />
              <WorkspaceContent />
            </div>
          }
          bottom={
            <div className="h-full flex flex-col overflow-hidden">
              <ChatThread />
              <ChatComposer />
            </div>
          }
        />

        {runStatus === 'running' && (
          <div className="fixed bottom-4 right-4 flex items-center gap-2 px-3 py-2 bg-white rounded-lg shadow-lg border border-gray-200 text-sm z-40">
            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            <span className="text-gray-600">Live updates active</span>
          </div>
        )}
      </div>
    </div>
  );
}
