# Code Intelligence Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the Code Intelligence Dashboard with tabbed findings panels, hybrid table/card display, and single file scanning.

**Architecture:** Modular Vue 3 components using Composition API. Main dashboard orchestrates state, child panels display findings via shared FindingsTable component. Composable handles all API calls with proper error handling.

**Tech Stack:** Vue 3, TypeScript, Composition API, existing design system CSS variables

**Issue:** #566

---

## Task 1: Fix API URL Mismatch (Critical Bug)

**Files:**
- Modify: `autobot-vue/src/composables/useCodeIntelligence.ts`

**Step 1: Fix all URL paths**

Replace all occurrences of `code_intelligence` with `code-intelligence`:

```typescript
// Line 53: fetchHealthScore
`${backendUrl}/api/code-intelligence/health-score?path=${encodeURIComponent(path)}`

// Line 71: fetchSecurityScore
`${backendUrl}/api/code-intelligence/security/score?path=${encodeURIComponent(path)}`

// Line 89: fetchPerformanceScore
`${backendUrl}/api/code-intelligence/performance/score?path=${encodeURIComponent(path)}`

// Line 107: fetchRedisScore
`${backendUrl}/api/code-intelligence/redis/health-score?path=${encodeURIComponent(path)}`

// Line 122: fetchPatternTypes
`${backendUrl}/api/code-intelligence/pattern-types`

// Line 134: fetchVulnerabilityTypes
`${backendUrl}/api/code-intelligence/security/vulnerability-types`

// Line 146: fetchPerformanceIssueTypes
`${backendUrl}/api/code-intelligence/performance/issue-types`

// Line 158: fetchRedisOptimizationTypes
`${backendUrl}/api/code-intelligence/redis/optimization-types`

// Line 175: downloadReport
`${backendUrl}/api/code-intelligence/${type}/report?path=${encodeURIComponent(path)}&format=${format}`
```

**Step 2: Commit**

```bash
git add autobot-vue/src/composables/useCodeIntelligence.ts
git commit -m "fix(frontend): correct API URLs from code_intelligence to code-intelligence (#566)"
```

---

## Task 2: Add Findings Types and New API Methods

**Files:**
- Modify: `autobot-vue/src/types/codeIntelligence.ts`
- Modify: `autobot-vue/src/composables/useCodeIntelligence.ts`

**Step 1: Add Redis finding type to types file**

Add after line 139 in `codeIntelligence.ts`:

```typescript
// Redis optimization finding (from analyze endpoint)
export interface RedisOptimizationFinding {
  optimization_type: string
  severity: Severity
  file_path: string
  line_number: number
  message: string
  recommendation: string
  category: string
}

// Analysis response types
export interface SecurityAnalysisResponse {
  status: string
  timestamp: string
  path: string
  summary: Record<string, unknown>
  findings: SecurityFinding[]
  total_findings: number
}

export interface PerformanceAnalysisResponse {
  status: string
  timestamp: string
  path: string
  summary: Record<string, unknown>
  findings: PerformanceFinding[]
  total_findings: number
}

export interface RedisAnalysisResponse {
  status: string
  timestamp: string
  path: string
  optimizations: RedisOptimizationFinding[]
  summary: Record<string, unknown>
}

// File scan response types
export interface FileScanResponse<T> {
  status: string
  timestamp: string
  file_path: string
  findings: T[]
  total_findings: number
}
```

**Step 2: Add new state and methods to composable**

Add after line 41 in `useCodeIntelligence.ts`:

```typescript
// Detailed findings
const securityFindings = ref<SecurityFinding[]>([])
const performanceFindings = ref<PerformanceFinding[]>([])
const redisFindings = ref<RedisOptimizationFinding[]>([])
```

Add new imports at top:

```typescript
import type {
  // ... existing imports ...
  SecurityFinding,
  PerformanceFinding,
  RedisOptimizationFinding,
  SecurityAnalysisResponse,
  PerformanceAnalysisResponse,
  RedisAnalysisResponse,
  FileScanResponse
} from '@/types/codeIntelligence'
```

**Step 3: Add fetchSecurityFindings method**

Add after `fetchRedisScore` function:

