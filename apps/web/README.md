# GSIP Web Application

A ChatGPT/Claude-style interface for the Goal-Oriented Simulation and Intervention Platform (GSIP).

## Overview

This web application provides a conversational interface for running simulations, with a "Simulation Workspace" that updates live as runs execute. Users can chat naturally while every run is grounded in structured ObjectiveSpec, ScenarioSpec, and RunLedger.

## Features

### Page Layout

- **Header**: Project selector, domain pack selector, run budget controls, status indicator
- **Simulation Workspace** (top 60-70%): Live run progress and results across 7 tabs
- **Chat Section** (bottom 30-40%): ChatGPT-style chat thread with composer

### Workspace Tabs

1. **Overview**: Pipeline timeline, live counters, current best card, top 5 candidates
2. **Leaderboard**: Sortable table of all scenarios with scores, metrics, constraints
3. **Scenario Detail**: Full scenario view with JSON, metrics, robustness, judge breakdown
4. **Charts**: Time series, comparison charts, and Pareto frontier visualization
5. **Heatmaps**: Masked spatial viewer with 5 mask types (threshold, delta, top-k, constraint, confidence)
6. **Evidence**: Evidence pack chunks and benchmark details
7. **Logs & Debug**: Orchestrator, simulation, optimizer, and MoE committee traces

### Chat Features

- Natural language input with run cards embedded in thread
- Streaming updates during runs
- Quick controls for dataset attachment and constraints

### Live Updates

- Server-Sent Events (SSE) for real-time updates
- Automatic reconnection with exponential backoff
- State reconciliation from API snapshots

## Tech Stack

- **Framework**: Next.js 14 with App Router
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **State Management**: Zustand
- **Charts**: Recharts
- **Icons**: Lucide React
- **Testing**: Vitest + Testing Library

## Getting Started

### Prerequisites

- Node.js 18+
- npm or yarn
- Backend API running on `http://localhost:8000`

### Installation

```bash
cd apps/web
npm install
```

### Development

```bash
npm run dev
```

The app runs on `http://localhost:3000`.

### Testing

```bash
# Run all tests
npm test

# Run tests with UI
npm run test:ui
```

### Build

```bash
npm run build
npm start
```

## Project Structure

```
src/
├── app/
│   ├── layout.tsx      # Root layout
│   └── page.tsx        # Main page
├── components/
│   ├── chat/           # Chat components
│   │   ├── ChatThread.tsx
│   │   ├── ChatMessage.tsx
│   │   ├── ChatComposer.tsx
│   │   └── RunCardEmbed.tsx
│   ├── layout/
│   │   └── Header.tsx
│   └── workspace/
│       ├── WorkspaceTabs.tsx
│       ├── WorkspaceContent.tsx
│       └── tabs/
│           ├── OverviewTab.tsx
│           ├── LeaderboardTab.tsx
│           ├── ScenarioDetailTab.tsx
│           ├── ChartsTab.tsx
│           ├── HeatmapsTab.tsx
│           ├── EvidenceTab.tsx
│           └── LogsTab.tsx
├── hooks/
│   └── useSSE.ts       # SSE hook for live updates
├── lib/
│   └── utils.ts        # Utility functions
├── store/
│   └── index.ts        # Zustand store
├── styles/
│   └── globals.css     # Global styles
├── test/
│   └── setup.ts        # Test setup
└── types/
    └── index.ts        # TypeScript types
```

## API Integration

The app proxies API requests to `http://localhost:8000` via Next.js rewrites.

### Key Endpoints

- `POST /api/runs/start` - Start a new simulation run
- `GET /api/runs/:id` - Get run details
- `GET /api/runs/:id/stream` - SSE endpoint for live updates
- `GET /api/runs/:id/benchmarks` - Get benchmarks for a run
- `GET /api/evidence/packs/:id` - Get evidence pack

## Screenshots

<!-- Screenshots will be added here -->

*[Screenshot: Main workspace view with chat]*

*[Screenshot: Leaderboard with scenario results]*

*[Screenshot: Heatmap with mask controls]*

*[Screenshot: Charts tab with Pareto frontier]*

## Demo Flow

1. User opens the app, selects project and domain pack
2. Types in chat: "Find best intervention for SpatialPack demo"
3. Run starts, workspace shows pipeline progress
4. Leaderboard populates with evaluated scenarios
5. Charts and masked heatmaps render
6. Judge grade appears with benchmark breakdown
7. User can click any scenario to view details

## Configuration

Environment variables (create `.env.local`):

```env
# API endpoint (defaults to localhost:8000)
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Contributing

1. Follow the existing code style
2. Add tests for new components
3. Update types in `src/types/index.ts`
4. Use Zustand for state management
