'use client';

import { cn, getStatusColor } from '@/lib/utils';
import type { RunCard, RunStatus } from '@/types';
import { CheckCircle, Clock, Loader2, Play, XCircle } from 'lucide-react';

interface RunCardEmbedProps {
  card: RunCard;
}

const STATUS_ICONS: Record<RunStatus, JSX.Element> = {
  idle: <Play className="w-4 h-4" />,
  running: <Loader2 className="w-4 h-4 animate-spin" />,
  completed: <CheckCircle className="w-4 h-4" />,
  failed: <XCircle className="w-4 h-4" />,
  awaiting_input: <Clock className="w-4 h-4" />,
};

const STATUS_LABELS: Record<RunStatus, string> = {
  idle: 'Idle',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  awaiting_input: 'Awaiting input',
};

export function RunCardEmbed({ card }: RunCardEmbedProps) {

  return (
    <div className="bg-gradient-to-r from-primary-50 to-blue-50 border border-primary-200 rounded-xl p-4">
      <div className="flex items-start gap-3">
        <div
          className={cn(
            'w-10 h-10 rounded-lg flex items-center justify-center',
            card.status === 'running' ? 'bg-blue-100' : 'bg-primary-100'
          )}
        >
          <div className={getStatusColor(card.status)}>
            {STATUS_ICONS[card.status]}
          </div>
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-semibold text-gray-900">
              Run Started
            </span>
            <span className="text-xs font-mono text-gray-500">{card.run_id}</span>
          </div>

          <p className="text-sm text-gray-600 mb-2">{card.objective_summary}</p>

          <div className="flex items-center gap-3 text-xs">
            <span className="flex items-center gap-1 text-gray-500">
              <span className="font-medium">Domain:</span>
              <span className="px-1.5 py-0.5 bg-white rounded text-gray-700">
                {card.domain_pack}
              </span>
            </span>

            <span
              className={cn(
                'flex items-center gap-1 px-2 py-0.5 rounded-full',
                card.status === 'running'
                  ? 'bg-blue-100 text-blue-700'
                  : card.status === 'completed'
                  ? 'bg-green-100 text-green-700'
                  : card.status === 'failed'
                  ? 'bg-red-100 text-red-700'
                  : card.status === 'awaiting_input'
                  ? 'bg-amber-100 text-amber-700'
                  : 'bg-gray-100 text-gray-700'
              )}
            >
              {STATUS_ICONS[card.status]}
              <span>{STATUS_LABELS[card.status]}</span>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
