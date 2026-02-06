'use client';

import { cn, formatNumber, truncate } from '@/lib/utils';
import { useAppStore } from '@/store';
import {
    AlertTriangle,
    CheckCircle,
    ChevronDown,
    ChevronRight,
    ExternalLink,
    FileText,
    Shield
} from 'lucide-react';
import { useState } from 'react';

export function EvidenceTab() {
  const { evidenceChunks, benchmarks, currentRun } = useAppStore();
  const [expandedChunk, setExpandedChunk] = useState<string | null>(null);
  const [expandedBenchmark, setExpandedBenchmark] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<'evidence' | 'benchmarks'>('evidence');

  return (
    <div className="flex-1 overflow-hidden flex flex-col">
      {/* Section Toggle */}
      <div className="flex items-center gap-2 p-4 border-b border-gray-200">
        <button
          onClick={() => setActiveSection('evidence')}
          className={cn(
            'px-4 py-2 text-sm font-medium rounded-lg transition-colors',
            activeSection === 'evidence'
              ? 'bg-primary-600 text-white'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          )}
        >
          Evidence Pack ({evidenceChunks.length})
        </button>
        <button
          onClick={() => setActiveSection('benchmarks')}
          className={cn(
            'px-4 py-2 text-sm font-medium rounded-lg transition-colors',
            activeSection === 'benchmarks'
              ? 'bg-primary-600 text-white'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          )}
        >
          Benchmarks ({benchmarks.length})
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {/* Evidence Section */}
        {activeSection === 'evidence' && (
          <div className="space-y-3">
            {evidenceChunks.length === 0 ? (
              <div className="text-center text-gray-500 py-8">
                <FileText className="w-12 h-12 mx-auto mb-3 text-gray-300" />
                <p>No evidence chunks available</p>
                <p className="text-sm mt-1">Evidence will appear when a run uses the evidence service</p>
              </div>
            ) : (
              evidenceChunks.map((chunk, index) => (
                <div 
                  key={chunk.chunk_id}
                  className="card p-4"
                >
                  <button
                    onClick={() => setExpandedChunk(
                      expandedChunk === chunk.chunk_id ? null : chunk.chunk_id
                    )}
                    className="w-full flex items-start gap-3 text-left"
                  >
                    <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-primary-100 flex items-center justify-center text-primary-600 font-medium text-sm">
                      {index + 1}
                    </div>
                    
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-gray-900">
                          {chunk.source}
                        </span>
                        {chunk.has_conflicts && (
                          <span className="badge badge-warning gap-1">
                            <AlertTriangle className="w-3 h-3" />
                            Conflicts
                          </span>
                        )}
                      </div>
                      
                      <p className="text-sm text-gray-600 mt-1">
                        {expandedChunk === chunk.chunk_id 
                          ? chunk.content 
                          : truncate(chunk.content, 150)
                        }
                      </p>
                      
                      <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                        <span>Relevance: {formatNumber(chunk.score, 2)}</span>
                        <span className="font-mono">{chunk.document_id}</span>
                      </div>
                    </div>

                    {expandedChunk === chunk.chunk_id ? (
                      <ChevronDown className="w-5 h-5 text-gray-400" />
                    ) : (
                      <ChevronRight className="w-5 h-5 text-gray-400" />
                    )}
                  </button>
                </div>
              ))
            )}
          </div>
        )}

        {/* Benchmarks Section */}
        {activeSection === 'benchmarks' && (
          <div className="space-y-3">
            {benchmarks.length === 0 ? (
              <div className="text-center text-gray-500 py-8">
                <Shield className="w-12 h-12 mx-auto mb-3 text-gray-300" />
                <p>No benchmarks applied</p>
                <p className="text-sm mt-1">Benchmarks will appear when scoring is complete</p>
              </div>
            ) : (
              benchmarks.map((benchmark) => (
                <div 
                  key={benchmark.id}
                  className="card p-4"
                >
                  <button
                    onClick={() => setExpandedBenchmark(
                      expandedBenchmark === benchmark.id ? null : benchmark.id
                    )}
                    className="w-full flex items-start gap-3 text-left"
                  >
                    <div className="flex-shrink-0">
                      {benchmark.passed ? (
                        <CheckCircle className="w-6 h-6 text-green-500" />
                      ) : (
                        <AlertTriangle className="w-6 h-6 text-red-500" />
                      )}
                    </div>
                    
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-gray-900">
                          {benchmark.name}
                        </span>
                        <span className={cn(
                          'badge',
                          benchmark.passed ? 'badge-success' : 'badge-error'
                        )}>
                          {benchmark.passed ? 'PASS' : 'FAIL'}
                        </span>
                      </div>
                      
                      <div className="flex items-center gap-4 mt-2 text-sm text-gray-600">
                        <span>
                          {benchmark.metric_name} {benchmark.threshold_type} {benchmark.threshold_value}
                        </span>
                      </div>

                      {expandedBenchmark === benchmark.id && (
                        <div className="mt-4 p-3 bg-gray-50 rounded-lg space-y-2">
                          <div className="flex items-center justify-between text-sm">
                            <span className="text-gray-500">Credibility Weight</span>
                            <span className="font-medium">{formatNumber(benchmark.credibility_weight, 2)}</span>
                          </div>
                          
                          {benchmark.context_tags.length > 0 && (
                            <div className="flex items-center gap-2">
                              <span className="text-sm text-gray-500">Context:</span>
                              <div className="flex flex-wrap gap-1">
                                {benchmark.context_tags.map((tag) => (
                                  <span 
                                    key={tag}
                                    className="px-2 py-0.5 bg-gray-200 rounded text-xs text-gray-700"
                                  >
                                    {tag}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                          
                          <button className="flex items-center gap-1 text-sm text-primary-600 hover:text-primary-700">
                            View source <ExternalLink className="w-3 h-3" />
                          </button>
                        </div>
                      )}
                    </div>

                    {expandedBenchmark === benchmark.id ? (
                      <ChevronDown className="w-5 h-5 text-gray-400" />
                    ) : (
                      <ChevronRight className="w-5 h-5 text-gray-400" />
                    )}
                  </button>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}
