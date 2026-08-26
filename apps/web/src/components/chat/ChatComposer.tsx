'use client';

import { generateId } from '@/lib/utils';
import { useAppStore } from '@/store';
import type { SimulationMode } from '@/types';
import { Loader2, Send, Settings2 } from 'lucide-react';
import { KeyboardEvent, useCallback, useRef, useState } from 'react';
import { refreshRunHistory } from '@/components/layout/RunHistorySidebar';

const MODE_LABELS: Record<SimulationMode, string> = {
  domain_pack: 'Use existing pack',
  create_pack: 'Create domain pack',
  no_pack: 'No domain pack',
};

export function ChatComposer() {
  const [input, setInput] = useState('');
  const [showQuickControls, setShowQuickControls] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const {
    isStreaming,
    addMessage,
    setStreaming,
    selectedDomainPack,
    selectedProject,
    simulationMode,
    setSimulationMode,
    runConfig,
    setCurrentRun,
  } = useAppStore();

  const handleSubmit = useCallback(async () => {
    if (!input.trim() || isStreaming) return;

    if (simulationMode === 'domain_pack' && !selectedDomainPack?.name) {
      addMessage({
        id: generateId(),
        role: 'system',
        content: 'Select a domain pack in the header, or switch mode to Create pack / No pack.',
        timestamp: new Date().toISOString(),
      });
      return;
    }

    const userMessage = {
      id: generateId(),
      role: 'user' as const,
      content: input.trim(),
      timestamp: new Date().toISOString(),
    };

    addMessage(userMessage);
    setInput('');
    setStreaming(true);

    try {
      const assistantMessageId = generateId();
      addMessage({
        id: assistantMessageId,
        role: 'assistant',
        content: 'Starting simulation run...',
        timestamp: new Date().toISOString(),
        streaming: true,
      });

      const body: Record<string, unknown> = {
        prompt: input.trim(),
        simulation_mode: simulationMode,
        config: runConfig,
      };
      if (simulationMode === 'domain_pack') {
        body.domain_pack = selectedDomainPack?.name;
      }
      if (selectedProject?.id && selectedProject.id !== 'demo-project') {
        body.project_id = selectedProject.id;
      }

      const response = await fetch('/api/runs/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(errText || 'Failed to start run');
      }

      const run = await response.json();
      setCurrentRun(run);
      void refreshRunHistory();

      const { updateMessage } = useAppStore.getState();
      const draftName =
        run.draft_pack && typeof run.draft_pack.name === 'string'
          ? run.draft_pack.name
          : undefined;
      const content =
        run.assistant_message ||
        run.narrative?.text ||
        (run.status === 'running'
          ? `Simulation running${draftName ? ` with ${draftName}` : ''}…`
          : run.simulation_mode === 'create_pack'
            ? `Drafted a domain pack approach for your request. Domain: ${run.classification?.domain || 'n/a'}.`
            : run.simulation_mode === 'no_pack'
              ? `Drafted an ephemeral / illustrative pack for this run (${draftName || 'see Overview'}).`
              : `I'll help using ${run.domain_pack}. The optimization run has started.`);

      updateMessage(assistantMessageId, {
        content,
        streaming: false,
        run_card: {
          run_id: run.id,
          status: run.status,
          objective_summary: run.objective_spec?.description || input.trim(),
          domain_pack: run.domain_pack || draftName || MODE_LABELS[simulationMode],
        },
      });
    } catch (error) {
      console.error('Failed to start run:', error);
      addMessage({
        id: generateId(),
        role: 'system',
        content: `Failed to start simulation run: ${error instanceof Error ? error.message : 'unknown error'}`,
        timestamp: new Date().toISOString(),
      });
    } finally {
      setStreaming(false);
    }
  }, [
    input,
    isStreaming,
    addMessage,
    setStreaming,
    selectedDomainPack,
    selectedProject,
    simulationMode,
    runConfig,
    setCurrentRun,
  ]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const adjustTextareaHeight = () => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
    }
  };

  return (
    <div className="border-t border-gray-200 bg-white p-4">
      {showQuickControls && (
        <div className="mb-3 p-3 bg-gray-50 rounded-lg border border-gray-200 space-y-3">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span className="text-gray-500">Mode:</span>
            {(Object.keys(MODE_LABELS) as SimulationMode[]).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setSimulationMode(mode)}
                className={`px-2 py-1 rounded border text-xs ${
                  simulationMode === mode
                    ? 'border-primary-500 bg-primary-50 text-primary-700'
                    : 'border-gray-200 text-gray-600 hover:bg-gray-100'
                }`}
              >
                {MODE_LABELS[mode]}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-4 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-gray-500">Domain Pack:</span>
              <span className="font-medium">
                {simulationMode === 'domain_pack'
                  ? selectedDomainPack?.name || 'Not selected'
                  : 'n/a for this mode'}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-gray-500">Max Scenarios:</span>
              <span className="font-medium">{runConfig.maxScenarios}</span>
            </div>
          </div>
        </div>
      )}

      <div className="flex items-end gap-2">
        <button
          type="button"
          onClick={() => setShowQuickControls(!showQuickControls)}
          className={`btn-ghost p-2 ${showQuickControls ? 'text-primary-600' : 'text-gray-400 hover:text-gray-600'}`}
          title="Quick controls"
          aria-label="Toggle quick controls"
          aria-expanded={showQuickControls}
        >
          <Settings2 className="w-5 h-5" />
        </button>

        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              adjustTextareaHeight();
            }}
            onKeyDown={handleKeyDown}
            placeholder="Describe your optimization goal..."
            rows={1}
            disabled={isStreaming}
            className="w-full resize-none rounded-xl border border-gray-300 bg-white px-4 py-3 pr-12 text-sm focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20 disabled:opacity-50"
          />
        </div>

        <button
          type="button"
          onClick={handleSubmit}
          disabled={!input.trim() || isStreaming}
          className="btn-primary p-3 rounded-xl"
          aria-label="Send message"
        >
          {isStreaming ? (
            <Loader2 className="w-5 h-5 animate-spin" />
          ) : (
            <Send className="w-5 h-5" />
          )}
        </button>
      </div>

      <p className="mt-2 text-xs text-gray-400 text-center">
        Mode: {MODE_LABELS[simulationMode]} · Enter to send · gear for options
      </p>
    </div>
  );
}
