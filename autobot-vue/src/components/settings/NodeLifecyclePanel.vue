<template>
  <div class="lifecycle-panel">
    <!-- Header with host info and current operation -->
    <div class="panel-header">
      <div class="header-info">
        <h5>{{ nodeName }} - Events Log</h5>
        <div v-if="currentOperation" class="current-operation">
          <i class="fas fa-spinner fa-spin"></i>
          <span>{{ currentOperation }}</span>
        </div>
      </div>
    </div>

    <!-- Action bar for updates (oVirt style) -->
    <div class="action-bar">
      <div class="updates-info">
        <span v-if="props.availableUpdates?.count" class="updates-available">
          <i class="fas fa-arrow-circle-up"></i>
          {{ props.availableUpdates.count }} updates available
          <span v-if="props.availableUpdates.security" class="security-count">
            ({{ props.availableUpdates.security }} security)
          </span>
        </span>
        <span v-else class="no-updates">
          <i class="fas fa-check-circle"></i>
          System up to date
        </span>
      </div>
      <div class="action-buttons">
        <button
          @click="$emit('checkUpdates')"
          class="btn-secondary"
          :disabled="props.isCheckingUpdates"
        >
          <i :class="props.isCheckingUpdates ? 'fas fa-spinner fa-spin' : 'fas fa-search'"></i>
          {{ props.isCheckingUpdates ? 'Checking...' : 'Check for Updates' }}
        </button>
        <button
          v-if="props.availableUpdates?.count"
          @click="handleApplyUpdates"
          class="btn-primary"
          :disabled="props.isUpdating"
        >
          <i :class="props.isUpdating ? 'fas fa-spinner fa-spin' : 'fas fa-download'"></i>
          {{ props.isUpdating ? 'Updating...' : 'Install Updates' }}
        </button>
      </div>
    </div>

    <!-- Filter bar (oVirt style) -->
    <div class="filter-bar">
      <div class="filter-group">
        <label>Filter:</label>
        <select v-model="eventFilter" class="filter-select">
          <option value="all">All Events</option>
          <option value="update">Updates</option>
          <option value="enrollment">Enrollment</option>
          <option value="status">Status Changes</option>
          <option value="maintenance">Maintenance</option>
        </select>
      </div>
      <div class="filter-group">
        <label>Severity:</label>
        <select v-model="severityFilter" class="filter-select">
          <option value="all">All</option>
          <option value="success">Success</option>
          <option value="info">Info</option>
          <option value="warning">Warning</option>
          <option value="error">Error</option>
        </select>
      </div>
      <div class="events-summary">
        <span class="summary-count">{{ filteredEvents.length }} events</span>
        <span v-if="totalEvents > events.length" class="summary-note">
          (showing latest {{ events.length }})
        </span>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <span>Loading events...</span>
    </div>

    <!-- Empty State -->
    <div v-else-if="filteredEvents.length === 0" class="empty-state">
      <i class="fas fa-clipboard-list"></i>
      <p v-if="events.length === 0">No events recorded yet</p>
      <p v-else>No events match the current filter</p>
    </div>

    <!-- Events Table (oVirt style) -->
    <div v-else class="events-table-wrapper">
      <table class="events-table">
        <thead>
          <tr>
            <th class="col-severity"></th>
            <th class="col-time">Time</th>
            <th class="col-type">Event Type</th>
            <th class="col-message">Message</th>
            <th class="col-user">User</th>
            <th class="col-duration">Duration</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="event in filteredEvents"
            :key="event.id"
            class="event-row"
            :class="event.severity"
          >
            <td class="col-severity">
              <span class="severity-icon" :class="event.severity">
                <i :class="getSeverityIcon(event.severity)"></i>
              </span>
            </td>
            <td class="col-time">
              <span class="time-full">{{ formatFullTime(event.timestamp) }}</span>
              <span class="time-relative">{{ formatTime(event.timestamp) }}</span>
            </td>
            <td class="col-type">
              <span class="event-type-badge" :class="getEventCategory(event.event_type)">
                <i :class="getEventIcon(event.event_type)"></i>
                {{ formatEventType(event.event_type) }}
              </span>
            </td>
            <td class="col-message">
              <span class="event-message">{{ event.message }}</span>
              <div v-if="event.details && Object.keys(event.details).length > 0" class="event-details">
                <span
                  v-for="(value, key) in event.details"
                  :key="key"
                  class="detail-chip"
                >
                  {{ formatDetailKey(key) }}: {{ value }}
                </span>
              </div>
            </td>
            <td class="col-user">
              <span class="user-badge">
                <i class="fas fa-robot"></i>
                System
              </span>
            </td>
            <td class="col-duration">
              <span v-if="event.duration_ms" class="duration-value">
                {{ formatDuration(event.duration_ms) }}
              </span>
              <span v-else class="duration-na">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Footer with auto-refresh -->
    <div class="panel-footer">
      <label class="auto-refresh">
        <input type="checkbox" v-model="autoRefresh" />
        Auto-refresh (every 5s)
      </label>
      <span class="last-refresh" v-if="lastRefresh">
        Last updated: {{ formatTime(lastRefresh) }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { getBackendUrl } from '@/config/ssot-config'

const logger = createLogger('NodeLifecyclePanel')

// Types
interface LifecycleEvent {
  id: string
  event_type: string
  timestamp: string
  message: string
  details?: Record<string, any>
  severity: string
  duration_ms?: number
}

// Props
interface Props {
  nodeId: string
  nodeName: string
  availableUpdates?: { count: number; security: number }
  isUpdating?: boolean
  isCheckingUpdates?: boolean
}

const props = defineProps<Props>()

// Emits
const emit = defineEmits<{
  close: []
  checkUpdates: []
  applyUpdates: []
}>()

// Handler functions with debug logging
function handleApplyUpdates() {
  logger.info('Install Updates button clicked')
  logger.info('Emitting applyUpdates event for node: %s', props.nodeId)
  emit('applyUpdates')
  logger.info('applyUpdates event emitted')
}

// State
const events = ref<LifecycleEvent[]>([])
const isLoading = ref(true)
const currentOperation = ref<string | null>(null)
const totalEvents = ref(0)
const autoRefresh = ref(true)
const lastRefresh = ref<string | null>(null)

// Filters
const eventFilter = ref<'all' | 'update' | 'enrollment' | 'status' | 'maintenance'>('all')
const severityFilter = ref<'all' | 'success' | 'info' | 'warning' | 'error'>('all')

// WebSocket connection
let ws: WebSocket | null = null
let refreshInterval: ReturnType<typeof setInterval> | null = null

// Computed
const filteredEvents = computed(() => {
  return events.value.filter(event => {
    // Event type filter
    if (eventFilter.value !== 'all') {
      const category = getEventCategory(event.event_type)
      if (category !== eventFilter.value) return false
    }

    // Severity filter
    if (severityFilter.value !== 'all') {
      if (event.severity !== severityFilter.value) return false
    }

    return true
  })
})

// Methods
async function fetchLifecycleEvents() {
  try {
    const backendUrl = getBackendUrl()
    const response = await fetch(`${backendUrl}/api/infrastructure/nodes/${props.nodeId}/lifecycle?limit=100`)

    if (!response.ok) {
      throw new Error(`Failed to fetch lifecycle: ${response.statusText}`)
    }

    const data = await response.json()
    events.value = data.events || []
    currentOperation.value = data.current_operation
    totalEvents.value = data.total_events
    lastRefresh.value = new Date().toISOString()
  } catch (error) {
    logger.error('Failed to fetch lifecycle events:', error)
  } finally {
    isLoading.value = false
  }
}

function connectWebSocket() {
  const backendUrl = getBackendUrl()
  const wsUrl = backendUrl.replace(/^http/, 'ws') + '/api/ws/infrastructure/nodes'

  try {
    ws = new WebSocket(wsUrl)

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)

        // Only handle events for this node
        if (data.node_id !== props.nodeId) return

        if (data.type === 'lifecycle_event') {
          // Add new event to the top
          events.value.unshift(data.payload)
          totalEvents.value++

          // Keep list manageable
          if (events.value.length > 100) {
            events.value = events.value.slice(0, 100)
          }
        }
      } catch (e) {
        logger.error('Failed to parse WebSocket message:', e)
      }
    }

    ws.onerror = (error) => {
      logger.error('WebSocket error:', error)
    }
  } catch (error) {
    logger.error('Failed to connect WebSocket:', error)
  }
}

