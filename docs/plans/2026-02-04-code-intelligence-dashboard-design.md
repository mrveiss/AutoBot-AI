# Code Intelligence Dashboard Design

> Issue #566 - [Frontend] Code Intelligence Dashboard - 18 Endpoints
> Date: 2026-02-04

## Overview

Complete the Code Intelligence Dashboard implementation to provide code analysis, security scanning, and performance insights with detailed findings display.

## Current State

**Working:**
- Route `/analytics/code-intelligence` accessible from AnalyticsView
- Four score cards (Health, Security, Performance, Redis)
- Full analysis trigger button
- Report download functionality (JSON/Markdown)
- All 18 backend endpoints exist

**Issues:**
- Critical bug: Frontend uses `/api/code_intelligence/` but backend registers `/api/code-intelligence/`
- Missing tabbed interface for detailed findings
- Missing single file scan UI

## Architecture

### Component Structure

```
autobot-user-frontend/src/components/analytics/
├── CodeIntelligenceDashboard.vue    (MODIFY - main orchestrator)
├── code-intelligence/               (NEW folder)
│   ├── FindingsTable.vue            (shared table component)
│   ├── FindingDetailCard.vue        (expandable detail view)
│   ├── SecurityFindingsPanel.vue    (security tab content)
│   ├── PerformanceFindingsPanel.vue (performance tab content)
│   ├── RedisFindingsPanel.vue       (redis tab content)
│   └── FileScanModal.vue            (single file scan dialog)
```

### Data Flow

1. `CodeIntelligenceDashboard.vue` owns all state (scores, findings, loading)
2. Composable `useCodeIntelligence.ts` handles all API calls
3. Child panels receive findings as props, emit events for interactions
4. `FindingsTable` is reused by all three panels with configurable columns
5. Clicking a table row expands `FindingDetailCard` inline

## UI Design

### Main Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Code Intelligence                    [Scan File] [Run Analysis]│
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │ 78 / A   │ │ 85 / A   │ │ 72 / C   │ │ 90 / A   │           │
│  │ Health   │ │ Security │ │ Perf     │ │ Redis    │           │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘           │
├─────────────────────────────────────────────────────────────────┤
│  [Security ▼] [Performance] [Redis] [Patterns]     [Download ▾]│
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  <ActivePanel />  (content based on selected tab)               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Hybrid Table/Card Display (FindingsTable.vue)

```
┌─────────────────────────────────────────────────────────────────┐
│ Filter: [All ▾] [Critical ▾] [High ▾]    Search: [________] 🔍 │
├─────────────────────────────────────────────────────────────────┤
│ Severity │ File:Line        │ Issue Type       │ Message       │
├──────────┼──────────────────┼──────────────────┼───────────────┤
│ 🔴 Crit  │ api/auth.py:45   │ SQL Injection    │ Unsanitized...│
│ ▼ EXPANDED DETAIL CARD ─────────────────────────────────────── │
│ │ Full message: User input directly concatenated into SQL...  │ │
│ │ Remediation: Use parameterized queries with ? placeholders  │ │
│ │ OWASP: A03:2021 - Injection                                 │ │
│ │ [View File] [Copy Path]                                     │ │
│ └─────────────────────────────────────────────────────────────┘ │
│ 🟠 High  │ utils/redis.py:89│ Connection Pool  │ Direct Redis..│
│ 🟡 Med   │ services/api.py  │ N+1 Query        │ Loop inside...│
└─────────────────────────────────────────────────────────────────┘
```

### File Scan Modal

```
┌──────────────────────────────────────────────┐
│  Scan Single File                        [X] │
├──────────────────────────────────────────────┤
│  File Path:                                  │
│  ┌────────────────────────────────────────┐  │
│  │ /path/to/file.py                      │  │
│  └────────────────────────────────────────┘  │
│                                              │
│  Scan Type:                                  │
│  [x] Security   [ ] Performance   [ ] Redis  │
│                                              │
│  Note: Only Python (.py) files supported     │
│                                              │
│              [Cancel]  [Scan File]           │
└──────────────────────────────────────────────┘
```

## API Changes

### URL Fix

All URLs in `useCodeIntelligence.ts` must change from underscore to hyphen:

```typescript
// BEFORE
/api/code_intelligence/health-score
/api/code_intelligence/security/score

// AFTER
/api/code-intelligence/health-score
/api/code-intelligence/security/score
```

### New Composable Methods

