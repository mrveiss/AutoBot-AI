<template>
  <div class="audit-log-table">
    <!-- Table Header with Actions -->
    <div class="table-header">
      <div class="table-info">
        <span class="result-count">
          {{ entries.length }} {{ entries.length === 1 ? 'entry' : 'entries' }}
          <span v-if="hasMore" class="more-indicator">(more available)</span>
        </span>
      </div>
      <div class="table-actions">
        <button
          class="btn btn-icon"
          @click="$emit('refresh')"
          title="Refresh"
          aria-label="Refresh audit log entries"
        >
          <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }" aria-hidden="true"></i>
        </button>
        <div class="export-dropdown">
          <button
            class="btn btn-secondary"
            @click="toggleExportMenu"
            aria-label="Export audit logs"
            :aria-expanded="showExportMenu"
          >
            <i class="fas fa-download" aria-hidden="true"></i>
            Export
          </button>
          <div v-if="showExportMenu" class="dropdown-menu" role="menu">
            <button @click="exportLogs('json')" role="menuitem" aria-label="Export as JSON">
              <i class="fas fa-file-code" aria-hidden="true"></i>
              Export JSON
            </button>
            <button @click="exportLogs('csv')" role="menuitem" aria-label="Export as CSV">
              <i class="fas fa-file-csv" aria-hidden="true"></i>
              Export CSV
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Table Container -->
    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th
              class="col-timestamp"
              @click="sortBy('timestamp')"
              role="button"
              tabindex="0"
              :aria-sort="sortField === 'timestamp' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'"
              aria-label="Sort by timestamp"
              @keydown.enter="sortBy('timestamp')"
              @keydown.space.prevent="sortBy('timestamp')"
            >
              <span>Timestamp</span>
              <i v-if="sortField === 'timestamp'" :class="sortIcon" aria-hidden="true"></i>
            </th>
            <th
              class="col-operation"
              @click="sortBy('operation')"
              role="button"
              tabindex="0"
              :aria-sort="sortField === 'operation' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'"
              aria-label="Sort by operation"
              @keydown.enter="sortBy('operation')"
              @keydown.space.prevent="sortBy('operation')"
            >
              <span>Operation</span>
              <i v-if="sortField === 'operation'" :class="sortIcon" aria-hidden="true"></i>
            </th>
            <th class="col-result">Result</th>
            <th class="col-user">User</th>
            <th class="col-session">Session</th>
            <th class="col-vm">VM</th>
            <th class="col-actions">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="entry in sortedEntries"
            :key="entry.id"
            :class="['entry-row', `result-${entry.result}`]"
            @click="selectEntry(entry)"
          >
            <td class="col-timestamp">
              <span class="timestamp-full mono-timestamp">{{ formatTimestamp(entry.timestamp) }}</span>
              <span class="timestamp-relative">{{ formatRelativeTime(entry.timestamp) }}</span>
            </td>
            <td class="col-operation">
              <span class="operation-name">{{ formatOperationName(entry.operation) }}</span>
            </td>
            <td class="col-result">
              <span :class="['result-badge', `badge-${entry.result}`]">
                <i :class="resultIcon(entry.result)"></i>
                {{ entry.result }}
              </span>
            </td>
            <td class="col-user">
              <button
                v-if="entry.user_id"
                class="link-btn mono-id"
                @click.stop="$emit('user-click', entry.user_id)"
              >
                {{ entry.user_id }}
              </button>
              <span v-else class="empty-value">-</span>
            </td>
            <td class="col-session">
              <button
                v-if="entry.session_id"
                class="link-btn mono-id"
                @click.stop="$emit('session-click', entry.session_id)"
              >
                {{ truncateId(entry.session_id) }}
              </button>
              <span v-else class="empty-value">-</span>
            </td>
            <td class="col-vm">
              <span v-if="entry.vm_name">{{ entry.vm_name }}</span>
              <span v-else class="empty-value">-</span>
            </td>
            <td class="col-actions">
              <button
                class="btn btn-icon btn-small"
                @click.stop="showDetails(entry)"
                title="View Details"
              >
                <i class="fas fa-eye"></i>
              </button>
            </td>
          </tr>
          <tr v-if="entries.length === 0 && !loading">
            <td colspan="7" class="empty-state">
              <i class="fas fa-inbox"></i>
              <span>No audit logs found</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div class="table-pagination">
      <button
        class="btn btn-secondary"
        :disabled="currentPage <= 1"
        @click="$emit('prev-page')"
      >
        <i class="fas fa-chevron-left"></i>
        Previous
      </button>
      <span class="page-info">Page {{ currentPage }}</span>
      <button
        class="btn btn-secondary"
        :disabled="!hasMore"
        @click="$emit('next-page')"
      >
        Next
        <i class="fas fa-chevron-right"></i>
      </button>
    </div>

    <!-- Detail Modal -->
    <div v-if="selectedEntry" class="modal-overlay" @click="closeDetails">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>Audit Entry Details</h3>
          <button class="btn btn-icon" @click="closeDetails">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body">
          <div class="detail-grid">
            <div class="detail-item">
              <label>ID</label>
              <span class="mono">{{ selectedEntry.id }}</span>
            </div>
            <div class="detail-item">
              <label>Timestamp</label>
              <span>{{ formatTimestamp(selectedEntry.timestamp) }}</span>
            </div>
            <div class="detail-item">
              <label>Operation</label>
              <span>{{ formatOperationName(selectedEntry.operation) }}</span>
            </div>
            <div class="detail-item">
              <label>Result</label>
              <span :class="['result-badge', `badge-${selectedEntry.result}`]">
                <i :class="resultIcon(selectedEntry.result)"></i>
                {{ selectedEntry.result }}
              </span>
            </div>
            <div class="detail-item">
              <label>User ID</label>
              <span>{{ selectedEntry.user_id || '-' }}</span>
            </div>
            <div class="detail-item">
              <label>Session ID</label>
              <span class="mono">{{ selectedEntry.session_id || '-' }}</span>
            </div>
            <div class="detail-item">
              <label>VM Name</label>
              <span>{{ selectedEntry.vm_name || '-' }}</span>
            </div>
            <div class="detail-item">
              <label>VM Source</label>
              <span>{{ selectedEntry.vm_source || '-' }}</span>
            </div>
            <div class="detail-item">
              <label>IP Address</label>
              <span class="mono">{{ selectedEntry.ip_address || '-' }}</span>
            </div>
            <div v-if="selectedEntry.error_message" class="detail-item detail-full">
              <label>Error Message</label>
              <span class="error-message">{{ selectedEntry.error_message }}</span>
            </div>
            <div v-if="hasDetails" class="detail-item detail-full">
              <label>Details</label>
              <pre class="details-json">{{ formatDetails(selectedEntry.details) }}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Loading Overlay -->
    <div v-if="loading" class="loading-overlay">
      <i class="fas fa-spinner fa-spin"></i>
      <span>Loading audit logs...</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { AuditEntry } from '@/types/audit'
