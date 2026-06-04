<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!-- Issue #566 - Code Intelligence Dashboard -->
<!-- Issue #4037 - Virtual scrolling for large findings tables (500+ rows) -->
<!-- Issue #4035 - Add debounce to search filters -->

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
          :placeholder="$t('analytics.findings.table.searchPlaceholder')"
          class="search-input"
          :aria-label="$t('analytics.findings.table.searchAriaLabel')"
        />
      </div>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <span>{{ $t('analytics.findings.table.loading') }}</span>
    </div>

    <!-- Empty state -->
    <div v-else-if="filteredFindings.length === 0" class="empty-state">
      <Icon name="check-circle" />
      <p>{{ emptyMessage }}</p>
    </div>

    <!-- Table with virtual scrolling -->
    <div v-else class="table-container">
      <table>
        <thead class="sticky top-0 z-10">
          <tr>
            <th class="col-severity">{{ $t('analytics.findings.table.severity') }}</th>
            <th class="col-file">{{ $t('analytics.findings.table.fileLine') }}</th>
            <th class="col-type">{{ $t('analytics.findings.table.type') }}</th>
            <th class="col-message">{{ $t('analytics.findings.table.message') }}</th>
          </tr>
        </thead>
        <tbody :style="{ height: totalHeight + 'px', position: 'relative' }">
          <!-- Virtualized findings rows -->
          <template v-for="virtualItem in visibleItems" :key="virtualItem.index">
            <tr
              @click="toggleExpand(virtualItem.index)"
              :class="{ expanded: isRowExpanded(virtualItem.index) }"
              class="finding-row"
              role="button"
              tabindex="0"
              :aria-expanded="isRowExpanded(virtualItem.index)"
              :aria-label="`${virtualItem.data.severity} severity finding in ${virtualItem.data.file_path}, click to expand details`"
              @keydown.enter="toggleExpand(virtualItem.index)"
              @keydown.space.prevent="toggleExpand(virtualItem.index)"
              :style="{ transform: `translateY(${virtualItem.offset}px)` }"
            >
              <td class="col-severity">
                <span :class="['severity-badge', virtualItem.data.severity]">
                  {{ getSeverityIcon(virtualItem.data.severity) }} {{ virtualItem.data.severity }}
                </span>
              </td>
              <td class="col-file">
                <code>{{ formatFilePath(virtualItem.data.file_path) }}:{{ virtualItem.data.line_number }}</code>
              </td>
              <td class="col-type">{{ getTypeDisplay(virtualItem.data) }}</td>
              <td class="col-message">{{ truncateMessage(virtualItem.data.message) }}</td>
            </tr>
            <!-- Expanded detail card -->
            <tr v-if="isRowExpanded(virtualItem.index)" class="detail-row">
              <td colspan="4">
                <div class="detail-card">
                  <div class="detail-section">
                    <strong>{{ $t('analytics.findings.table.fullMessage') }}</strong>
                    <p>{{ virtualItem.data.message }}</p>
                  </div>
                  <div class="detail-section">
                    <strong>{{ $t('analytics.findings.table.recommendation') }}</strong>
                    <p>{{ getRemediation(virtualItem.data) }}</p>
                  </div>
                  <div v-if="virtualItem.data.owasp_category" class="detail-section">
                    <strong>{{ $t('analytics.findings.table.owasp') }}</strong>
                    <span class="owasp-tag">{{ virtualItem.data.owasp_category }}</span>
                  </div>
                  <div class="detail-actions">
                    <button
                      @click.stop="copyPath(virtualItem.data)"
                      class="btn-small"
                      :aria-label="$t('analytics.findings.table.copyPathAriaLabel')"
                    >
                      <Icon name="copy" /> {{ $t('analytics.findings.table.copyPath') }}
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
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useVirtualList } from '@/composables/useVirtualList'
import { useDebounce } from '@/composables/useDebounce'
import { useExpansion } from '@/composables/useExpansion'
import type { Severity } from '@/types/codeIntelligence'