function getEventCategory(eventType: string): string {
  if (eventType.includes('update')) return 'update'
  if (eventType.includes('enrollment') || eventType === 'created') return 'enrollment'
  if (eventType.includes('status') || eventType.includes('connection') || eventType.includes('health')) return 'status'
  if (eventType.includes('maintenance') || eventType.includes('role')) return 'maintenance'
  return 'status'
}

function getEventIcon(eventType: string): string {
  const icons: Record<string, string> = {
    created: 'fas fa-plus-circle',
    enrolling: 'fas fa-cog',
    enrollment_step: 'fas fa-tasks',
    enrollment_complete: 'fas fa-check-circle',
    enrollment_failed: 'fas fa-times-circle',
    connection_test: 'fas fa-plug',
    update_started: 'fas fa-download',
    update_progress: 'fas fa-sync',
    update_complete: 'fas fa-check-circle',
    update_failed: 'fas fa-exclamation-triangle',
    role_change: 'fas fa-exchange-alt',
    status_change: 'fas fa-toggle-on',
    health_check: 'fas fa-heartbeat',
    maintenance_start: 'fas fa-wrench',
    maintenance_end: 'fas fa-check',
  }
  return icons[eventType] || 'fas fa-info-circle'
}

function getSeverityIcon(severity: string): string {
  const icons: Record<string, string> = {
    success: 'fas fa-check-circle',
    info: 'fas fa-info-circle',
    warning: 'fas fa-exclamation-triangle',
    error: 'fas fa-times-circle',
  }
  return icons[severity] || 'fas fa-circle'
}

