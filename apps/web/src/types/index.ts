// Run Status
export type RunStatus = 'idle' | 'running' | 'completed' | 'failed' | 'awaiting_input';

// How the run obtains its simulator
export type SimulationMode = 'domain_pack' | 'create_pack' | 'no_pack';

// Pipeline Stages
export type PipelineStage = 
  | 'formalize'
  | 'evidence'
  | 'scenarios'
  | 'simulation'
  | 'optimize'
  | 'robustness'
  | 'judge'
  | 'report';

export interface StageStatus {
  stage: PipelineStage;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress?: number;
  message?: string;
}

// Fidelity
export type FidelityLevel = 'cheap' | 'mid' | 'high';

// Scenario
export interface Scenario {
  id: string;
  run_id: string;
  state: Record<string, unknown>;
  actions: Record<string, unknown>;
  fidelity: FidelityLevel;
  seed: number;
  hash?: string;
}

// Metrics
export interface MetricResult {
  name: string;
  value: number;
  unit?: string;
  uncertainty?: {
    p10: number;
    p50: number;
    p90: number;
  };
}

// Judge Score
export type ThresholdLevel = 'unacceptable' | 'acceptable' | 'good' | 'very_good' | 'excellent';

export interface JudgeScore {
  scenario_id: string;
  score: number;
  level: ThresholdLevel;
  breakdown: {
    metric_name: string;
    raw_value: number;
    threshold_score: number;
    weight: number;
  }[];
  benchmarks_passed: number;
  benchmarks_total: number;
}

// Scenario with Results
export interface ScenarioResult extends Scenario {
  metrics: MetricResult[];
  judge_score?: JudgeScore;
  constraint_violations: string[];
  robustness_passed?: number;
  robustness_total?: number;
  confidence: number;
}

// Run
export interface Run {
  id: string;
  project_id: string;
  status: RunStatus;
  title?: string;
  domain_pack: string;
  domain_pack_version: string;
  simulation_mode?: SimulationMode;
  objective_spec: ObjectiveSpec;
  created_at: string;
  updated_at: string;
  stages: StageStatus[];
  counters: RunCounters;
  current_best?: ScenarioResult;
  candidates: ScenarioResult[];
  narrative?: RunNarrative;
  summary?: RunSummary;
  assistant_message?: string;
  classification?: {
    domain?: string;
    problem_type?: string;
    summary?: string;
  };
  candidate_methods?: Array<{
    id?: string;
    name?: string;
    why_suitable?: string;
    recommended?: boolean;
  }>;
  draft_pack?: Record<string, unknown>;
  mode_status?: string;
}

/** Lightweight row for the history sidebar (from GET /api/runs). */
export interface RunListItem {
  id: string;
  project_id?: string | null;
  status: RunStatus | 'archived' | string;
  title: string;
  prompt_preview: string;
  domain_pack: string;
  simulation_mode?: SimulationMode;
  created_at: string;
  updated_at: string;
}

// AI-generated, results-grounded executive summary of the run.
export interface RunNarrative {
  text: string;
  generated_by: string; // provider name (e.g. "groq") or "template"
}

export interface RunSummary {
  total_scenarios?: number;
  completed?: number;
  failed?: number;
  best_score?: number | null;
  best_scenario_id?: string | null;
  mean_score?: number | null;
  score_std?: number | null;
}

export interface RunCounters {
  scenarios_proposed: number;
  scenarios_simulated: number;
  scenarios_promoted: number;
  cache_hits: number;
  compute_cost: number;
  storage_cost: number;
  budget_consumed: number;
  budget_total: number;
}

export interface ObjectiveSpec {
  description: string;
  objectives: {
    name: string;
    direction: 'maximize' | 'minimize';
    weight: number;
  }[];
  constraints: {
    name: string;
    type: 'hard' | 'soft';
    threshold?: number;
  }[];
}

// Chat
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  run_card?: RunCard;
  streaming?: boolean;
}

export interface RunCard {
  run_id: string;
  status: RunStatus;
  objective_summary: string;
  domain_pack: string;
}

// Evidence
export interface EvidenceChunk {
  chunk_id: string;
  document_id: string;
  source: string;
  content: string;
  score: number;
  has_conflicts?: boolean;
}

export interface Benchmark {
  id: string;
  name: string;
  metric_name: string;
  threshold_value: number;
  threshold_type: 'min' | 'max' | 'target';
  // null/undefined => not yet evaluated against this run's results.
  passed?: boolean | null;
  credibility_weight?: number;
  context_tags?: string[];
}

// Heatmap
export interface HeatmapLayer {
  name: string;
  data: number[][];
  min: number;
  max: number;
  unit?: string;
}

export interface HeatmapMask {
  type: 'threshold' | 'delta' | 'topk' | 'constraint' | 'confidence';
  value?: number;
  enabled: boolean;
}

// Domain Pack
export interface DomainPack {
  id: string;
  name: string;
  version: string;
  description: string;
  has_spatial_output: boolean;
}

// Project
export interface Project {
  id: string;
  name: string;
  org_id: string;
}

// SSE Events. The server sends these as *named* events (event: <type>), so the
// client must use addEventListener(type) rather than onmessage.
export type SSEEventType =
  | 'stage_update'
  | 'counters_update'
  | 'scenario_result'
  | 'best_changed'
  | 'run_completed'
  | 'error';
