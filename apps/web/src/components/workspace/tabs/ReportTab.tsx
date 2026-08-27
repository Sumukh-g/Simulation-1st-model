'use client';

import { useAppStore } from '@/store';
import { Download, FileText, Loader2 } from 'lucide-react';
import { useCallback, useState } from 'react';

export function ReportTab() {
  const { currentRun } = useAppStore();
  const [downloading, setDownloading] = useState(false);

  const downloadPdf = useCallback(async () => {
    if (!currentRun?.id) return;
    if (currentRun.status !== 'completed') {
      alert('Report is available after the run completes.');
      return;
    }
    setDownloading(true);
    try {
      const res = await fetch(`/api/runs/${currentRun.id}/report.pdf`);
      if (!res.ok) {
        const detail = res.status === 404
          ? 'Report endpoint not found — restart the API server and try again.'
          : `Server returned ${res.status}`;
        throw new Error(detail);
      }
      const blob = await res.blob();
      if (!blob.size || blob.type.includes('json')) {
        throw new Error('Empty or invalid PDF response');
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `gsip-report-${currentRun.id}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error(err);
      alert(err instanceof Error ? err.message : 'Could not download report.');
    } finally {
      setDownloading(false);
    }
  }, [currentRun?.id, currentRun?.status]);

  if (!currentRun) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-500">
        No active run. Start a simulation to generate a report.
      </div>
    );
  }

  const { narrative, summary, candidates, simulation_mode, status, report_pdf } = currentRun;
  const hasResults = (candidates?.length ?? 0) > 0;
  const pdfReady = status === 'completed';

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <FileText className="w-5 h-5 text-primary-600" />
            Simulation Report
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            Structured PDF with executive summary, classification, top candidates, and recommended actions.
          </p>
        </div>
        <button
          type="button"
          onClick={downloadPdf}
          disabled={!pdfReady || downloading}
          className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg text-sm font-medium hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {downloading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
          Download PDF
        </button>
      </div>

      {simulation_mode !== 'domain_pack' && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {simulation_mode === 'no_pack'
            ? 'Illustrative run — results use an ephemeral reduced-order simulator. Validate before operational use.'
            : 'Auto-generated pack (TOY/UNVALIDATED fidelity) — confirm assumptions before production decisions.'}
        </div>
      )}

      {status === 'running' && (
        <div className="text-sm text-blue-600">Run in progress — report will be available when the pipeline completes.</div>
      )}

      {status === 'failed' && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          Run failed — no scenarios completed successfully. Try again or switch to Use existing pack with toy-pack/spatial-pack.
        </div>
      )}

      {narrative?.text && (
        <section className="card p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Executive Summary</h3>
          <p className="text-sm text-gray-700 whitespace-pre-line leading-relaxed">{narrative.text}</p>
        </section>
      )}

      {summary && (
        <section className="card p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Results at a Glance</h3>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-gray-500">Scenarios completed</dt>
              <dd className="font-medium">{summary.completed ?? 0}</dd>
            </div>
            <div>
              <dt className="text-gray-500">Best score</dt>
              <dd className="font-medium">{summary.best_score != null ? summary.best_score.toFixed(3) : '—'}</dd>
            </div>
            <div>
              <dt className="text-gray-500">Mean score</dt>
              <dd className="font-medium">{summary.mean_score != null ? summary.mean_score.toFixed(3) : '—'}</dd>
            </div>
            <div>
              <dt className="text-gray-500">Failed</dt>
              <dd className="font-medium">{summary.failed ?? 0}</dd>
            </div>
          </dl>
        </section>
      )}

      {pdfReady && currentRun.id && (
        <section className="card p-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">PDF Preview</h3>
          <iframe
            title="Report preview"
            src={`/api/runs/${currentRun.id}/report.pdf`}
            className="w-full h-[560px] rounded border border-gray-200 bg-white"
          />
        </section>
      )}

      {!hasResults && status === 'completed' && (
        <p className="text-sm text-gray-500">No ranked candidates in this run — the PDF may still include classification and summary sections.</p>
      )}
    </div>
  );
}
