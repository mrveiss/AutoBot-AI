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
          aria-label="Search findings by file path or message"
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
              role="button"
              tabindex="0"
              :aria-expanded="expandedRow === index"
              :aria-label="`${finding.severity} severity finding in ${finding.file_path}, click to expand details`"
              @keydown.enter="toggleExpand(index)"
              @keydown.space.prevent="toggleExpand(index)"
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
                    <button
                      @click.stop="copyPath(finding)"
                      class="btn-small"
                      aria-label="Copy file path to clipboard"
                    >
                      <i class="fas fa-copy" aria-hidden="true"></i> Copy Path
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
/* Issue #901: Technical Precision FindingsTable Design */
.findings-table {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: 4px;
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
  border: 1px solid var(--border-default);
  border-radius: 2px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-family: var(--font-sans);
  font-size: 13px;
  width: 200px;
  transition: all 150ms cubic-bezier(0.4, 0, 0.2, 1);
}

.search-input:focus {
  outline: none;
  border-color: var(--color-info);
  box-shadow: 0 0 0 3px var(--color-info-bg);
}

/* Issue #901: Technical Precision severity badges */
.severity-badge {
  padding: 2px 8px;
  border-radius: 2px;
  font-size: 11px;
  font-weight: 500;
  font-family: var(--font-sans);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.severity-badge.critical {
  background: var(--color-error-bg);
  color: var(--color-error-dark);
}

.severity-badge.high {
  background: var(--color-warning-bg);
  color: var(--color-warning-dark);
}

.severity-badge.medium {
  background: rgba(234, 179, 8, 0.1);
  color: rgb(161, 98, 7);
}

.severity-badge.low {
  background: var(--color-info-bg);
  color: var(--color-info-dark);
}

.severity-badge.info {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

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
  border: 2px solid var(--border-default);
  border-top-color: var(--color-info);
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

/* Issue #901: Monospace for file paths and line numbers */
code {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-primary);
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}

.detail-row td {
  padding: 0;
  background: var(--bg-tertiary);
}

.detail-card {
  padding: var(--spacing-4);
  border-left: 2px solid var(--color-info);
  margin: var(--spacing-2);
  background: var(--bg-secondary);
  border-radius: 2px;
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

/* Issue #901: Electric blue for OWASP tags */
.owasp-tag {
  display: inline-block;
  padding: 2px 8px;
  background: var(--color-info-bg);
  color: var(--color-info-dark);
  border-radius: 2px;
  font-size: 12px;
  font-family: var(--font-mono);
  font-weight: 500;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.detail-actions {
  display: flex;
  gap: var(--spacing-2);
  margin-top: var(--spacing-3);
}

/* Issue #901: Technical Precision button styling */
.btn-small {
  padding: 6px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 2px;
  color: var(--text-primary);
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  font-family: var(--font-sans);
  transition: all 150ms cubic-bezier(0.4, 0, 0.2, 1);
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.btn-small:hover {
  background: var(--bg-hover);
  border-color: var(--border-strong);
}
</style>
