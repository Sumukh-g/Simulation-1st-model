import type { ScenarioResult } from '@/types';
import { beforeEach, describe, expect, it } from 'vitest';
import { useAppStore } from './index';

describe('AppStore', () => {
  beforeEach(() => {
    useAppStore.getState().reset();
  });

  describe('Project & Domain Pack', () => {
    it('sets selected project', () => {
      const project = { id: 'p1', name: 'Test Project', org_id: 'org-1' };
      useAppStore.getState().setSelectedProject(project);
      
      expect(useAppStore.getState().selectedProject).toEqual(project);
    });

    it('sets selected domain pack', () => {
      const pack = {
        id: 'dp1',
        name: 'TestPack',
        version: '1.0',
        description: 'Test',
        has_spatial_output: false,
      };
      useAppStore.getState().setSelectedDomainPack(pack);
      
      expect(useAppStore.getState().selectedDomainPack).toEqual(pack);
    });
  });

  describe('Run Config', () => {
    it('updates run config partially', () => {
      useAppStore.getState().setRunConfig({ maxScenarios: 50 });
      
      expect(useAppStore.getState().runConfig.maxScenarios).toBe(50);
      expect(useAppStore.getState().runConfig.maxWallTime).toBe(3600); // unchanged
    });
  });

  describe('Messages', () => {
    it('adds message to thread', () => {
      const message = {
        id: 'msg-1',
        role: 'user' as const,
        content: 'Hello',
        timestamp: new Date().toISOString(),
      };
      
      useAppStore.getState().addMessage(message);
      
      expect(useAppStore.getState().messages).toHaveLength(1);
      expect(useAppStore.getState().messages[0].content).toBe('Hello');
    });

    it('updates existing message', () => {
      const message = {
        id: 'msg-1',
        role: 'user' as const,
        content: 'Hello',
        timestamp: new Date().toISOString(),
      };
      
      useAppStore.getState().addMessage(message);
      useAppStore.getState().updateMessage('msg-1', { content: 'Updated' });
      
      expect(useAppStore.getState().messages[0].content).toBe('Updated');
    });
  });

  describe('Run Management', () => {
    const mockRun = {
      id: 'run-1',
      project_id: 'proj-1',
      status: 'running' as const,
      domain_pack: 'TestPack',
      domain_pack_version: '1.0',
      objective_spec: { description: 'Test', objectives: [], constraints: [] },
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      stages: [{ stage: 'formalize' as const, status: 'pending' as const }],
      counters: {
        scenarios_proposed: 0,
        scenarios_simulated: 0,
        scenarios_promoted: 0,
        cache_hits: 0,
        compute_cost: 0,
        storage_cost: 0,
        budget_consumed: 0,
        budget_total: 100,
      },
      candidates: [],
    };

    it('sets current run', () => {
      useAppStore.getState().setCurrentRun(mockRun);
      
      expect(useAppStore.getState().currentRun).toEqual(mockRun);
      expect(useAppStore.getState().runStatus).toBe('running');
    });

    it('updates run stage', () => {
      useAppStore.getState().setCurrentRun(mockRun);
      useAppStore.getState().updateRunStage({
        stage: 'formalize',
        status: 'completed',
      });
      
      const stages = useAppStore.getState().currentRun?.stages;
      expect(stages?.[0].status).toBe('completed');
    });

    it('updates run counters', () => {
      useAppStore.getState().setCurrentRun(mockRun);
      useAppStore.getState().updateRunCounters({
        scenarios_proposed: 10,
        cache_hits: 3,
      });
      
      const counters = useAppStore.getState().currentRun?.counters;
      expect(counters?.scenarios_proposed).toBe(10);
      expect(counters?.cache_hits).toBe(3);
      expect(counters?.budget_total).toBe(100); // unchanged
    });
  });

  describe('Scenario Results', () => {
    const mockScenario: ScenarioResult = {
      id: 'scenario-1',
      run_id: 'run-1',
      state: {},
      actions: {},
      fidelity: 'cheap',
      seed: 42,
      metrics: [],
      judge_score: {
        scenario_id: 'scenario-1',
        score: 0.8,
        level: 'good',
        breakdown: [],
        benchmarks_passed: 5,
        benchmarks_total: 6,
      },
      constraint_violations: [],
      confidence: 0.9,
    };

    it('adds scenario result and sorts by score', () => {
      const mockRun = {
        id: 'run-1',
        project_id: 'proj-1',
        status: 'running' as const,
        domain_pack: 'TestPack',
        domain_pack_version: '1.0',
        objective_spec: { description: 'Test', objectives: [], constraints: [] },
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        stages: [],
        counters: {
          scenarios_proposed: 0,
          scenarios_simulated: 0,
          scenarios_promoted: 0,
          cache_hits: 0,
          compute_cost: 0,
          storage_cost: 0,
          budget_consumed: 0,
          budget_total: 100,
        },
        candidates: [],
      };

      useAppStore.getState().setCurrentRun(mockRun);
      
      useAppStore.getState().addScenarioResult({
        ...mockScenario,
        id: 's1',
        judge_score: { ...mockScenario.judge_score!, score: 0.5 },
      });
      
      useAppStore.getState().addScenarioResult({
        ...mockScenario,
        id: 's2',
        judge_score: { ...mockScenario.judge_score!, score: 0.9 },
      });

      const candidates = useAppStore.getState().currentRun?.candidates;
      expect(candidates).toHaveLength(2);
      expect(candidates?.[0].id).toBe('s2'); // Higher score first
      expect(candidates?.[1].id).toBe('s1');
    });

    it('sets current best', () => {
      const mockRun = {
        id: 'run-1',
        project_id: 'proj-1',
        status: 'running' as const,
        domain_pack: 'TestPack',
        domain_pack_version: '1.0',
        objective_spec: { description: 'Test', objectives: [], constraints: [] },
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        stages: [],
        counters: {
          scenarios_proposed: 0,
          scenarios_simulated: 0,
          scenarios_promoted: 0,
          cache_hits: 0,
          compute_cost: 0,
          storage_cost: 0,
          budget_consumed: 0,
          budget_total: 100,
        },
        candidates: [],
      };

      useAppStore.getState().setCurrentRun(mockRun);
      useAppStore.getState().setCurrentBest(mockScenario);
      
      expect(useAppStore.getState().currentRun?.current_best).toEqual(mockScenario);
    });
  });

  describe('Heatmaps', () => {
    it('computes delta heatmap when setting layers', () => {
      const baseline = {
        name: 'Baseline',
        data: [[1, 2], [3, 4]],
        min: 1,
        max: 4,
      };
      
      const scenario = {
        name: 'Scenario',
        data: [[2, 4], [6, 8]],
        min: 2,
        max: 8,
      };

      useAppStore.getState().setHeatmapLayers(baseline, scenario);

      const delta = useAppStore.getState().deltaHeatmap;
      expect(delta).not.toBeNull();
      expect(delta?.data[0][0]).toBe(1); // 2 - 1
      expect(delta?.data[1][1]).toBe(4); // 8 - 4
    });

    it('toggles heatmap mask', () => {
      const initialMasks = useAppStore.getState().heatmapMasks;
      const thresholdMask = initialMasks.find(m => m.type === 'threshold');
      expect(thresholdMask?.enabled).toBe(false);

      useAppStore.getState().toggleHeatmapMask('threshold');

      const updatedMasks = useAppStore.getState().heatmapMasks;
      const updatedThresholdMask = updatedMasks.find(m => m.type === 'threshold');
      expect(updatedThresholdMask?.enabled).toBe(true);
    });

    it('sets heatmap mask value', () => {
      useAppStore.getState().setHeatmapMaskValue('topk', 20);

      const masks = useAppStore.getState().heatmapMasks;
      const topkMask = masks.find(m => m.type === 'topk');
      expect(topkMask?.value).toBe(20);
    });
  });

  describe('Reset', () => {
    it('resets state to initial values', () => {
      // Set some state
      useAppStore.getState().addMessage({
        id: 'msg-1',
        role: 'user',
        content: 'Hello',
        timestamp: new Date().toISOString(),
      });
      useAppStore.getState().setActiveTab('charts');

      // Reset
      useAppStore.getState().reset();

      expect(useAppStore.getState().messages).toHaveLength(0);
      expect(useAppStore.getState().currentRun).toBeNull();
      expect(useAppStore.getState().runStatus).toBe('idle');
    });
  });
});