import { formatAuditTimestamp, formatAuditRelativeTime, AUDIT_RESULT_CONFIG } from '@/types/audit'

interface Props {
  entries: AuditEntry[]
  loading?: boolean
  hasMore?: boolean
  currentPage?: number
}

interface Emits {
  (e: 'refresh'): void
  (e: 'export', format: 'json' | 'csv'): void
  (e: 'entry-select', entry: AuditEntry): void
  (e: 'user-click', userId: string): void
  (e: 'session-click', sessionId: string): void
  (e: 'next-page'): void
  (e: 'prev-page'): void
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  hasMore: false,
  currentPage: 1
})

const emit = defineEmits<Emits>()

const selectedEntry = ref<AuditEntry | null>(null)
const showExportMenu = ref(false)
const sortField = ref<'timestamp' | 'operation'>('timestamp')
const sortDirection = ref<'asc' | 'desc'>('desc')

const sortIcon = computed(() =>
  sortDirection.value === 'asc' ? 'fas fa-sort-up' : 'fas fa-sort-down'
)

const sortedEntries = computed(() => {
  const entries = [...props.entries]
  entries.sort((a, b) => {
    let comparison = 0
    if (sortField.value === 'timestamp') {
      comparison = new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    } else if (sortField.value === 'operation') {
      comparison = a.operation.localeCompare(b.operation)
    }
    return sortDirection.value === 'asc' ? comparison : -comparison
  })
  return entries
})

