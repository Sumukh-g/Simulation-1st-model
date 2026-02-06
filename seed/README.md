# GSIP Seed Data

This directory contains seed data for initializing the GSIP platform.

## Files

### rubrics.json

Scoring rubrics that define how simulation outcomes are evaluated:
- `default-single-objective`: Standard single-metric rubric
- `finance-risk-adjusted`: Portfolio optimization rubric
- `spatial-coverage`: Spatial simulation rubric
- `multi-objective-pareto`: Multi-objective optimization rubric

### benchmarks.json

Expert benchmarks for comparison:
- Finance: Sharpe ratio thresholds, drawdown limits
- Spatial: Safe area coverage, critical area limits
- Toy: Navigation efficiency benchmarks

### domain_packs.json

Registered domain pack metadata:
- ToyPack: Simple 2D navigation
- FinancePack: Portfolio backtesting
- SpatialPack: Grid diffusion simulation

### demo_runs.json

Sample run configurations for demonstration:
- ToyPack navigation demo
- Portfolio optimization demo
- Air quality simulation demo

## Loading Seed Data

```bash
# From the project root
python scripts/seed_data.py
```

Or via API:

```bash
# Load rubrics
curl -X POST http://localhost:8000/admin/seed/rubrics \
  -H "Content-Type: application/json" \
  -d @seed/rubrics.json

# Load benchmarks
curl -X POST http://localhost:8000/admin/seed/benchmarks \
  -H "Content-Type: application/json" \
  -d @seed/benchmarks.json
```
