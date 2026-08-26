import type {
    Benchmark,
    ChatMessage,
    DomainPack,
    EvidenceChunk,
    HeatmapLayer,
    HeatmapMask,
    Project,
    Run,
    RunListItem,
    RunStatus,
    ScenarioResult,
    SimulationMode,
    StageStatus,
} from '@/types';
import { create } from 'zustand';

interface AppState {
  // Projects & Domain Packs
  projects: Project[];
  selectedProject: Project | null;
  domainPacks: DomainPack[];
  selectedDomainPack: DomainPack | null;
  simulationMode: SimulationMode;
  
  // Run Configuration
  runConfig: {
    maxScenarios: number;
    maxWallTime: number;
    fidelityPolicy: 'cheap_first' | 'balanced' | 'high_only';
  };
  
  // Current Run
  currentRun: Run | null;
  runStatus: RunStatus;
  runHistory: RunListItem[];
  historyLoading: boolean;
  historyOpen: boolean;
  
  // Chat
  messages: ChatMessage[];
  isStreaming: boolean;
  
  // Workspace
  activeTab: string;
  selectedScenario: ScenarioResult | null;
  
  // Evidence
  evidenceChunks: EvidenceChunk[];
  benchmarks: Benchmark[];
  
  // Heatmaps
  baselineHeatmap: HeatmapLayer | null;
  scenarioHeatmap: HeatmapLayer | null;
  deltaHeatmap: HeatmapLayer | null;
  heatmapMasks: HeatmapMask[];
  
  // Actions
  setProjects: (projects: Project[]) => void;
  setSelectedProject: (project: Project | null) => void;
  setSelectedDomainPack: (pack: DomainPack | null) => void;
  setSimulationMode: (mode: SimulationMode) => void;
  setRunConfig: (config: Partial<AppState['runConfig']>) => void;
  
  setCurrentRun: (run: Run | null) => void;
  setRunHistory: (runs: RunListItem[]) => void;
  setHistoryLoading: (loading: boolean) => void;
  setHistoryOpen: (open: boolean) => void;
  updateRunStage: (stage: StageStatus) => void;
  updateRunCounters: (counters: Partial<Run['counters']>) => void;
  addScenarioResult: (result: ScenarioResult) => void;
  setCandidates: (results: ScenarioResult[]) => void;
  setCurrentBest: (result: ScenarioResult) => void;
  
  addMessage: (message: ChatMessage) => void;
  updateMessage: (id: string, updates: Partial<ChatMessage>) => void;
  setMessages: (messages: ChatMessage[]) => void;
  setStreaming: (streaming: boolean) => void;
  
  setActiveTab: (tab: string) => void;
  setSelectedScenario: (scenario: ScenarioResult | null) => void;
  
  setEvidenceChunks: (chunks: EvidenceChunk[]) => void;
  setBenchmarks: (benchmarks: Benchmark[]) => void;
  
  setHeatmapLayers: (baseline: HeatmapLayer | null, scenario: HeatmapLayer | null) => void;
  toggleHeatmapMask: (type: HeatmapMask['type']) => void;
  setHeatmapMaskValue: (type: HeatmapMask['type'], value: number) => void;
  
  /** Clear the open chat/run without wiping project/pack selection. */
  startNewChat: () => void;
  reset: () => void;
}

const initialMasks: HeatmapMask[] = [
  { type: 'threshold', value: 0, enabled: false },
  { type: 'delta', value: 0, enabled: true },
  { type: 'topk', value: 10, enabled: false },
  { type: 'constraint', value: 0, enabled: false },
  { type: 'confidence', value: 0.8, enabled: false },
];

const emptyWorkspace = {
  currentRun: null as Run | null,
  runStatus: 'idle' as RunStatus,
  messages: [] as ChatMessage[],
  selectedScenario: null as ScenarioResult | null,
  evidenceChunks: [] as EvidenceChunk[],
  benchmarks: [] as Benchmark[],
  baselineHeatmap: null as HeatmapLayer | null,
  scenarioHeatmap: null as HeatmapLayer | null,
  deltaHeatmap: null as HeatmapLayer | null,
  heatmapMasks: initialMasks,
};

