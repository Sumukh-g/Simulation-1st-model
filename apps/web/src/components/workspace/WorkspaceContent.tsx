'use client';

import { useAppStore } from '@/store';
import { ChartsTab } from './tabs/ChartsTab';
import { EvidenceTab } from './tabs/EvidenceTab';
import { HeatmapsTab } from './tabs/HeatmapsTab';
import { LeaderboardTab } from './tabs/LeaderboardTab';
import { LogsTab } from './tabs/LogsTab';
import { OverviewTab } from './tabs/OverviewTab';
import { ScenarioDetailTab } from './tabs/ScenarioDetailTab';

export function WorkspaceContent() {
  const { activeTab } = useAppStore();

  const renderTab = () => {
    switch (activeTab) {
      case 'overview':
        return <OverviewTab />;
      case 'leaderboard':
        return <LeaderboardTab />;
      case 'detail':
        return <ScenarioDetailTab />;
      case 'charts':
        return <ChartsTab />;
      case 'heatmaps':
        return <HeatmapsTab />;
      case 'evidence':
        return <EvidenceTab />;
      case 'logs':
        return <LogsTab />;
      default:
        return <OverviewTab />;
    }
  };

  return (
    <div className="flex-1 overflow-hidden flex flex-col bg-surface-secondary">
      {renderTab()}
    </div>
  );
}