const hasDetails = computed(() => {
  if (!selectedEntry.value?.details) return false
  return Object.keys(selectedEntry.value.details).length > 0
})

function formatTimestamp(timestamp: string): string {
  return formatAuditTimestamp(timestamp)
}

function formatRelativeTime(timestamp: string): string {
  return formatAuditRelativeTime(timestamp)
}

function formatOperationName(operation: string): string {
  return operation
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function resultIcon(result: string): string {
  const config = AUDIT_RESULT_CONFIG[result as keyof typeof AUDIT_RESULT_CONFIG]
  return config?.icon || 'fas fa-question-circle'
}

function truncateId(id: string): string {
  if (id.length <= 12) return id
  return `${id.substring(0, 8)}...`
}

function formatDetails(details: Record<string, unknown>): string {
  return JSON.stringify(details, null, 2)
}

function sortBy(field: 'timestamp' | 'operation') {
  if (sortField.value === field) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortField.value = field
    sortDirection.value = 'desc'
  }
}

function selectEntry(entry: AuditEntry) {
  emit('entry-select', entry)
}

function showDetails(entry: AuditEntry) {
  selectedEntry.value = entry
}

function closeDetails() {
  selectedEntry.value = null
}

function toggleExportMenu() {
  showExportMenu.value = !showExportMenu.value
}

function exportLogs(format: 'json' | 'csv') {
  emit('export', format)
  showExportMenu.value = false
}
</script>

<style scoped>
/* Issue #901: Technical Precision AuditLogTable Design */
.audit-log-table {
  position: relative;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  overflow: hidden;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-3) var(--spacing-4);
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.table-info {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.more-indicator {
  color: var(--color-primary);
}

.table-actions {
  display: flex;
  gap: var(--spacing-2);
}

.export-dropdown {
  position: relative;
}

.dropdown-menu {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: var(--spacing-1);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 4px;
  box-shadow: var(--shadow-lg);
  z-index: 10;
  min-width: 150px;
}

.dropdown-menu button {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  width: 100%;
  padding: var(--spacing-2) var(--spacing-3);
  border: none;
  background: transparent;
  color: var(--text-primary);
  font-size: var(--text-sm);
  cursor: pointer;
  text-align: left;
}

.dropdown-menu button:hover {
  background: var(--bg-hover);
}

.table-container {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th, td {
  padding: var(--spacing-3) var(--spacing-4);
  text-align: left;
  border-bottom: 1px solid var(--border-subtle);
}

th {
  font-weight: var(--font-semibold);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  background: var(--bg-secondary);
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}

th:hover {
  color: var(--text-primary);
}

th span {
  margin-right: var(--spacing-1);
}

.entry-row {
  cursor: pointer;
  transition: background var(--duration-200) var(--ease-in-out);
}

.entry-row:hover {
  background: var(--bg-hover);
}

.entry-row.result-denied {
  background: rgba(239, 68, 68, 0.05);
}

.entry-row.result-failed {
  background: rgba(249, 115, 22, 0.05);
}

.entry-row.result-error {
  background: rgba(234, 179, 8, 0.05);
}

.col-timestamp {
  min-width: 180px;
}

.timestamp-full {
  display: block;
  font-size: var(--text-sm);
  color: var(--text-primary);
}

/* Issue #901: Monospace font for timestamps */
.mono-timestamp {
  font-family: var(--font-mono);
  font-size: 12px;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}

.timestamp-relative {
  display: block;
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  font-family: var(--font-sans);
}

.col-operation {
  min-width: 200px;
}

.operation-name {
  font-weight: var(--font-medium);
}

.col-result {
  min-width: 100px;
}

/* Issue #901: Technical Precision badges */
.result-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  padding: var(--spacing-1) var(--spacing-2);
  border-radius: 2px;
  font-size: 11px;
  font-weight: 500;
  font-family: var(--font-sans);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.badge-success {
  background: var(--color-success-bg);
  color: var(--color-success-dark);
}

.badge-denied {
  background: var(--color-error-bg);
  color: var(--color-error-dark);
}

.badge-failed {
  background: var(--color-warning-bg);
  color: var(--color-warning-dark);
}

.badge-error {
  background: var(--color-warning-bg);
  color: var(--color-warning-dark);
}

.col-user, .col-session {
  min-width: 120px;
}

.link-btn {
  background: none;
  border: none;
  color: var(--color-info);
  font-size: inherit;
  cursor: pointer;
  padding: 0;
  text-decoration: underline;
  font-family: var(--font-sans);
}

.link-btn:hover {
  color: var(--color-info-dark);
}

/* Issue #901: Monospace font for IDs */
.mono-id {
  font-family: var(--font-mono);
  font-size: 12px;
  letter-spacing: -0.02em;
}

.empty-value {
  color: var(--text-tertiary);
}

.col-vm {
  min-width: 100px;
}

.col-actions {
  width: 60px;
  text-align: center;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3);
  border-radius: var(--radius-default);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-in-out);
  border: none;
}

