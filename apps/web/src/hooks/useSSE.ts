import { useAppStore } from '@/store';
import type { ScenarioResult, SSEEvent, StageStatus } from '@/types';
import { useCallback, useEffect, useRef, useState } from 'react';

interface UseSSEOptions {
  runId: string;
  enabled?: boolean;
  onError?: (error: Error) => void;
  onReconnect?: () => void;
}

export function useSSE({ runId, enabled = true, onError, onReconnect }: UseSSEOptions) {
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  
  const {
    updateRunStage,
    updateRunCounters,
    addScenarioResult,
    setCurrentBest,
    setCurrentRun,
  } = useAppStore();

  const connect = useCallback(() => {
    if (!enabled || !runId) return;

    // Close existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const url = `/api/runs/${runId}/stream`;
    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      setIsConnected(true);
      setReconnectAttempts(0);
      onReconnect?.();
    };

    eventSource.onmessage = (event) => {
      try {
        const data: SSEEvent = JSON.parse(event.data);
        handleEvent(data);
      } catch (err) {
        console.error('Failed to parse SSE event:', err);
      }
    };

    eventSource.onerror = (error) => {
      setIsConnected(false);
      eventSource.close();

      // Exponential backoff reconnect
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
      setReconnectAttempts((prev) => prev + 1);

      reconnectTimeoutRef.current = setTimeout(() => {
        connect();
      }, delay);

      onError?.(new Error('SSE connection error'));
    };
  }, [runId, enabled, reconnectAttempts, onError, onReconnect]);

  const handleEvent = useCallback((event: SSEEvent) => {
    switch (event.type) {
      case 'stage_update':
        updateRunStage(event.data as StageStatus);
        break;

      case 'scenario_result':
        addScenarioResult(event.data as ScenarioResult);
        break;

      case 'best_changed':
        setCurrentBest(event.data as ScenarioResult);
        break;

      case 'run_completed':
        setCurrentRun(event.data as any);
        break;

      case 'error':
        console.error('SSE error event:', event.data);
        break;

      default:
        console.log('Unknown SSE event type:', event.type);
    }
  }, [updateRunStage, addScenarioResult, setCurrentBest, setCurrentRun]);

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

// Hook for fetching snapshot and reconciling state
export function useRunSnapshot(runId: string | null) {
  const { setCurrentRun, setEvidenceChunks, setBenchmarks } = useAppStore();

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

  return { refetch: fetchSnapshot };
}