```typescript
async function fetchSecurityFindings(path: string): Promise<SecurityFinding[]> {
  loading.value = true
  error.value = null
  try {
    const backendUrl = await getBackendUrl()
    const response = await fetch(`${backendUrl}/api/code-intelligence/security/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path })
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data: SecurityAnalysisResponse = await response.json()
    securityFindings.value = data.findings
    return data.findings
  } catch (e) {
    error.value = `Failed to fetch security findings: ${e}`
    logger.error('fetchSecurityFindings failed:', e)
    return []
  } finally {
    loading.value = false
  }
}
```

**Step 4: Add fetchPerformanceFindings method**

```typescript
async function fetchPerformanceFindings(path: string): Promise<PerformanceFinding[]> {
  loading.value = true
  error.value = null
  try {
    const backendUrl = await getBackendUrl()
    const response = await fetch(`${backendUrl}/api/code-intelligence/performance/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path })
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data: PerformanceAnalysisResponse = await response.json()
    performanceFindings.value = data.findings
    return data.findings
  } catch (e) {
    error.value = `Failed to fetch performance findings: ${e}`
    logger.error('fetchPerformanceFindings failed:', e)
    return []
  } finally {
    loading.value = false
  }
}
```

**Step 5: Add fetchRedisFindings method**

```typescript
async function fetchRedisFindings(path: string): Promise<RedisOptimizationFinding[]> {
  loading.value = true
  error.value = null
  try {
    const backendUrl = await getBackendUrl()
    const response = await fetch(`${backendUrl}/api/code-intelligence/redis/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path })
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data: RedisAnalysisResponse = await response.json()
    redisFindings.value = data.optimizations
    return data.optimizations
  } catch (e) {
    error.value = `Failed to fetch Redis findings: ${e}`
    logger.error('fetchRedisFindings failed:', e)
    return []
  } finally {
    loading.value = false
  }
}
```

**Step 6: Add file scan methods**

```typescript
async function scanFileSecurity(filePath: string): Promise<SecurityFinding[]> {
  loading.value = true
  error.value = null
  try {
    const backendUrl = await getBackendUrl()
    const response = await fetch(`${backendUrl}/api/code-intelligence/security/scan-file`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath })
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()
    return data.findings || []
  } catch (e) {
    error.value = `Failed to scan file: ${e}`
    logger.error('scanFileSecurity failed:', e)
    return []
  } finally {
    loading.value = false
  }
}

async function scanFilePerformance(filePath: string): Promise<PerformanceFinding[]> {
  loading.value = true
  error.value = null
  try {
    const backendUrl = await getBackendUrl()
    const response = await fetch(`${backendUrl}/api/code-intelligence/performance/scan-file`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath })
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()
    return data.findings || []
  } catch (e) {
    error.value = `Failed to scan file: ${e}`
    logger.error('scanFilePerformance failed:', e)
    return []
  } finally {
    loading.value = false
  }
}

async function scanFileRedis(filePath: string): Promise<RedisOptimizationFinding[]> {
  loading.value = true
  error.value = null
  try {
    const backendUrl = await getBackendUrl()
    const response = await fetch(`${backendUrl}/api/code-intelligence/redis/scan-file`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_path: filePath })
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()
    return data.optimizations || []
  } catch (e) {
    error.value = `Failed to scan file: ${e}`
    logger.error('scanFileRedis failed:', e)
    return []
  } finally {
    loading.value = false
  }
}
```

**Step 7: Update return statement**

Add to the return object:

```typescript
return {
  // ... existing ...
  // New state
  securityFindings,
  performanceFindings,
  redisFindings,
  // New actions
  fetchSecurityFindings,
  fetchPerformanceFindings,
  fetchRedisFindings,
  scanFileSecurity,
  scanFilePerformance,
  scanFileRedis
}
```

**Step 8: Commit**

```bash
git add autobot-vue/src/types/codeIntelligence.ts autobot-vue/src/composables/useCodeIntelligence.ts
git commit -m "feat(frontend): add findings fetch and file scan methods to composable (#566)"
```

---

## Task 3: Create FindingsTable Component

**Files:**
- Create: `autobot-vue/src/components/analytics/code-intelligence/FindingsTable.vue`

**Step 1: Create the directory**

```bash
mkdir -p autobot-vue/src/components/analytics/code-intelligence
```

**Step 2: Create FindingsTable.vue**

```vue
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!-- Issue #566 - Code Intelligence Dashboard -->

