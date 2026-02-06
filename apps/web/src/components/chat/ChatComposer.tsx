'use client';

import { generateId } from '@/lib/utils';
import { useAppStore } from '@/store';
import { Loader2, Paperclip, Send, Settings2 } from 'lucide-react';
import { KeyboardEvent, useCallback, useRef, useState } from 'react';

export function ChatComposer() {
  const [input, setInput] = useState('');
  const [showQuickControls, setShowQuickControls] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  
  const {
    isStreaming,
    addMessage,
    setStreaming,
    selectedDomainPack,
    runConfig,
    setCurrentRun,
  } = useAppStore();

  const handleSubmit = useCallback(async () => {
    if (!input.trim() || isStreaming) return;

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
      // Create assistant message placeholder
      const assistantMessageId = generateId();
      addMessage({
        id: assistantMessageId,
        role: 'assistant',
        content: 'Starting simulation run...',
        timestamp: new Date().toISOString(),
        streaming: true,
      });

      // Send to backend
      const response = await fetch('/api/runs/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: input.trim(),
          domain_pack: selectedDomainPack?.name,
          config: runConfig,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to start run');
      }

      const run = await response.json();
      setCurrentRun(run);

      // Update assistant message with run card
      const { updateMessage } = useAppStore.getState();
      updateMessage(assistantMessageId, {
        content: `I'll help you find the best intervention using ${run.domain_pack}. The optimization run has started.`,
        streaming: false,
        run_card: {
          run_id: run.id,
          status: 'running',
          objective_summary: run.objective_spec?.description || input.trim(),
          domain_pack: run.domain_pack,
        },
      });

    } catch (error) {
      console.error('Failed to start run:', error);
      addMessage({
        id: generateId(),
        role: 'system',
        content: 'Failed to start simulation run. Please try again.',
        timestamp: new Date().toISOString(),
      });
    } finally {
      setStreaming(false);
    }
  }, [input, isStreaming, addMessage, setStreaming, selectedDomainPack, runConfig, setCurrentRun]);

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
      {/* Quick Controls */}
      {showQuickControls && (
        <div className="mb-3 p-3 bg-gray-50 rounded-lg border border-gray-200">
          <div className="flex items-center gap-4 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-gray-500">Domain Pack:</span>
              <span className="font-medium">{selectedDomainPack?.name || 'Not selected'}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-gray-500">Max Scenarios:</span>
              <span className="font-medium">{runConfig.maxScenarios}</span>
            </div>
          </div>
        </div>
      )}

      <div className="flex items-end gap-2">
        {/* Attachment Button */}
        <button
          className="btn-ghost p-2 text-gray-400 hover:text-gray-600"
          title="Attach dataset"
        >
          <Paperclip className="w-5 h-5" />
        </button>

        {/* Quick Controls Toggle */}
        <button
          onClick={() => setShowQuickControls(!showQuickControls)}
          className={`btn-ghost p-2 ${showQuickControls ? 'text-primary-600' : 'text-gray-400 hover:text-gray-600'}`}
          title="Quick controls"
        >
          <Settings2 className="w-5 h-5" />
        </button>

        {/* Input */}
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

        {/* Send Button */}
        <button
          onClick={handleSubmit}
          disabled={!input.trim() || isStreaming}
          className="btn-primary p-3 rounded-xl"
        >
          {isStreaming ? (
            <Loader2 className="w-5 h-5 animate-spin" />
          ) : (
            <Send className="w-5 h-5" />
          )}
        </button>
      </div>

      <p className="mt-2 text-xs text-gray-400 text-center">
        Press Enter to send, Shift+Enter for new line
      </p>
    </div>
  );
}
