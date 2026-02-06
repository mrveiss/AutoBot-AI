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
