import type {
    Benchmark,
    ChatMessage,
    DomainPack,
    EvidenceChunk,
    HeatmapLayer,
    HeatmapMask,
    Project,
    Run,
    RunStatus,
    ScenarioResult,
    StageStatus,
} from '@/types';
import { create } from 'zustand';

interface AppState {
  // Projects & Domain Packs
  projects: Project[];
  selectedProject: Project | null;
  domainPacks: DomainPack[];
  selectedDomainPack: DomainPack | null;
  
  // Run Configuration
  runConfig: {
    maxScenarios: number;
    maxWallTime: number;
    fidelityPolicy: 'cheap_first' | 'balanced' | 'high_only';
  };
  
  // Current Run
  currentRun: Run | null;
  runStatus: RunStatus;
  
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
  setSelectedProject: (project: Project | null) => void;
  setSelectedDomainPack: (pack: DomainPack | null) => void;
  setRunConfig: (config: Partial<AppState['runConfig']>) => void;
  
  setCurrentRun: (run: Run | null) => void;
  updateRunStage: (stage: StageStatus) => void;
  updateRunCounters: (counters: Partial<Run['counters']>) => void;
  addScenarioResult: (result: ScenarioResult) => void;
  setCurrentBest: (result: ScenarioResult) => void;
  
  addMessage: (message: ChatMessage) => void;
  updateMessage: (id: string, updates: Partial<ChatMessage>) => void;
  setStreaming: (streaming: boolean) => void;
  
  setActiveTab: (tab: string) => void;
  setSelectedScenario: (scenario: ScenarioResult | null) => void;
  
  setEvidenceChunks: (chunks: EvidenceChunk[]) => void;
  setBenchmarks: (benchmarks: Benchmark[]) => void;
  
  setHeatmapLayers: (baseline: HeatmapLayer | null, scenario: HeatmapLayer | null) => void;
  toggleHeatmapMask: (type: HeatmapMask['type']) => void;
  setHeatmapMaskValue: (type: HeatmapMask['type'], value: number) => void;
  
  reset: () => void;
}

const initialMasks: HeatmapMask[] = [
  { type: 'threshold', value: 0, enabled: false },
  { type: 'delta', value: 0, enabled: true },
  { type: 'topk', value: 10, enabled: false },
  { type: 'constraint', value: 0, enabled: false },
  { type: 'confidence', value: 0.8, enabled: false },
];

export const useAppStore = create<AppState>((set, get) => ({
  // Initial state
  projects: [],
  selectedProject: null,
  domainPacks: [],
  selectedDomainPack: null,
  
  runConfig: {
    maxScenarios: 100,
    maxWallTime: 3600,
    fidelityPolicy: 'cheap_first',
  },
  
  currentRun: null,
  runStatus: 'idle',
  
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
  setSelectedProject: (project) => set({ selectedProject: project }),
  setSelectedDomainPack: (pack) => set({ selectedDomainPack: pack }),
  setRunConfig: (config) => set((state) => ({
    runConfig: { ...state.runConfig, ...config },
  })),
  
  setCurrentRun: (run) => set({
    currentRun: run,
    runStatus: run?.status || 'idle',
  }),
  
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
  
  reset: () => set({
    currentRun: null,
    runStatus: 'idle',
    messages: [],
    selectedScenario: null,
    evidenceChunks: [],
    benchmarks: [],
    baselineHeatmap: null,
    scenarioHeatmap: null,
    deltaHeatmap: null,
    heatmapMasks: initialMasks,
  }),
}));