function formatEventType(eventType: string): string {
  return eventType
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

function formatDetailKey(key: string): string {
  return key
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

function formatTime(timestamp: string): string {
  const date = new Date(timestamp)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()

  if (diffMs < 60000) {
    return 'Just now'
  } else if (diffMs < 3600000) {
    const mins = Math.floor(diffMs / 60000)
    return `${mins}m ago`
  } else if (diffMs < 86400000) {
    const hours = Math.floor(diffMs / 3600000)
    return `${hours}h ago`
  } else {
    const days = Math.floor(diffMs / 86400000)
    return `${days}d ago`
  }
}

function formatFullTime(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

function formatDuration(ms: number): string {
  if (ms < 1000) {
    return `${ms}ms`
  } else if (ms < 60000) {
    return `${(ms / 1000).toFixed(1)}s`
  } else {
    const mins = Math.floor(ms / 60000)
    const secs = Math.floor((ms % 60000) / 1000)
    return `${mins}m ${secs}s`
  }
}

// Watch for auto-refresh changes
watch(autoRefresh, (enabled) => {
  if (enabled) {
    refreshInterval = setInterval(fetchLifecycleEvents, 5000)
  } else if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
})

// Lifecycle
onMounted(() => {
  fetchLifecycleEvents()
  connectWebSocket()

  if (autoRefresh.value) {
    refreshInterval = setInterval(fetchLifecycleEvents, 5000)
  }
})

onUnmounted(() => {
  if (ws) {
    ws.close()
  }
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})
</script>

<style scoped>
.lifecycle-panel {
  background: var(--bg-primary);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  max-height: 500px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-light);
  flex-shrink: 0;
}

.header-info h5 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.current-operation {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-info);
}

/* Action Bar */
.action-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-light);
  flex-shrink: 0;
}

.updates-info {
  font-size: 13px;
}

.updates-available {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--color-warning);
  font-weight: 500;
}

.updates-available i {
  font-size: 14px;
}

.security-count {
  color: var(--color-danger);
  font-size: 12px;
}

.no-updates {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--color-success);
}

.no-updates i {
  font-size: 14px;
}

.action-buttons {
  display: flex;
  gap: 8px;
}

.btn-secondary {
  padding: 8px 14px;
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s;
}

.btn-secondary:hover:not(:disabled) {
  background: var(--bg-tertiary);
  border-color: var(--text-tertiary);
}

.btn-secondary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-primary {
  padding: 8px 14px;
  background: var(--color-primary);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s;
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Filter Bar */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 16px;
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-light);
  flex-shrink: 0;
}

.filter-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-group label {
  font-size: 12px;
  color: var(--text-tertiary);
}