<template>
  <div class="findings-table">
    <!-- Filters -->
    <div class="table-controls">
      <div class="severity-filters">
        <label v-for="sev in severityLevels" :key="sev" class="filter-checkbox">
          <input type="checkbox" v-model="selectedSeverities" :value="sev" />
          <span :class="['severity-badge', sev]">{{ sev }}</span>
        </label>
      </div>
      <div class="search-box">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search files or messages..."
          class="search-input"
        />
      </div>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <span>Loading findings...</span>
    </div>

    <!-- Empty state -->
    <div v-else-if="filteredFindings.length === 0" class="empty-state">
      <i class="fas fa-check-circle"></i>
      <p>{{ emptyMessage }}</p>
    </div>

    <!-- Table -->
    <div v-else class="table-container">
      <table>
        <thead>
          <tr>
            <th class="col-severity">Severity</th>
            <th class="col-file">File:Line</th>
            <th class="col-type">Type</th>
            <th class="col-message">Message</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="(finding, index) in filteredFindings" :key="index">
            <tr
              @click="toggleExpand(index)"
              :class="{ expanded: expandedRow === index }"
              class="finding-row"
            >
              <td class="col-severity">
                <span :class="['severity-badge', finding.severity]">
                  {{ getSeverityIcon(finding.severity) }} {{ finding.severity }}
                </span>
              </td>
              <td class="col-file">
                <code>{{ formatFilePath(finding.file_path) }}:{{ finding.line_number }}</code>
              </td>
              <td class="col-type">{{ getTypeDisplay(finding) }}</td>
              <td class="col-message">{{ truncateMessage(finding.message) }}</td>
            </tr>
            <!-- Expanded detail card -->
            <tr v-if="expandedRow === index" class="detail-row">
              <td colspan="4">
                <div class="detail-card">
                  <div class="detail-section">
                    <strong>Full Message:</strong>
                    <p>{{ finding.message }}</p>
                  </div>
                  <div class="detail-section">
                    <strong>Recommendation:</strong>
                    <p>{{ getRemediation(finding) }}</p>
                  </div>
                  <div v-if="finding.owasp_category" class="detail-section">
                    <strong>OWASP:</strong>
                    <span class="owasp-tag">{{ finding.owasp_category }}</span>
                  </div>
                  <div class="detail-actions">
                    <button @click.stop="copyPath(finding)" class="btn-small">
                      <i class="fas fa-copy"></i> Copy Path
                    </button>
                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { Severity } from '@/types/codeIntelligence'

interface Finding {
  severity: Severity
  file_path: string
  line_number: number
  message: string
  vulnerability_type?: string
  issue_type?: string
  optimization_type?: string
  remediation?: string
  recommendation?: string
  owasp_category?: string
}

const props = defineProps<{
  findings: Finding[]
  loading: boolean
  emptyMessage: string
}>()

const severityLevels: Severity[] = ['critical', 'high', 'medium', 'low', 'info']
const selectedSeverities = ref<Severity[]>([...severityLevels])
const searchQuery = ref('')
const expandedRow = ref<number | null>(null)

const filteredFindings = computed(() => {
  return props.findings.filter(f => {
    const matchesSeverity = selectedSeverities.value.includes(f.severity)
    const matchesSearch = searchQuery.value === '' ||
      f.file_path.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
      f.message.toLowerCase().includes(searchQuery.value.toLowerCase())
    return matchesSeverity && matchesSearch
  })
})

function getSeverityIcon(severity: Severity): string {
  const icons: Record<Severity, string> = {
    critical: '🔴',
    high: '🟠',
    medium: '🟡',
    low: '🔵',
    info: '⚪'
  }
  return icons[severity] || '⚪'
}

function formatFilePath(path: string): string {
  const parts = path.split('/')
  return parts.length > 3 ? '.../' + parts.slice(-3).join('/') : path
}

function getTypeDisplay(finding: Finding): string {
  return finding.vulnerability_type || finding.issue_type || finding.optimization_type || 'Unknown'
}

function truncateMessage(message: string): string {
  return message.length > 60 ? message.slice(0, 60) + '...' : message
}

function getRemediation(finding: Finding): string {
  return finding.remediation || finding.recommendation || 'No recommendation available'
}

function toggleExpand(index: number): void {
  expandedRow.value = expandedRow.value === index ? null : index
}

function copyPath(finding: Finding): void {
  const path = `${finding.file_path}:${finding.line_number}`
  navigator.clipboard.writeText(path)
}
</script>

<style scoped>
.findings-table {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.table-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-3);
  border-bottom: 1px solid var(--border-primary);
  flex-wrap: wrap;
  gap: var(--spacing-2);
}

.severity-filters {
  display: flex;
  gap: var(--spacing-2);
  flex-wrap: wrap;
}

.filter-checkbox {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  cursor: pointer;
}

.search-input {
  padding: var(--spacing-2);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  background: var(--bg-primary);
  color: var(--text-primary);
  width: 200px;
}

.severity-badge {
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
  font-weight: var(--font-medium);
  text-transform: uppercase;
}