const { t } = useI18n()

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
  id?: string
}

const props = defineProps<{
  findings: Finding[]
  loading: boolean
  emptyMessage: string
}>()

const severityLevels: Severity[] = ['critical', 'high', 'medium', 'low', 'info']
const selectedSeverities = ref<Severity[]>([...severityLevels])
const searchQuery = ref('')
const { isExpanded: isRowExpanded, expand: expandRow, collapseAll: collapseAllRows } = useExpansion<number>()

// Debounce search query for performance (Issue #4035)
// Reduces unnecessary filtering operations during rapid typing
const debouncedSearchQuery = useDebounce(searchQuery, 350)

const filteredFindings = computed<(Finding & { id: string })[]>(() => {
  return props.findings
    .filter(f => {
      const matchesSeverity = selectedSeverities.value.includes(f.severity)
      // Use debounced search query to prevent filtering on every keystroke
      const matchesSearch = debouncedSearchQuery.value === '' ||
        f.file_path.toLowerCase().includes(debouncedSearchQuery.value.toLowerCase()) ||
        f.message.toLowerCase().includes(debouncedSearchQuery.value.toLowerCase())
      return matchesSeverity && matchesSearch
    })
    .map((f, idx) => ({
      ...f,
      id: f.id || `finding_${idx}`
    })) as (Finding & { id: string })[]
})

// Virtual scrolling composable - Issue #4037
// Each finding row is approximately 50px, expanded detail rows are ~300px
// Use a conservative estimate to avoid layout shift
const { containerRef, visibleItems, totalHeight } = useVirtualList(filteredFindings, 50, 3)

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
  return finding.remediation || finding.recommendation || t('analytics.findings.table.noRecommendation')
}

function toggleExpand(index: number): void {
  const wasExpanded = isRowExpanded(index)
  collapseAllRows()
  if (!wasExpanded) expandRow(index)
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
  border-radius: var(--radius-default);
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
  border-radius: var(--radius-xs);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-family: var(--font-sans);
  font-size: var(--text-sm);
  width: 200px;
  transition: all var(--duration-150) var(--ease-in-out);
}

.search-input:focus {
  outline: none;
  border-color: var(--color-info);
  box-shadow: 0 0 0 3px var(--color-info-bg);
}
.search-input:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

/* Issue #901: Technical Precision severity badges */
.severity-badge {
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-xs);
  font-size: var(--text-xs);
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
  max-height: 600px;
  overflow-y: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  position: relative;
}

th, td {
  padding: var(--spacing-3);
  text-align: left;
  border-bottom: 1px solid var(--border-primary);
}

th {
  background: var(--bg-tertiary);
  font-weight: var(--font-medium);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.finding-row {
  cursor: pointer;
  transition: background var(--duration-150);
  position: relative;
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
  font-size: var(--text-xs);
  color: var(--text-primary);
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}

.detail-row td {
  padding: var(--spacing-0);
  background: var(--bg-tertiary);
}

.detail-card {
  padding: var(--spacing-4);
  border-left: 2px solid var(--color-info);
  margin: var(--spacing-2);
  background: var(--bg-secondary);
  border-radius: var(--radius-xs);
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
  margin: var(--spacing-0);
}

/* Issue #901: Electric blue for OWASP tags */
.owasp-tag {
  display: inline-block;
  padding: var(--spacing-0-5) var(--spacing-2);
  background: var(--color-info-bg);
  color: var(--color-info-dark);
  border-radius: var(--radius-xs);
  font-size: var(--text-xs);
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
  padding: var(--spacing-1-5) var(--spacing-3);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xs);
  color: var(--text-primary);
  cursor: pointer;
  font-size: var(--text-sm);
  font-weight: 500;
  font-family: var(--font-sans);
  transition: all var(--duration-150) var(--ease-in-out);
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1-5);
}

.btn-small:hover {
  background: var(--bg-hover);
  border-color: var(--border-strong);
}
</style>