.filter-select {
  padding: 4px 8px;
  font-size: 12px;
  border: 1px solid var(--border-default);
  border-radius: 4px;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.events-summary {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-tertiary);
}

.summary-count {
  font-weight: 500;
  color: var(--text-secondary);
}

/* Loading/Empty States */
.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px;
  color: var(--text-tertiary);
  gap: 12px;
}

.loading-state i,
.empty-state i {
  font-size: 32px;
}

/* Events Table (oVirt style) */
.events-table-wrapper {
  flex: 1;
  overflow-y: auto;
  min-height: 200px;
}

.events-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.events-table thead {
  position: sticky;
  top: 0;
  background: var(--bg-secondary);
  z-index: 1;
}

.events-table th {
  padding: 10px 12px;
  text-align: left;
  font-weight: 600;
  color: var(--text-secondary);
  font-size: 11px;
  text-transform: uppercase;
  border-bottom: 2px solid var(--border-light);
}

.events-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-light);
  vertical-align: top;
}

.events-table tr:hover {
  background: var(--bg-secondary);
}

/* Column widths */
.col-severity { width: 32px; }
.col-time { width: 140px; }
.col-type { width: 150px; }
.col-message { flex: 1; }
.col-user { width: 80px; }
.col-duration { width: 80px; }

/* Severity icons */
.severity-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  font-size: 12px;
}

.severity-icon.success {
  background: var(--color-success-bg, rgba(34, 197, 94, 0.15));
  color: var(--color-success, #22c55e);
}

.severity-icon.info {
  background: var(--color-info-bg, rgba(59, 130, 246, 0.15));
  color: var(--color-info, #3b82f6);
}

.severity-icon.warning {
  background: var(--color-warning-bg, rgba(245, 158, 11, 0.15));
  color: var(--color-warning, #f59e0b);
}

.severity-icon.error {
  background: var(--color-danger-bg, rgba(239, 68, 68, 0.15));
  color: var(--color-danger, #ef4444);
}

/* Time column */
.col-time {
  white-space: nowrap;
}

.time-full {
  display: block;
  font-size: 12px;
  color: var(--text-primary);
}

.time-relative {
  display: block;
  font-size: 11px;
  color: var(--text-tertiary);
}

/* Event type badge */
.event-type-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.event-type-badge.update {
  background: var(--color-info-bg, rgba(59, 130, 246, 0.15));
  color: var(--color-info, #3b82f6);
}

.event-type-badge.enrollment {
  background: var(--color-primary-bg, rgba(99, 102, 241, 0.15));
  color: var(--color-primary, #6366f1);
}

.event-type-badge.status {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.event-type-badge.maintenance {
  background: var(--color-warning-bg, rgba(245, 158, 11, 0.15));
  color: var(--color-warning, #f59e0b);
}

/* Message column */
.event-message {
  color: var(--text-primary);
  word-break: break-word;
}

.event-details {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.detail-chip {
  font-size: 11px;
  padding: 2px 6px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  color: var(--text-secondary);
}

/* User badge */
.user-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.user-badge i {
  font-size: 11px;
}

/* Duration column */
.duration-value {
  font-family: monospace;
  font-size: 12px;
  color: var(--text-secondary);
}

.duration-na {
  color: var(--text-tertiary);
}

/* Footer */
.panel-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  border-top: 1px solid var(--border-light);
  background: var(--bg-secondary);
  flex-shrink: 0;
}

.auto-refresh {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
}

.auto-refresh input {
  cursor: pointer;
}

.last-refresh {
  font-size: 11px;
  color: var(--text-tertiary);
}

/* Row severity styling */
.event-row.error {
  background: var(--color-danger-bg, rgba(239, 68, 68, 0.05));
}

.event-row.warning {
  background: var(--color-warning-bg, rgba(245, 158, 11, 0.05));
}

/* Responsive */
@media (max-width: 768px) {
  .action-bar {
    flex-direction: column;
    gap: 12px;
    align-items: flex-start;
  }

  .filter-bar {
    flex-wrap: wrap;
  }

  .events-summary {
    width: 100%;
    margin-left: 0;
    margin-top: 8px;
  }

  .col-user,
  .col-duration {
    display: none;
  }

  .events-table th,
  .events-table td {
    padding: 8px;
  }
}
</style>
