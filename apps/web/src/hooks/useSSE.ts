import { useAppStore } from '@/store';
import type { Run, RunCounters, ScenarioResult, StageStatus } from '@/types';
import { useCallback, useEffect, useRef, useState } from 'react';

interface UseSSEOptions {
  runId: string;
  enabled?: boolean;
  onError?: (error: Error) => void;
  onReconnect?: () => void;
}

function safeParse<T>(raw: string): T | null {
  try {
    return JSON.parse(raw) as T;
  } catch (err) {
    console.error('Failed to parse SSE payload:', err);
    return null;
  }
}

export function useSSE({ runId, enabled = true, onError, onReconnect }: UseSSEOptions) {
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const completedRef = useRef(false);
  const [isConnected, setIsConnected] = useState(false);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);

  const {
    updateRunStage,
    updateRunCounters,
    setCandidates,
    setCurrentBest,
    setCurrentRun,
  } = useAppStore();

  const connect = useCallback(() => {
    if (!enabled || !runId) return;

    // Close existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    completedRef.current = false;
    // Bypass the Next.js rewrite proxy for EventSource. Dev rewrites buffer /
    // reset long-lived SSE connections ("socket hang up"), which left the UI
    // stuck on "Reconnecting..." forever. Point the browser straight at the API.
    const apiBase = (process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
    const url = `${apiBase}/api/runs/${runId}/stream`;
    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      setIsConnected(true);
      setReconnectAttempts(0);
      onReconnect?.();
    };

    // The API emits *named* SSE events; each must be registered explicitly.
    eventSource.addEventListener('stage_update', (e) => {
      const data = safeParse<StageStatus>((e as MessageEvent).data);
      if (data) updateRunStage(data);
    });

    eventSource.addEventListener('counters_update', (e) => {
      const data = safeParse<RunCounters>((e as MessageEvent).data);
      if (data) updateRunCounters(data);
    });

    // scenario_result carries the full ranked candidate list.
    eventSource.addEventListener('scenario_result', (e) => {
      const data = safeParse<ScenarioResult[]>((e as MessageEvent).data);
      if (Array.isArray(data)) setCandidates(data);
    });

    eventSource.addEventListener('best_changed', (e) => {
      const data = safeParse<ScenarioResult>((e as MessageEvent).data);
      if (data && Object.keys(data).length > 0) setCurrentBest(data);
    });

    eventSource.addEventListener('run_completed', (e) => {
      const data = safeParse<Run>((e as MessageEvent).data);
      if (data) {
        setCurrentRun(data);
        if (data.status === 'completed' && (data.candidates?.length ?? 0) > 0) {
          useAppStore.getState().setActiveTab('report');
        }
      }
      // Terminal event: stop listening so we don't reconnect to a closed stream.
      completedRef.current = true;
      eventSource.close();
      setIsConnected(false);
    });

    eventSource.addEventListener('error', (e) => {
      const message = (e as MessageEvent).data;
      if (message) console.error('SSE error event:', message);
    });

    eventSource.onerror = () => {
      setIsConnected(false);
      eventSource.close();

      // Don't reconnect after a normal terminal completion.
      if (completedRef.current) return;

      // Before spinning forever, ask the API whether the run already ended
      // (e.g. worker crashed mid-stream). If it did, adopt that snapshot and stop.
      void (async () => {
        try {
          const res = await fetch(`/api/runs/${runId}`);
          if (res.ok) {
            const run = (await res.json()) as Run;
            if (run.status === 'completed' || run.status === 'failed' || run.status === 'awaiting_input') {
              setCurrentRun(run);
              completedRef.current = true;
              setIsConnected(false);
              return;
            }
          }
        } catch {
          // fall through to reconnect
        }

        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
        setReconnectAttempts((prev) => prev + 1);
        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, delay);
        onError?.(new Error('SSE connection error'));
      })();
    };
  }, [runId, enabled, reconnectAttempts, onError, onReconnect, updateRunStage, updateRunCounters, setCandidates, setCurrentBest, setCurrentRun]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setIsConnected(false);
  }, []);

  useEffect(() => {
    if (enabled && runId) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [enabled, runId, connect, disconnect]);

  return {
    isConnected,
    reconnectAttempts,
    disconnect,
    reconnect: connect,
  };
}

// Hook for fetching snapshot and reconciling state.
// Also polls while a run is active so a dropped SSE stream cannot leave the
// UI spinning on a stale "running" status forever.
export function useRunSnapshot(runId: string | null) {
  const { setCurrentRun, setEvidenceChunks, setBenchmarks, runStatus } = useAppStore();

  const fetchSnapshot = useCallback(async () => {
    if (!runId) return;

    try {
      const response = await fetch(`/api/runs/${runId}`);
      if (!response.ok) throw new Error('Failed to fetch run');
      
      const run = await response.json();
      setCurrentRun(run);

      // Fetch evidence if available
      if (run.evidence_pack_id) {
        const evidenceRes = await fetch(`/api/evidence/packs/${run.evidence_pack_id}`);
        if (evidenceRes.ok) {
          const pack = await evidenceRes.json();
          setEvidenceChunks(pack.chunks || []);
        }
      }

      // Fetch benchmarks
      const benchmarksRes = await fetch(`/api/runs/${runId}/benchmarks`);
      if (benchmarksRes.ok) {
        const benchmarks = await benchmarksRes.json();
        setBenchmarks(benchmarks.benchmarks || []);
      }
    } catch (err) {
      console.error('Failed to fetch run snapshot:', err);
    }
  }, [runId, setCurrentRun, setEvidenceChunks, setBenchmarks]);

  useEffect(() => {
    fetchSnapshot();
  }, [fetchSnapshot]);

  useEffect(() => {
    if (!runId || runStatus !== 'running') return;
    const id = setInterval(() => {
      void fetchSnapshot();
    }, 2000);
    return () => clearInterval(id);
  }, [runId, runStatus, fetchSnapshot]);

  return { refetch: fetchSnapshot };
}