export const useAppStore = create<AppState>((set, get) => ({
  // Initial state
  projects: [],
  selectedProject: null,
  domainPacks: [],
  selectedDomainPack: null,
  simulationMode: 'domain_pack',
  
  runConfig: {
    maxScenarios: 100,
    maxWallTime: 3600,
    fidelityPolicy: 'cheap_first',
  },
  
  currentRun: null,
  runStatus: 'idle',
  runHistory: [],
  historyLoading: false,
  historyOpen: true,
  
  messages: [],
  isStreaming: false,
  
  activeTab: 'overview',
  selectedScenario: null,
  
  evidenceChunks: [],
  benchmarks: [],
  
  baselineHeatmap: null,
  scenarioHeatmap: null,
  deltaHeatmap: null,
  heatmapMasks: initialMasks,
  
  // Actions
  setProjects: (projects) => set({ projects }),
  setSelectedProject: (project) => set({ selectedProject: project }),
  setSelectedDomainPack: (pack) => set({ selectedDomainPack: pack }),
  setSimulationMode: (mode) => set({ simulationMode: mode }),
  setRunConfig: (config) => set((state) => ({
    runConfig: { ...state.runConfig, ...config },
  })),
  
  setCurrentRun: (run) => set({
    currentRun: run,
    runStatus: (run?.status as RunStatus) || 'idle',
  }),

  setRunHistory: (runs) => set({ runHistory: runs }),
  setHistoryLoading: (loading) => set({ historyLoading: loading }),
  setHistoryOpen: (open) => set({ historyOpen: open }),
  
  updateRunStage: (stage) => set((state) => {
    if (!state.currentRun) return state;
    const stages = state.currentRun.stages.map((s) =>
      s.stage === stage.stage ? stage : s
    );
    return {
      currentRun: { ...state.currentRun, stages },
    };
  }),
  
  updateRunCounters: (counters) => set((state) => {
    if (!state.currentRun) return state;
    return {
      currentRun: {
        ...state.currentRun,
        counters: { ...state.currentRun.counters, ...counters },
      },
    };
  }),
  
  addScenarioResult: (result) => set((state) => {
    if (!state.currentRun) return state;
    const candidates = [...state.currentRun.candidates, result];
    // Sort by judge score descending
    candidates.sort((a, b) => (b.judge_score?.score || 0) - (a.judge_score?.score || 0));
    return {
      currentRun: { ...state.currentRun, candidates },
    };
  }),

  setCandidates: (results) => set((state) => {
    if (!state.currentRun) return state;
    const candidates = [...results].sort(
      (a, b) => (b.judge_score?.score || 0) - (a.judge_score?.score || 0)
    );
    return {
      currentRun: { ...state.currentRun, candidates },
    };
  }),
  
  setCurrentBest: (result) => set((state) => {
    if (!state.currentRun) return state;
    return {
      currentRun: { ...state.currentRun, current_best: result },
    };
  }),
  
  addMessage: (message) => set((state) => ({
    messages: [...state.messages, message],
  })),
  
  updateMessage: (id, updates) => set((state) => ({
    messages: state.messages.map((m) =>
      m.id === id ? { ...m, ...updates } : m
    ),
  })),

  setMessages: (messages) => set({ messages }),
  
  setStreaming: (streaming) => set({ isStreaming: streaming }),
  
  setActiveTab: (tab) => set({ activeTab: tab }),
  setSelectedScenario: (scenario) => set({ selectedScenario: scenario }),
  
  setEvidenceChunks: (chunks) => set({ evidenceChunks: chunks }),
  setBenchmarks: (benchmarks) => set({ benchmarks }),
  
  setHeatmapLayers: (baseline, scenario) => {
    let delta: HeatmapLayer | null = null;
    if (baseline && scenario && baseline.data.length === scenario.data.length) {
      const deltaData = baseline.data.map((row, i) =>
        row.map((val, j) => scenario.data[i][j] - val)
      );
      const flatDelta = deltaData.flat();
      delta = {
        name: 'Delta',
        data: deltaData,
        min: Math.min(...flatDelta),
        max: Math.max(...flatDelta),
        unit: baseline.unit,
      };
    }
    set({ baselineHeatmap: baseline, scenarioHeatmap: scenario, deltaHeatmap: delta });
  },
  
  toggleHeatmapMask: (type) => set((state) => ({
    heatmapMasks: state.heatmapMasks.map((m) =>
      m.type === type ? { ...m, enabled: !m.enabled } : m
    ),
  })),
  
  setHeatmapMaskValue: (type, value) => set((state) => ({
    heatmapMasks: state.heatmapMasks.map((m) =>
      m.type === type ? { ...m, value } : m
    ),
  })),

  startNewChat: () => set({
    ...emptyWorkspace,
    isStreaming: false,
    activeTab: 'overview',
  }),
  
  reset: () => set({
    ...emptyWorkspace,
    isStreaming: false,
  }),
}));

/** Rebuild a minimal chat thread from a persisted run. */
export function messagesFromRun(run: Run): ChatMessage[] {
  const prompt = run.objective_spec?.description?.trim() || run.title || 'Previous run';
  const packLabel =
    run.domain_pack ||
    (run.simulation_mode === 'create_pack'
      ? 'Create domain pack'
      : run.simulation_mode === 'no_pack'
        ? 'No domain pack'
        : 'Simulation');

  let assistantContent: string;
  if (run.assistant_message) {
    assistantContent = run.assistant_message;
  } else if (run.narrative?.text) {
    assistantContent = run.narrative.text;
  } else if (run.status === 'failed') {
    assistantContent = 'This run failed. Open Logs & Debug for details, or start a new run.';
  } else if (run.status === 'awaiting_input') {
    const domain = run.classification?.domain;
    assistantContent = domain
      ? `This run is awaiting your input (domain: ${domain}). See candidate methods / draft pack in Overview.`
      : 'This run is awaiting further input.';
  } else if (run.status === 'completed') {
    const best = run.summary?.best_score;
    assistantContent =
      best != null
        ? `Run completed. Best judge score: ${best.toFixed?.(3) ?? best}.`
        : 'Run completed. See Overview and Leaderboard for results.';
  } else if (run.status === 'running') {
    assistantContent = `Run in progress using ${packLabel}.`;
  } else {
    assistantContent = `Loaded past run (${run.status}).`;
  }

  return [
    {
      id: `hist-user-${run.id}`,
      role: 'user',
      content: prompt,
      timestamp: run.created_at,
    },
    {
      id: `hist-asst-${run.id}`,
      role: 'assistant',
      content: assistantContent,
      timestamp: run.updated_at || run.created_at,
      run_card: {
        run_id: run.id,
        status: (run.status as RunStatus) || 'idle',
        objective_summary: prompt,
        domain_pack: packLabel,
      },
    },
  ];
}
