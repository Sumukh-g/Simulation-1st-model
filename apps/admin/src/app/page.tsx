'use client';

import {
    AlertTriangle,
    Check,
    CheckCircle,
    ChevronRight,
    Database,
    FileText,
    History,
    Package,
    Pencil,
    Play,
    Plus,
    Shield,
    Trash2,
    X
} from 'lucide-react';
import { useState } from 'react';

type Section = 'benchmarks' | 'rubrics' | 'packs' | 'audit' | 'simulate';

interface Benchmark {
  id: string;
  name: string;
  metric_name: string;
  threshold_value: number;
  threshold_type: 'min' | 'max' | 'target';
  context_tags: string[];
  credibility_weight: number;
  source_id: string;
}

interface Rubric {
  id: string;
  name: string;
  version: string;
  status: 'draft' | 'pending' | 'approved';
  metric_weights: Record<string, number>;
}

interface DomainPack {
  id: string;
  name: string;
  version: string;
  certified: boolean;
  description: string;
}

interface AuditEntry {
  id: string;
  timestamp: string;
  user: string;
  action: string;
  resource: string;
  details: string;
}

export default function AdminPage() {
  const [activeSection, setActiveSection] = useState<Section>('benchmarks');
  const [editingId, setEditingId] = useState<string | null>(null);

  // Mock data
  const [benchmarks] = useState<Benchmark[]>([
    { id: 'b1', name: 'Min ROI', metric_name: 'roi', threshold_value: 0.05, threshold_type: 'min', context_tags: ['finance'], credibility_weight: 0.9, source_id: 'src-1' },
    { id: 'b2', name: 'Max Risk', metric_name: 'risk', threshold_value: 0.3, threshold_type: 'max', context_tags: ['finance', 'risk'], credibility_weight: 0.85, source_id: 'src-2' },
    { id: 'b3', name: 'Coverage Target', metric_name: 'coverage', threshold_value: 0.8, threshold_type: 'min', context_tags: ['spatial'], credibility_weight: 0.95, source_id: 'src-3' },
  ]);

  const [rubrics] = useState<Rubric[]>([
    { id: 'r1', name: 'Impact Assessment', version: '1.2', status: 'approved', metric_weights: { impact: 0.4, cost: 0.3, feasibility: 0.3 } },
    { id: 'r2', name: 'Risk-Adjusted Return', version: '2.0', status: 'pending', metric_weights: { return: 0.5, risk: 0.3, liquidity: 0.2 } },
    { id: 'r3', name: 'Spatial Efficiency', version: '1.0', status: 'draft', metric_weights: { coverage: 0.5, cost: 0.3, time: 0.2 } },
  ]);

  const [packs] = useState<DomainPack[]>([
    { id: 'p1', name: 'SpatialPack', version: '1.0.0', certified: true, description: 'Spatial simulation for urban planning' },
    { id: 'p2', name: 'FinancePack', version: '1.0.0', certified: true, description: 'Financial modeling and optimization' },
    { id: 'p3', name: 'ToyPack', version: '1.0.0', certified: false, description: 'Demo pack for testing' },
  ]);

  const [auditLog] = useState<AuditEntry[]>([
    { id: 'a1', timestamp: new Date().toISOString(), user: 'admin@gsip.io', action: 'UPDATE', resource: 'rubric/r1', details: 'Updated version to 1.2' },
    { id: 'a2', timestamp: new Date(Date.now() - 3600000).toISOString(), user: 'admin@gsip.io', action: 'CREATE', resource: 'benchmark/b3', details: 'Created Coverage Target benchmark' },
    { id: 'a3', timestamp: new Date(Date.now() - 86400000).toISOString(), user: 'system', action: 'APPROVE', resource: 'pack/p1', details: 'Certified SpatialPack v1.0.0' },
  ]);

  const sidebarItems = [
    { id: 'benchmarks', label: 'Benchmarks', icon: Database },
    { id: 'rubrics', label: 'Rubrics', icon: FileText },
    { id: 'packs', label: 'Domain Packs', icon: Package },
    { id: 'audit', label: 'Audit Log', icon: History },
    { id: 'simulate', label: 'Simulate Preview', icon: Play },
  ];

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-64 bg-gray-900 text-white">
        <div className="p-4 border-b border-gray-700">
          <div className="flex items-center gap-2">
            <Shield className="w-8 h-8 text-primary-500" />
            <div>
              <h1 className="font-bold text-lg">GSIP Admin</h1>
              <p className="text-xs text-gray-400">Administration Console</p>
            </div>
          </div>
        </div>

        <nav className="p-4 space-y-1">
          {sidebarItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeSection === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveSection(item.id as Section)}
                className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-primary-600 text-white'
                    : 'text-gray-300 hover:bg-gray-800'
                }`}
              >
                <Icon className="w-5 h-5" />
                {item.label}
                {isActive && <ChevronRight className="w-4 h-4 ml-auto" />}
              </button>
            );
          })}
        </nav>
      </aside>

      {/* Main Content */}
      <main className="flex-1 p-8">
        {/* Benchmarks Section */}
        {activeSection === 'benchmarks' && (
          <div>
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-2xl font-bold text-gray-900">Benchmark Sources & Benchmarks</h2>
              <button className="btn-primary gap-2">
                <Plus className="w-4 h-4" />
                Add Benchmark
              </button>
            </div>

            <div className="card overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr>
                    <th className="table-header">Name</th>
                    <th className="table-header">Metric</th>
                    <th className="table-header">Threshold</th>
                    <th className="table-header">Context Tags</th>
                    <th className="table-header">Credibility</th>
                    <th className="table-header">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {benchmarks.map((b) => (
                    <tr key={b.id} className="hover:bg-gray-50">
                      <td className="table-cell font-medium">{b.name}</td>
                      <td className="table-cell font-mono text-sm">{b.metric_name}</td>
                      <td className="table-cell">
                        <span className="px-2 py-1 bg-gray-100 rounded text-xs">
                          {b.threshold_type} {b.threshold_value}
                        </span>
                      </td>
                      <td className="table-cell">
                        <div className="flex gap-1">
                          {b.context_tags.map((tag) => (
                            <span key={tag} className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs">
                              {tag}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="table-cell">{b.credibility_weight}</td>
                      <td className="table-cell">
                        <div className="flex gap-2">
                          <button className="p-1 hover:bg-gray-100 rounded">
                            <Pencil className="w-4 h-4 text-gray-500" />
                          </button>
                          <button className="p-1 hover:bg-red-100 rounded">
                            <Trash2 className="w-4 h-4 text-red-500" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Rubrics Section */}
        {activeSection === 'rubrics' && (
          <div>
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-2xl font-bold text-gray-900">Rubric Editor</h2>
              <button className="btn-primary gap-2">
                <Plus className="w-4 h-4" />
                New Rubric
              </button>
            </div>

            <div className="grid gap-4">
              {rubrics.map((r) => (
                <div key={r.id} className="card p-4">
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-gray-900">{r.name}</h3>
                        <span className="text-sm text-gray-500">v{r.version}</span>
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                          r.status === 'approved' ? 'bg-green-100 text-green-700' :
                          r.status === 'pending' ? 'bg-yellow-100 text-yellow-700' :
                          'bg-gray-100 text-gray-700'
                        }`}>
                          {r.status}
                        </span>
                      </div>
                      <div className="mt-2 flex gap-2">
                        {Object.entries(r.metric_weights).map(([metric, weight]) => (
                          <span key={metric} className="text-sm text-gray-600">
                            {metric}: {(weight * 100).toFixed(0)}%
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      {r.status === 'draft' && (
                        <button className="btn-secondary text-xs gap-1">
                          <Check className="w-3 h-3" />
                          Submit for Approval
                        </button>
                      )}
                      {r.status === 'pending' && (
                        <>
                          <button className="btn-primary text-xs gap-1">
                            <Check className="w-3 h-3" />
                            Approve
                          </button>
                          <button className="btn-danger text-xs gap-1">
                            <X className="w-3 h-3" />
                            Reject
                          </button>
                        </>
                      )}
                      <button className="btn-secondary text-xs gap-1">
                        <Pencil className="w-3 h-3" />
                        Edit
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Domain Packs Section */}
        {activeSection === 'packs' && (
          <div>
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-2xl font-bold text-gray-900">Domain Pack Registry</h2>
            </div>

            <div className="grid gap-4">
              {packs.map((p) => (
                <div key={p.id} className="card p-4">
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-4">
                      <div className={`w-12 h-12 rounded-lg flex items-center justify-center ${
                        p.certified ? 'bg-green-100' : 'bg-yellow-100'
                      }`}>
                        {p.certified ? (
                          <CheckCircle className="w-6 h-6 text-green-600" />
                        ) : (
                          <AlertTriangle className="w-6 h-6 text-yellow-600" />
                        )}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="font-semibold text-gray-900">{p.name}</h3>
                          <span className="text-sm text-gray-500">v{p.version}</span>
                        </div>
                        <p className="text-sm text-gray-600 mt-1">{p.description}</p>
                        <span className={`inline-block mt-2 px-2 py-0.5 rounded text-xs font-medium ${
                          p.certified ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'
                        }`}>
                          {p.certified ? 'Certified' : 'Pending Certification'}
                        </span>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      {!p.certified && (
                        <button className="btn-primary text-xs gap-1">
                          <Check className="w-3 h-3" />
                          Certify
                        </button>
                      )}
                      <button className="btn-secondary text-xs gap-1">
                        View Details
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Audit Log Section */}
        {activeSection === 'audit' && (
          <div>
            <h2 className="text-2xl font-bold text-gray-900 mb-6">Audit Log</h2>

            <div className="card overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr>
                    <th className="table-header">Timestamp</th>
                    <th className="table-header">User</th>
                    <th className="table-header">Action</th>
                    <th className="table-header">Resource</th>
                    <th className="table-header">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {auditLog.map((entry) => (
                    <tr key={entry.id} className="hover:bg-gray-50">
                      <td className="table-cell text-sm text-gray-500">
                        {new Date(entry.timestamp).toLocaleString()}
                      </td>
                      <td className="table-cell font-medium">{entry.user}</td>
                      <td className="table-cell">
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                          entry.action === 'CREATE' ? 'bg-green-100 text-green-700' :
                          entry.action === 'UPDATE' ? 'bg-blue-100 text-blue-700' :
                          entry.action === 'DELETE' ? 'bg-red-100 text-red-700' :
                          'bg-purple-100 text-purple-700'
                        }`}>
                          {entry.action}
                        </span>
                      </td>
                      <td className="table-cell font-mono text-sm">{entry.resource}</td>
                      <td className="table-cell text-sm text-gray-600">{entry.details}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Simulate Preview Section */}
        {activeSection === 'simulate' && (
          <div>
            <h2 className="text-2xl font-bold text-gray-900 mb-6">Simulate Preview</h2>
            <p className="text-gray-600 mb-6">
              Run a quick cheap-fidelity simulation to validate domain packs and scenarios.
            </p>

            <div className="card p-6 max-w-2xl">
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Domain Pack
                  </label>
                  <select className="input">
                    {packs.map((p) => (
                      <option key={p.id} value={p.id}>{p.name} v{p.version}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Scenario JSON
                  </label>
                  <textarea
                    className="input font-mono text-sm"
                    rows={8}
                    placeholder='{"state": {...}, "actions": {...}}'
                    defaultValue={JSON.stringify({
                      state: { x: 0, y: 0, target_x: 10, target_y: 10 },
                      actions: { dx: 1, dy: 1, steps: 10 },
                    }, null, 2)}
                  />
                </div>

                <div className="flex gap-2">
                  <button className="btn-primary gap-2">
                    <Play className="w-4 h-4" />
                    Run Simulation
                  </button>
                  <button className="btn-secondary">
                    Load Example
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
