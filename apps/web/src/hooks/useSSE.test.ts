import { useAppStore } from '@/store';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useSSE } from './useSSE';

// Mock EventSource
class MockEventSource {
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: ((error: Event) => void) | null = null;
  readyState = 0;
  
  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
    // Simulate async connection
    setTimeout(() => {
      this.readyState = 1;
      this.onopen?.();
    }, 10);
  }
  
  close() {
    this.readyState = 2;
  }
  
  // Helper to simulate messages
  simulateMessage(data: object) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
  
  simulateError() {
    this.onerror?.(new Event('error'));
  }
  
  static instances: MockEventSource[] = [];
  static reset() {
    MockEventSource.instances = [];
  }
}

describe('useSSE', () => {
  beforeEach(() => {
    MockEventSource.reset();
    (global as any).EventSource = MockEventSource;
    useAppStore.setState({
      currentRun: null,
      runStatus: 'idle',
    });
  });

  afterEach(() => {
    vi.clearAllTimers();
  });

  it('connects to SSE endpoint when enabled', async () => {
    const { result } = renderHook(() =>
      useSSE({ runId: 'run-123', enabled: true })
    );

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true);
    });

    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.instances[0].url).toBe('/api/runs/run-123/stream');
  });

  it('does not connect when disabled', () => {
    renderHook(() =>
      useSSE({ runId: 'run-123', enabled: false })
    );

    expect(MockEventSource.instances).toHaveLength(0);
  });

  it('does not connect when runId is empty', () => {
    renderHook(() =>
      useSSE({ runId: '', enabled: true })
    );

    expect(MockEventSource.instances).toHaveLength(0);
  });

  it('handles stage_update events', async () => {
    const { result } = renderHook(() =>
      useSSE({ runId: 'run-123', enabled: true })
    );

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true);
    });

    // Set up a mock run to update
    useAppStore.setState({
      currentRun: {
        id: 'run-123',
        project_id: 'proj-1',
        status: 'running',
        domain_pack: 'SpatialPack',
        domain_pack_version: '1.0',
        objective_spec: { description: 'Test', objectives: [], constraints: [] },
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        stages: [{ stage: 'formalize', status: 'pending' }],
        counters: {
          scenarios_proposed: 0,
          scenarios_simulated: 0,
          scenarios_promoted: 0,
          cache_hits: 0,
          compute_cost: 0,
          storage_cost: 0,
          budget_consumed: 0,
          budget_total: 100,
        },
        candidates: [],
      },
    });

    act(() => {
      MockEventSource.instances[0].simulateMessage({
        type: 'stage_update',
        run_id: 'run-123',
        data: { stage: 'formalize', status: 'completed' },
      });
    });

    const stages = useAppStore.getState().currentRun?.stages;
    expect(stages).toBeDefined();
    expect(stages?.[0]?.status).toBe('completed');
  });

  it('disconnects on unmount', async () => {
    const { result, unmount } = renderHook(() =>
      useSSE({ runId: 'run-123', enabled: true })
    );

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true);
    });

    unmount();

    expect(MockEventSource.instances[0].readyState).toBe(2);
  });

  it('calls onError callback on connection error', async () => {
    vi.useFakeTimers();
    const onError = vi.fn();

    renderHook(() =>
      useSSE({ runId: 'run-123', enabled: true, onError })
    );

    await vi.advanceTimersByTimeAsync(20);

    act(() => {
      MockEventSource.instances[0].simulateError();
    });

    expect(onError).toHaveBeenCalled();
    vi.useRealTimers();
  });

  it('attempts to reconnect after error', async () => {
    vi.useFakeTimers();

    const { result } = renderHook(() =>
      useSSE({ runId: 'run-123', enabled: true })
    );

    await vi.advanceTimersByTimeAsync(20);

    act(() => {
      MockEventSource.instances[0].simulateError();
    });

    expect(result.current.isConnected).toBe(false);
    expect(result.current.reconnectAttempts).toBe(1);

    // Advance past reconnect delay
    await vi.advanceTimersByTimeAsync(2000);

    expect(MockEventSource.instances.length).toBeGreaterThan(1);
    vi.useRealTimers();
  });
});
