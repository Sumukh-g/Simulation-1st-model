# GSIP Admin Console

Administration console for the Goal-Oriented Simulation and Intervention Platform (GSIP).

## Overview

This admin application provides management interfaces for benchmarks, rubrics, domain packs, and audit logs. It includes a simulation preview tool for validating packs.

## Features

### Benchmark Management

- View, create, edit, and delete benchmarks
- Configure metric thresholds (min/max/target)
- Add context tags for filtering
- Set credibility weights

### Rubric Editor

- Create and edit scoring rubrics
- Configure metric weights
- Approval workflow (draft → pending → approved)
- Version management

### Domain Pack Registry

- View registered domain packs
- Certification status and workflow
- Version information

### Audit Log

- View all administrative actions
- Filter by user, action type, resource
- Detailed change tracking

### Simulate Preview

- Run quick cheap-fidelity simulations
- Validate domain pack configurations
- Test scenario JSON before production runs

## Tech Stack

- **Framework**: Next.js 14 with App Router
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **Icons**: Lucide React
- **Testing**: Vitest

## Getting Started

### Prerequisites

- Node.js 18+
- npm or yarn
- Backend API running on `http://localhost:8000`

### Installation

```bash
cd apps/admin
npm install
```

### Development

```bash
npm run dev
```

The admin console runs on `http://localhost:3001`.

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
│   └── page.tsx        # Main admin page with sidebar navigation
└── styles/
    └── globals.css     # Global styles
```

## Screenshots

<!-- Screenshots will be added here -->

*[Screenshot: Benchmark management table]*

*[Screenshot: Rubric editor with approval workflow]*

*[Screenshot: Domain pack registry]*

*[Screenshot: Audit log viewer]*

## API Integration

The app proxies API requests to `http://localhost:8000` via Next.js rewrites.

### Key Endpoints

- `GET/POST/PATCH/DELETE /api/admin/benchmarks` - Benchmark CRUD
- `GET/POST/PATCH/DELETE /api/admin/rubrics` - Rubric CRUD
- `GET/POST /api/admin/domain_packs` - Domain pack management
- `GET /api/admin/audit_events` - Audit log
- `POST /api/sim_fabric/run` - Simulation preview

## Configuration

Environment variables (create `.env.local`):

```env
# API endpoint (defaults to localhost:8000)
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Security

- Requires admin role for access
- All actions are logged to audit trail
- RBAC enforcement via backend

## Contributing

1. Follow the existing code style
2. Add tests for new features
3. Ensure all admin actions are auditable
