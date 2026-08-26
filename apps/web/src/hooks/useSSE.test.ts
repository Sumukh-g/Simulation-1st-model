import { useAppStore } from '@/store';
import type { Run } from '@/types';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useSSE } from './useSSE';

// Mock EventSource that models real semantics: named events are delivered via
// addEventListener(type), NOT onmessage.
class MockEventSource {
  url: string;
  onopen: (() => void) | null = null;
  onerror: ((error: Event) => void) | null = null;
  readyState = 0;
  private listeners: Record<string, Array<(e: { data: string }) => void>> = {};

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
    setTimeout(() => {
      this.readyState = 1;
      this.onopen?.();
    }, 10);
  }

  addEventListener(type: string, cb: (e: { data: string }) => void) {
    (this.listeners[type] ||= []).push(cb);
  }

  close() {
    this.readyState = 2;
  }

  // Simulate a named SSE event whose data is the raw payload.
  emit(type: string, payload: unknown) {
    const data = typeof payload === 'string' ? payload : JSON.stringify(payload);
    (this.listeners[type] || []).forEach((cb) => cb({ data }));
  }

  simulateError() {
    this.onerror?.(new Event('error'));
  }

  static instances: MockEventSource[] = [];
  static reset() {
    MockEventSource.instances = [];
  }
}

const mockRun: Run = {
  id: 'run-123',
  project_id: 'proj-1',
  status: 'running',
  domain_pack: 'toy-pack',
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
};

describe('useSSE', () => {
  beforeEach(() => {
    MockEventSource.reset();
    (global as any).EventSource = MockEventSource;
    useAppStore.setState({ currentRun: null, runStatus: 'idle' });
  });

  afterEach(() => {
    vi.clearAllTimers();
  });

  it('connects to SSE endpoint when enabled', async () => {
    const { result } = renderHook(() => useSSE({ runId: 'run-123', enabled: true }));
    await waitFor(() => expect(result.current.isConnected).toBe(true));
    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.instances[0].url).toBe('http://127.0.0.1:8000/api/runs/run-123/stream');
  });

  it('does not connect when disabled', () => {
    renderHook(() => useSSE({ runId: 'run-123', enabled: false }));
    expect(MockEventSource.instances).toHaveLength(0);
  });

  it('does not connect when runId is empty', () => {
    renderHook(() => useSSE({ runId: '', enabled: true }));
    expect(MockEventSource.instances).toHaveLength(0);
  });

  it('handles named stage_update events', async () => {
    const { result } = renderHook(() => useSSE({ runId: 'run-123', enabled: true }));
    await waitFor(() => expect(result.current.isConnected).toBe(true));
    useAppStore.setState({ currentRun: { ...mockRun } });

    act(() => {
      MockEventSource.instances[0].emit('stage_update', { stage: 'formalize', status: 'completed' });
    });

    expect(useAppStore.getState().currentRun?.stages?.[0]?.status).toBe('completed');
  });

  it('handles counters_update events', async () => {
    const { result } = renderHook(() => useSSE({ runId: 'run-123', enabled: true }));
    await waitFor(() => expect(result.current.isConnected).toBe(true));
    useAppStore.setState({ currentRun: { ...mockRun } });

    act(() => {
      MockEventSource.instances[0].emit('counters_update', {
        ...mockRun.counters,
        scenarios_simulated: 12,
      });
    });

    expect(useAppStore.getState().currentRun?.counters.scenarios_simulated).toBe(12);
  });

  it('replaces candidates on scenario_result (full list)', async () => {
    const { result } = renderHook(() => useSSE({ runId: 'run-123', enabled: true }));
    await waitFor(() => expect(result.current.isConnected).toBe(true));
    useAppStore.setState({ currentRun: { ...mockRun } });

    act(() => {
      MockEventSource.instances[0].emit('scenario_result', [
        { id: 'a', run_id: 'run-123', state: {}, actions: {}, fidelity: 'cheap', seed: 1, metrics: [], judge_score: { scenario_id: 'a', score: 0.4, level: 'good', breakdown: [], benchmarks_passed: 0, benchmarks_total: 0 }, constraint_violations: [], confidence: 0.7 },
        { id: 'b', run_id: 'run-123', state: {}, actions: {}, fidelity: 'cheap', seed: 2, metrics: [], judge_score: { scenario_id: 'b', score: 0.9, level: 'excellent', breakdown: [], benchmarks_passed: 0, benchmarks_total: 0 }, constraint_violations: [], confidence: 0.8 },
      ]);
    });

    const candidates = useAppStore.getState().currentRun?.candidates;
    expect(candidates).toHaveLength(2);
    expect(candidates?.[0].id).toBe('b'); // sorted by score desc
  });

  it('applies run_completed and stops reconnecting', async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useSSE({ runId: 'run-123', enabled: true }));
    await vi.advanceTimersByTimeAsync(20);

    act(() => {
      MockEventSource.instances[0].emit('run_completed', { ...mockRun, status: 'completed' });
    });

    expect(useAppStore.getState().currentRun?.status).toBe('completed');

    // A subsequent connection error must NOT trigger a reconnect after completion.
    act(() => {
      MockEventSource.instances[0].simulateError();
    });
    await vi.advanceTimersByTimeAsync(5000);
    expect(MockEventSource.instances).toHaveLength(1);
    vi.useRealTimers();
  });

  it('disconnects on unmount', async () => {
    const { result, unmount } = renderHook(() => useSSE({ runId: 'run-123', enabled: true }));
    await waitFor(() => expect(result.current.isConnected).toBe(true));
    unmount();
    expect(MockEventSource.instances[0].readyState).toBe(2);
  });

  it('calls onError callback on connection error', async () => {
    vi.useFakeTimers();
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ...mockRun, status: 'running' }),
    }) as any;
    const onError = vi.fn();
    renderHook(() => useSSE({ runId: 'run-123', enabled: true, onError }));
    await vi.advanceTimersByTimeAsync(20);
    await act(async () => {
      MockEventSource.instances[0].simulateError();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(onError).toHaveBeenCalled();
    vi.useRealTimers();
  });

  it('attempts to reconnect after error', async () => {
    vi.useFakeTimers();
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ...mockRun, status: 'running' }),
    }) as any;
    const { result } = renderHook(() => useSSE({ runId: 'run-123', enabled: true }));
    await vi.advanceTimersByTimeAsync(20);
    await act(async () => {
      MockEventSource.instances[0].simulateError();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(result.current.isConnected).toBe(false);
    expect(result.current.reconnectAttempts).toBe(1);
    await vi.advanceTimersByTimeAsync(2000);
    expect(MockEventSource.instances.length).toBeGreaterThan(1);
    vi.useRealTimers();
  });

  it('stops reconnecting when snapshot shows a terminal status', async () => {
    vi.useFakeTimers();
    useAppStore.setState({ currentRun: { ...mockRun, status: 'running' } });
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ...mockRun, status: 'failed' }),
    }) as any;
    renderHook(() => useSSE({ runId: 'run-123', enabled: true }));
    await vi.advanceTimersByTimeAsync(20);
    await act(async () => {
      MockEventSource.instances[0].simulateError();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(useAppStore.getState().currentRun?.status).toBe('failed');
    expect(MockEventSource.instances).toHaveLength(1);
    vi.useRealTimers();
  });
});