.severity-badge.critical { background: rgba(239, 68, 68, 0.2); color: #ef4444; }
.severity-badge.high { background: rgba(249, 115, 22, 0.2); color: #f97316; }
.severity-badge.medium { background: rgba(234, 179, 8, 0.2); color: #eab308; }
.severity-badge.low { background: rgba(59, 130, 246, 0.2); color: #3b82f6; }
.severity-badge.info { background: rgba(156, 163, 175, 0.2); color: #9ca3af; }

.loading-state, .empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-8);
  color: var(--text-secondary);
}

.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--border-primary);
  border-top-color: var(--color-info-dark);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.table-container {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th, td {
  padding: var(--spacing-3);
  text-align: left;
  border-bottom: 1px solid var(--border-primary);
}

th {
  background: var(--bg-tertiary);
  font-weight: var(--font-medium);
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.finding-row {
  cursor: pointer;
  transition: background 0.15s;
}

.finding-row:hover {
  background: var(--bg-tertiary);
}

.finding-row.expanded {
  background: var(--bg-tertiary);
}

.col-severity { width: 100px; }
.col-file { width: 200px; }
.col-type { width: 150px; }
.col-message { flex: 1; }

code {
  font-family: monospace;
  font-size: 0.875rem;
  color: var(--text-primary);
}

.detail-row td {
  padding: 0;
  background: var(--bg-tertiary);
}

.detail-card {
  padding: var(--spacing-4);
  border-left: 3px solid var(--color-info-dark);
  margin: var(--spacing-2);
  background: var(--bg-secondary);
  border-radius: var(--radius-md);
}

.detail-section {
  margin-bottom: var(--spacing-3);
}

.detail-section strong {
  display: block;
  margin-bottom: var(--spacing-1);
  color: var(--text-primary);
}

.detail-section p {
  color: var(--text-secondary);
  margin: 0;
}

.owasp-tag {
  display: inline-block;
  padding: 2px 8px;
  background: rgba(99, 102, 241, 0.2);
  color: #6366f1;
  border-radius: var(--radius-sm);
  font-size: 0.875rem;
}

.detail-actions {
  display: flex;
  gap: var(--spacing-2);
  margin-top: var(--spacing-3);
}

.btn-small {
  padding: var(--spacing-1) var(--spacing-2);
  background: var(--bg-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  cursor: pointer;
  font-size: 0.875rem;
}

.btn-small:hover {
  background: var(--bg-tertiary);
}
</style>
```

**Step 3: Commit**

```bash
git add autobot-vue/src/components/analytics/code-intelligence/FindingsTable.vue
git commit -m "feat(frontend): add shared FindingsTable component with hybrid display (#566)"
```

---

## Task 4: Create Panel Components

**Files:**
- Create: `autobot-vue/src/components/analytics/code-intelligence/SecurityFindingsPanel.vue`
- Create: `autobot-vue/src/components/analytics/code-intelligence/PerformanceFindingsPanel.vue`
- Create: `autobot-vue/src/components/analytics/code-intelligence/RedisFindingsPanel.vue`

**Step 1: Create SecurityFindingsPanel.vue**

```vue
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!-- Issue #566 - Code Intelligence Dashboard -->

<template>
  <div class="security-panel">
    <div class="panel-header">
      <h3><i class="fas fa-shield-alt"></i> Security Vulnerabilities</h3>
      <span v-if="findings.length > 0" class="count-badge">{{ findings.length }}</span>
    </div>
    <FindingsTable
      :findings="findings"
      :loading="loading"
      empty-message="No security vulnerabilities found"
    />
  </div>
</template>

<script setup lang="ts">
import FindingsTable from './FindingsTable.vue'
import type { SecurityFinding } from '@/types/codeIntelligence'

defineProps<{
  findings: SecurityFinding[]
  loading: boolean
}>()
</script>

<style scoped>
.security-panel {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.panel-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.panel-header h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.panel-header i {
  color: var(--color-info-dark);
}

.count-badge {
  background: var(--bg-tertiary);
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 0.75rem;
  color: var(--text-secondary);
}
</style>
```

**Step 2: Create PerformanceFindingsPanel.vue**

```vue
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!-- Issue #566 - Code Intelligence Dashboard -->

<template>
  <div class="performance-panel">
    <div class="panel-header">
      <h3><i class="fas fa-tachometer-alt"></i> Performance Issues</h3>
      <span v-if="findings.length > 0" class="count-badge">{{ findings.length }}</span>
    </div>
    <FindingsTable
      :findings="findings"
      :loading="loading"
      empty-message="No performance issues found"
    />
  </div>
</template>

<script setup lang="ts">
import FindingsTable from './FindingsTable.vue'
import type { PerformanceFinding } from '@/types/codeIntelligence'

defineProps<{
  findings: PerformanceFinding[]
  loading: boolean
}>()
</script>

<style scoped>
.performance-panel {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.panel-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.panel-header h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.panel-header i {
  color: var(--chart-yellow, #f59e0b);
}

.count-badge {
  background: var(--bg-tertiary);
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 0.75rem;
  color: var(--text-secondary);
}
</style>
```

**Step 3: Create RedisFindingsPanel.vue**

```vue
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!-- Issue #566 - Code Intelligence Dashboard -->

<template>
  <div class="redis-panel">
    <div class="panel-header">
      <h3><i class="fas fa-database"></i> Redis Optimizations</h3>
      <span v-if="findings.length > 0" class="count-badge">{{ findings.length }}</span>
    </div>
    <FindingsTable
      :findings="findings"
      :loading="loading"
      empty-message="No Redis optimization opportunities found"
    />
  </div>
</template>

<script setup lang="ts">
import FindingsTable from './FindingsTable.vue'
import type { RedisOptimizationFinding } from '@/types/codeIntelligence'

defineProps<{
  findings: RedisOptimizationFinding[]
  loading: boolean
}>()
</script>

<style scoped>
.redis-panel {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.panel-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.panel-header h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.panel-header i {
  color: var(--chart-red, #ef4444);
}

.count-badge {
  background: var(--bg-tertiary);
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 0.75rem;
  color: var(--text-secondary);
}
</style>
```

**Step 4: Commit**

```bash
git add autobot-vue/src/components/analytics/code-intelligence/
git commit -m "feat(frontend): add Security, Performance, and Redis findings panels (#566)"
```

---

## Task 5: Create FileScanModal Component

**Files:**
- Create: `autobot-vue/src/components/analytics/code-intelligence/FileScanModal.vue`

**Step 1: Create FileScanModal.vue**

```vue
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!-- Issue #566 - Code Intelligence Dashboard -->

<template>
  <Teleport to="body">
    <div v-if="show" class="modal-overlay" @click.self="$emit('close')">
      <div class="modal-content">
        <div class="modal-header">
          <h3>Scan Single File</h3>
          <button class="close-btn" @click="$emit('close')">
            <i class="fas fa-times"></i>
          </button>
        </div>

        <div class="modal-body">
          <div class="form-group">
            <label>File Path:</label>
            <input
              v-model="filePath"
              type="text"
              placeholder="/path/to/file.py"
              class="file-input"
              :class="{ error: pathError }"
            />
            <span v-if="pathError" class="error-text">{{ pathError }}</span>
          </div>

          <div class="form-group">
            <label>Scan Types:</label>
            <div class="checkbox-group">
              <label class="checkbox-label">
                <input type="checkbox" v-model="scanTypes.security" />
                <span>Security</span>
              </label>
              <label class="checkbox-label">
                <input type="checkbox" v-model="scanTypes.performance" />
                <span>Performance</span>
              </label>
              <label class="checkbox-label">
                <input type="checkbox" v-model="scanTypes.redis" />
                <span>Redis</span>
              </label>
            </div>
          </div>

          <p class="note">Note: Only Python (.py) files are supported</p>
        </div>

        <div class="modal-footer">
          <button class="btn-secondary" @click="$emit('close')">Cancel</button>
          <button
            class="btn-primary"
            @click="handleScan"
            :disabled="!canScan || scanning"
          >
            <span v-if="scanning" class="spinner-small"></span>
            {{ scanning ? 'Scanning...' : 'Scan File' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const props = defineProps<{
  show: boolean
}>()

const emit = defineEmits<{
  close: []
  scan: [filePath: string, types: { security: boolean; performance: boolean; redis: boolean }]
}>()

const filePath = ref('')
const scanning = ref(false)
const scanTypes = ref({
  security: true,
  performance: false,
  redis: false
})

const pathError = computed(() => {
  if (!filePath.value) return ''
  if (!filePath.value.endsWith('.py')) return 'Only Python files (.py) are supported'
  return ''
})

const canScan = computed(() => {
  return filePath.value &&
    filePath.value.endsWith('.py') &&
    (scanTypes.value.security || scanTypes.value.performance || scanTypes.value.redis)
})

async function handleScan() {
  if (!canScan.value) return
  scanning.value = true
  emit('scan', filePath.value, { ...scanTypes.value })
  scanning.value = false
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: var(--bg-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  width: 100%;
  max-width: 480px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4);
  border-bottom: 1px solid var(--border-primary);
}

.modal-header h3 {
  margin: 0;
  font-size: 1.125rem;
  font-weight: var(--font-semibold);
  color: var(--text-primary);
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: var(--spacing-1);
}

.close-btn:hover {
  color: var(--text-primary);
}

.modal-body {
  padding: var(--spacing-4);
}

.form-group {
  margin-bottom: var(--spacing-4);
}

.form-group label {
  display: block;
  margin-bottom: var(--spacing-2);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.file-input {
  width: 100%;
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-family: monospace;
}

.file-input.error {
  border-color: #ef4444;
}

.error-text {
  display: block;
  margin-top: var(--spacing-1);
  color: #ef4444;
  font-size: 0.875rem;
}

.checkbox-group {
  display: flex;
  gap: var(--spacing-4);
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  cursor: pointer;
}

.note {
  color: var(--text-tertiary);
  font-size: 0.875rem;
  margin: 0;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-2);
  padding: var(--spacing-4);
  border-top: 1px solid var(--border-primary);
}

.btn-secondary {
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  cursor: pointer;
}

.btn-primary {
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--color-info-dark);
  border: none;
  border-radius: var(--radius-md);
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.spinner-small {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
```

**Step 2: Commit**

```bash
git add autobot-vue/src/components/analytics/code-intelligence/FileScanModal.vue
git commit -m "feat(frontend): add FileScanModal for single file scanning (#566)"
```

---

## Task 6: Update Main Dashboard with Tabs

**Files:**
- Modify: `autobot-vue/src/components/analytics/CodeIntelligenceDashboard.vue`

**Step 1: Replace entire file with updated version**

```vue
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!-- Issue #566 - Code Intelligence Dashboard Component -->

<template>
  <div class="code-intelligence-dashboard">
    <!-- Header -->
    <div class="dashboard-header">
      <div class="header-content">
        <h2><i class="fas fa-brain"></i> Code Intelligence</h2>
        <p class="header-description">Analyze your codebase for quality, security, and performance issues</p>
      </div>
      <div class="header-actions">
        <div class="path-input">
          <input
            v-model="analysisPath"
            type="text"
            placeholder="Enter path to analyze..."
            class="path-field"
          />
        </div>
        <button @click="showFileScanModal = true" class="btn-secondary">
          <i class="fas fa-file-code"></i> Scan File
        </button>
        <button
          @click="runAnalysis"
          :disabled="loading || !analysisPath"
          class="btn-primary"
        >
          <i :class="loading ? 'fas fa-spinner fa-spin' : 'fas fa-search'"></i>
          Analyze
        </button>
      </div>
    </div>

    <!-- Error display -->
    <div v-if="error" class="error-banner">
      <i class="fas fa-exclamation-triangle"></i>
      {{ error }}
    </div>

    <!-- Health Scores Grid -->
    <div v-if="hasScores" class="scores-grid">
      <div class="score-card">
        <HealthScoreGauge
          v-if="healthScore"
          :score="healthScore.health_score"
          :grade="healthScore.grade"
          label="Code Quality"
          :status-message="`${healthScore.total_issues} issues in ${healthScore.files_analyzed} files`"
        />
      </div>
      <div class="score-card">
        <HealthScoreGauge
          v-if="securityScore"
          :score="securityScore.security_score"
          :grade="securityScore.grade"
          label="Security"
          :status-message="securityScore.status_message"
        />
      </div>
      <div class="score-card">
        <HealthScoreGauge
          v-if="performanceScore"
          :score="performanceScore.performance_score"
          :grade="performanceScore.grade"
          label="Performance"
          :status-message="performanceScore.status_message"
        />
      </div>
      <div class="score-card">
        <HealthScoreGauge
          v-if="redisScore"
          :score="redisScore.health_score"
          :grade="redisScore.grade"
          label="Redis Usage"
          :status-message="redisScore.status_message"
        />
      </div>
    </div>

    <!-- Empty state for scores -->
    <div v-else-if="!loading" class="empty-state">
      <i class="fas fa-code"></i>
      <h3>No Analysis Results</h3>
      <p>Enter a path above and click Analyze to scan your codebase</p>
    </div>

    <!-- Tabs -->
    <div v-if="hasScores" class="tabs-section">
      <div class="tabs-header">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          @click="activeTab = tab.id"
          :class="['tab-btn', { active: activeTab === tab.id }]"
        >
          <i :class="tab.icon"></i>
          {{ tab.label }}
          <span v-if="getTabCount(tab.id) > 0" class="tab-count">
            {{ getTabCount(tab.id) }}
          </span>
        </button>
      </div>

      <div class="tabs-content">
        <SecurityFindingsPanel
          v-if="activeTab === 'security'"
          :findings="securityFindings"
          :loading="findingsLoading"
        />
        <PerformanceFindingsPanel
          v-if="activeTab === 'performance'"
          :findings="performanceFindings"
          :loading="findingsLoading"
        />
        <RedisFindingsPanel
          v-if="activeTab === 'redis'"
          :findings="redisFindings"
          :loading="findingsLoading"
        />
      </div>
    </div>

    <!-- Reports Section -->
    <div v-if="hasScores" class="reports-section">
      <h3><i class="fas fa-file-alt"></i> Download Reports</h3>
      <div class="report-buttons">
        <button @click="downloadReport('security', 'json')" class="btn-secondary">
          <i class="fas fa-shield-alt"></i> Security Report (JSON)
        </button>
        <button @click="downloadReport('security', 'markdown')" class="btn-secondary">
          <i class="fas fa-shield-alt"></i> Security Report (MD)
        </button>
        <button @click="downloadReport('performance', 'json')" class="btn-secondary">
          <i class="fas fa-tachometer-alt"></i> Performance Report (JSON)
        </button>
        <button @click="downloadReport('performance', 'markdown')" class="btn-secondary">
          <i class="fas fa-tachometer-alt"></i> Performance Report (MD)
        </button>
      </div>
    </div>

    <!-- File Scan Modal -->
    <FileScanModal
      :show="showFileScanModal"
      @close="showFileScanModal = false"
      @scan="handleFileScan"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useCodeIntelligence } from '@/composables/useCodeIntelligence'
import HealthScoreGauge from './HealthScoreGauge.vue'
import SecurityFindingsPanel from './code-intelligence/SecurityFindingsPanel.vue'
import PerformanceFindingsPanel from './code-intelligence/PerformanceFindingsPanel.vue'
import RedisFindingsPanel from './code-intelligence/RedisFindingsPanel.vue'
import FileScanModal from './code-intelligence/FileScanModal.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('CodeIntelligenceDashboard')

const {
  loading,
  error,
  healthScore,
  securityScore,
  performanceScore,
  redisScore,
  securityFindings,
  performanceFindings,
  redisFindings,
  fetchAllScores,
  fetchAllTypes,
  fetchSecurityFindings,
  fetchPerformanceFindings,
  fetchRedisFindings,
  scanFileSecurity,
  scanFilePerformance,
  scanFileRedis,
  downloadReport: doDownloadReport
} = useCodeIntelligence()

const analysisPath = ref('/home/kali/Desktop/AutoBot')
const activeTab = ref<'security' | 'performance' | 'redis'>('security')
const showFileScanModal = ref(false)
const findingsLoading = ref(false)
const findingsFetched = ref({ security: false, performance: false, redis: false })

const tabs = [
  { id: 'security' as const, label: 'Security', icon: 'fas fa-shield-alt' },
  { id: 'performance' as const, label: 'Performance', icon: 'fas fa-tachometer-alt' },
  { id: 'redis' as const, label: 'Redis', icon: 'fas fa-database' }
]

const hasScores = computed(() =>
  healthScore.value || securityScore.value || performanceScore.value || redisScore.value
)

function getTabCount(tabId: string): number {
  switch (tabId) {
    case 'security': return securityFindings.value.length
    case 'performance': return performanceFindings.value.length
    case 'redis': return redisFindings.value.length
    default: return 0
  }
}

async function runAnalysis() {
  if (!analysisPath.value) return
  logger.info('Running analysis on:', analysisPath.value)

  // Reset findings cache
  findingsFetched.value = { security: false, performance: false, redis: false }

  // Fetch scores
  await fetchAllScores(analysisPath.value)

  // Fetch findings for active tab
  await loadFindingsForTab(activeTab.value)
}

async function loadFindingsForTab(tab: 'security' | 'performance' | 'redis') {
  if (findingsFetched.value[tab]) return

  findingsLoading.value = true
  try {
    switch (tab) {
      case 'security':
        await fetchSecurityFindings(analysisPath.value)
        break
      case 'performance':
        await fetchPerformanceFindings(analysisPath.value)
        break
      case 'redis':
        await fetchRedisFindings(analysisPath.value)
        break
    }
    findingsFetched.value[tab] = true
  } finally {
    findingsLoading.value = false
  }
}

// Load findings when tab changes
watch(activeTab, (newTab) => {
  if (hasScores.value) {
    loadFindingsForTab(newTab)
  }
})

async function handleFileScan(
  filePath: string,
  types: { security: boolean; performance: boolean; redis: boolean }
) {
  showFileScanModal.value = false
  findingsLoading.value = true

  try {
    const results: string[] = []

    if (types.security) {
      const findings = await scanFileSecurity(filePath)
      if (findings.length > 0) {
        securityFindings.value = findings
        findingsFetched.value.security = true
        results.push(`${findings.length} security`)
      }
    }

    if (types.performance) {
      const findings = await scanFilePerformance(filePath)
      if (findings.length > 0) {
        performanceFindings.value = findings
        findingsFetched.value.performance = true
        results.push(`${findings.length} performance`)
      }
    }

    if (types.redis) {
      const findings = await scanFileRedis(filePath)
      if (findings.length > 0) {
        redisFindings.value = findings
        findingsFetched.value.redis = true
        results.push(`${findings.length} Redis`)
      }
    }

    if (results.length > 0) {
      logger.info(`File scan found: ${results.join(', ')} issues`)
      // Switch to first tab with results
      if (types.security && securityFindings.value.length > 0) {
        activeTab.value = 'security'
      } else if (types.performance && performanceFindings.value.length > 0) {
        activeTab.value = 'performance'
      } else if (types.redis && redisFindings.value.length > 0) {
        activeTab.value = 'redis'
      }
    }
  } finally {
    findingsLoading.value = false
  }
}

async function downloadReport(type: 'security' | 'performance', format: 'json' | 'markdown') {
  if (!analysisPath.value) return
  await doDownloadReport(analysisPath.value, type, format)
}

onMounted(async () => {
  await fetchAllTypes()
})
</script>

<style scoped>
.code-intelligence-dashboard {
  padding: var(--spacing-4);
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-6);
  flex-wrap: wrap;
  gap: var(--spacing-4);
}

.header-content h2 {
  font-size: 1.5rem;
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0;
}

.header-content h2 i {
  margin-right: var(--spacing-2);
  color: var(--color-info-dark);
}

.header-description {
  color: var(--text-secondary);
  margin-top: var(--spacing-1);
}

.header-actions {
  display: flex;
  gap: var(--spacing-2);
  flex-wrap: wrap;
}

.path-input {
  display: flex;
  gap: var(--spacing-2);
}

.path-field {
  width: 300px;
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.btn-primary {
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--color-info-dark);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-weight: var(--font-medium);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 0.875rem;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.btn-secondary:hover {
  background: var(--bg-tertiary);
}

.error-banner {
  padding: var(--spacing-3);
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: var(--radius-md);
  color: #ef4444;
  margin-bottom: var(--spacing-4);
}

.scores-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.score-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  display: flex;
  justify-content: center;
}

.empty-state {
  text-align: center;
  padding: var(--spacing-8);
  color: var(--text-secondary);
}

.empty-state i {
  font-size: 3rem;
  margin-bottom: var(--spacing-4);
  opacity: 0.5;
}

.empty-state h3 {
  margin: 0 0 var(--spacing-2) 0;
  color: var(--text-primary);
}

.tabs-section {
  margin-bottom: var(--spacing-6);
}

.tabs-header {
  display: flex;
  gap: var(--spacing-1);
  border-bottom: 1px solid var(--border-primary);
  margin-bottom: var(--spacing-4);
}

.tab-btn {
  padding: var(--spacing-2) var(--spacing-4);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: 0.875rem;
  transition: all 0.15s;
}

.tab-btn:hover {
  color: var(--text-primary);
}

.tab-btn.active {
  color: var(--color-info-dark);
  border-bottom-color: var(--color-info-dark);
}

.tab-count {
  background: var(--bg-tertiary);
  padding: 1px 6px;
  border-radius: var(--radius-full);
  font-size: 0.75rem;
}

.tab-btn.active .tab-count {
  background: rgba(99, 102, 241, 0.2);
  color: var(--color-info-dark);
}

.tabs-content {
  min-height: 200px;
}

.reports-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
}

.reports-section h3 {
  margin: 0 0 var(--spacing-4) 0;
  font-size: 1rem;
  color: var(--text-primary);
}

.reports-section h3 i {
  margin-right: var(--spacing-2);
}

.report-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-2);
}
</style>
```

**Step 2: Commit**

```bash
git add autobot-vue/src/components/analytics/CodeIntelligenceDashboard.vue
git commit -m "feat(frontend): add tabbed interface and file scan to CodeIntelligenceDashboard (#566)"
```

---

## Task 7: Sync to Frontend VM and Verify

**Step 1: Sync changes to frontend VM**

```bash
./scripts/utilities/sync-to-vm.sh frontend autobot-vue/src/ /home/autobot/autobot-vue/src/
```

**Step 2: Test in browser**

1. Navigate to `http://172.16.168.21:5173/analytics/code-intelligence`
2. Verify score cards display after clicking Analyze
3. Verify tabs switch correctly
4. Verify findings display in table with expandable rows
5. Verify file scan modal opens and works

**Step 3: Final commit with issue close reference**

```bash
git add -A
git commit -m "feat(frontend): complete Code Intelligence Dashboard implementation

- Fix API URL mismatch (code_intelligence -> code-intelligence)
- Add tabbed interface for Security/Performance/Redis findings
- Implement hybrid table/card display with expandable rows
- Add single file scan modal
- Add findings fetch and file scan methods to composable

Closes #566

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

| Task | Files | Estimated Lines |
|------|-------|-----------------|
| 1. Fix API URLs | useCodeIntelligence.ts | ~10 changes |
| 2. Add types and methods | types + composable | ~150 lines |
| 3. FindingsTable | new component | ~200 lines |
| 4. Panel components | 3 new components | ~150 lines total |
| 5. FileScanModal | new component | ~180 lines |
| 6. Update dashboard | existing component | ~300 lines (replace) |
| 7. Test and verify | - | - |

**Total new/modified code:** ~1000 lines across 7 files
