import { useAppStore } from '@/store';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { WorkspaceTabs } from './WorkspaceTabs';

describe('WorkspaceTabs', () => {
  beforeEach(() => {
    // Reset store state
    useAppStore.setState({
      activeTab: 'overview',
      selectedDomainPack: null,
    });
  });

  it('renders all default tabs', () => {
    render(<WorkspaceTabs />);
    
    expect(screen.getByText('Overview')).toBeInTheDocument();
    expect(screen.getByText('Leaderboard')).toBeInTheDocument();
    expect(screen.getByText('Scenario Detail')).toBeInTheDocument();
    expect(screen.getByText('Charts')).toBeInTheDocument();
    expect(screen.getByText('Evidence')).toBeInTheDocument();
    expect(screen.getByText('Logs & Debug')).toBeInTheDocument();
  });

  it('hides Heatmaps tab when domain pack has no spatial output', () => {
    useAppStore.setState({
      selectedDomainPack: {
        id: 'test',
        name: 'TestPack',
        version: '1.0',
        description: 'Test',
        has_spatial_output: false,
      },
    });
    
    render(<WorkspaceTabs />);
    
    expect(screen.queryByText('Heatmaps')).not.toBeInTheDocument();
  });

  it('shows Heatmaps tab when domain pack has spatial output', () => {
    useAppStore.setState({
      selectedDomainPack: {
        id: 'spatial',
        name: 'SpatialPack',
        version: '1.0',
        description: 'Spatial',
        has_spatial_output: true,
      },
    });
    
    render(<WorkspaceTabs />);
    
    expect(screen.getByText('Heatmaps')).toBeInTheDocument();
  });

  it('changes active tab on click', () => {
    render(<WorkspaceTabs />);
    
    fireEvent.click(screen.getByText('Leaderboard'));
    
    expect(useAppStore.getState().activeTab).toBe('leaderboard');
  });

  it('highlights active tab', () => {
    useAppStore.setState({ activeTab: 'charts' });
    
    render(<WorkspaceTabs />);
    
    const chartsTab = screen.getByText('Charts').closest('button');
    expect(chartsTab).toHaveClass('text-primary-600');
  });
});