```typescript
// Fetch detailed findings (not just scores)
async function fetchSecurityFindings(path: string): Promise<SecurityFinding[]>
async function fetchPerformanceFindings(path: string): Promise<PerformanceFinding[]>
async function fetchRedisFindings(path: string): Promise<RedisOptimization[]>

// Single file scans
async function scanFileSecurity(filePath: string): Promise<SecurityFinding[]>
async function scanFilePerformance(filePath: string): Promise<PerformanceFinding[]>
async function scanFileRedis(filePath: string): Promise<RedisOptimization[]>
```

### Backend Endpoints Used

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/code-intelligence/security/analyze` | Get security findings |
| POST | `/api/code-intelligence/security/scan-file` | Scan single file |
| POST | `/api/code-intelligence/performance/analyze` | Get performance findings |
| POST | `/api/code-intelligence/performance/scan-file` | Scan single file |
| POST | `/api/code-intelligence/redis/analyze` | Get Redis findings |
| POST | `/api/code-intelligence/redis/scan-file` | Scan single file |

## Component Specifications

### FindingsTable.vue (~150 lines)

**Props:**
```typescript
interface Props {
  findings: Finding[]
  columns: ColumnDef[]
  loading: boolean
  emptyMessage: string
}
```

**Features:**
- Click row to expand/collapse detail card inline
- Filter by severity (checkboxes)
- Search across file path and message
- Sort by clicking column headers

### Panel Components (~100 lines each)

Each panel (Security, Performance, Redis) wraps FindingsTable with:
- Panel-specific column configuration
- Panel-specific empty state message
- Panel-specific detail card fields

### FileScanModal.vue (~120 lines)

**Behavior:**
- File path input with `.py` validation
- Multi-select scan type checkboxes
- On submit: call appropriate `/scan-file` endpoints
- On success: close modal, show toast, switch to relevant tab

## State Management

```typescript
// In CodeIntelligenceDashboard.vue
const activeTab = ref<'security' | 'performance' | 'redis' | 'patterns'>('security')
const analysisPath = ref('/home/kali/Desktop/AutoBot')
const loading = ref(false)
const showFileScanModal = ref(false)

// Scores (existing)
const healthScore = ref<HealthScoreResponse | null>(null)
const securityScore = ref<SecurityScoreResponse | null>(null)
const performanceScore = ref<PerformanceScoreResponse | null>(null)
const redisScore = ref<RedisHealthScoreResponse | null>(null)

// Detailed findings (new)
const securityFindings = ref<SecurityFinding[]>([])
const performanceFindings = ref<PerformanceFinding[]>([])
const redisFindings = ref<RedisOptimization[]>([])
```

**Tab Behavior:**
- Lazy-loaded: findings fetched only when tab first selected
- Cache results until new analysis triggered
- Show skeleton loader while fetching
- Badge on tab shows count: `Security (12)`

## Error Handling

```typescript
// On 401: Show "Admin authentication required" toast
// On 404: Show "API endpoint not available" toast
// On 500: Show error message from response
// Network error: Show "Backend unreachable" toast
```

## Implementation Checklist

### Files to Modify

| File | Changes |
|------|---------|
| `useCodeIntelligence.ts` | Fix URLs (underscore → hyphen), add 6 new methods |
| `CodeIntelligenceDashboard.vue` | Add tabs, state for findings, integrate panels |

### Files to Create

| File | Lines | Purpose |
|------|-------|---------|
| `code-intelligence/FindingsTable.vue` | ~150 | Shared hybrid table |
| `code-intelligence/FindingDetailCard.vue` | ~80 | Expandable detail row |
| `code-intelligence/SecurityFindingsPanel.vue` | ~100 | Security tab |
| `code-intelligence/PerformanceFindingsPanel.vue` | ~100 | Performance tab |
| `code-intelligence/RedisFindingsPanel.vue` | ~100 | Redis tab |
| `code-intelligence/FileScanModal.vue` | ~120 | File scan dialog |

## Acceptance Criteria

| Criteria | Status | Component |
|----------|--------|-----------|
| CodeIntelligenceView accessible from AnalyticsView | ✅ Done | - |
| All four score cards display correctly | ✅ Done | - |
| Full analysis can be triggered | ✅ Done | - |
| Single file scanning works | 🔧 TODO | FileScanModal.vue |
| Security tab shows vulnerabilities | 🔧 TODO | SecurityFindingsPanel.vue |
| Performance tab shows issues | 🔧 TODO | PerformanceFindingsPanel.vue |
| Redis tab shows optimizations | 🔧 TODO | RedisFindingsPanel.vue |
| Reports can be generated/downloaded | ✅ Done | - |

---

*Generated with Claude Code for Issue #566*
