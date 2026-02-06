// Run Status
export type RunStatus = 'idle' | 'running' | 'completed' | 'failed';

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
  domain_pack: string;
  domain_pack_version: string;
  objective_spec: ObjectiveSpec;
  created_at: string;
  updated_at: string;
  stages: StageStatus[];
  counters: RunCounters;
  current_best?: ScenarioResult;
  candidates: ScenarioResult[];
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
  passed?: boolean;
  credibility_weight: number;
  context_tags: string[];
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

// SSE Events
export interface SSEEvent {
  type: 'stage_update' | 'scenario_result' | 'best_changed' | 'run_completed' | 'error';
  run_id: string;
  data: unknown;
}