.btn-icon {
  padding: var(--spacing-2);
  background: transparent;
  color: var(--text-secondary);
}

.btn-icon:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.btn-small {
  padding: var(--spacing-1);
}

.btn-secondary {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--bg-hover);
}

.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.empty-state {
  text-align: center;
  padding: var(--spacing-8) !important;
  color: var(--text-tertiary);
}

.empty-state i {
  font-size: var(--text-3xl);
  margin-bottom: var(--spacing-2);
  display: block;
}

.table-pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: var(--spacing-4);
  padding: var(--spacing-3) var(--spacing-4);
  border-top: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

.page-info {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

/* Modal Styles */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: var(--spacing-4);
}

.modal-content {
  background: var(--bg-card);
  border-radius: 4px;
  max-width: 700px;
  width: 100%;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-default);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-4);
  border-bottom: 1px solid var(--border-default);
}

.modal-header h3 {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
}

.modal-body {
  padding: var(--spacing-4);
  overflow-y: auto;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--spacing-4);
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.detail-item label {
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  color: var(--text-secondary);
  text-transform: uppercase;
}

.detail-item span {
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.detail-full {
  grid-column: span 2;
}

/* Issue #901: Monospace for technical data in modal */
.mono {
  font-family: var(--font-mono);
  font-size: 12px;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}

.error-message {
  color: var(--color-error);
  background: var(--color-error-bg);
  padding: var(--spacing-2);
  border-radius: 2px;
  font-family: var(--font-mono);
  font-size: 12px;
}

.details-json {
  font-family: var(--font-mono);
  font-size: 12px;
  background: var(--bg-secondary);
  padding: var(--spacing-3);
  border-radius: 2px;
  overflow-x: auto;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  letter-spacing: -0.02em;
  line-height: 1.5;
}

.loading-overlay {
  position: absolute;
  inset: 0;
  background: rgba(var(--bg-card-rgb), 0.8);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  color: var(--text-secondary);
}

.loading-overlay i {
  font-size: var(--text-2xl);
  color: var(--color-primary);
}

@media (max-width: 768px) {
  .table-header {
    flex-direction: column;
    gap: var(--spacing-2);
    align-items: stretch;
  }

  .table-actions {
    justify-content: flex-end;
  }

  .detail-grid {
    grid-template-columns: 1fr;
  }

  .detail-full {
    grid-column: span 1;
  }
}
</style>
