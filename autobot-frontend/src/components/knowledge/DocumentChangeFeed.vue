<template>
  <div class="document-change-feed">
    <!-- Header with Stats -->
    <div class="feed-header">
      <h3 class="feed-title">
        <i class="fas fa-sync-alt"></i>
        Document Changes
      </h3>

      <!-- Change Summary Badges -->
      <div class="change-badges">
        <span v-if="changeSummary.added > 0" class="badge badge-success">
          <i class="fas fa-plus-circle"></i>
          {{ changeSummary.added }} Added
        </span>
        <span v-if="changeSummary.updated > 0" class="badge badge-info">
          <i class="fas fa-sync-alt"></i>
          {{ changeSummary.updated }} Updated
        </span>
        <span v-if="changeSummary.removed > 0" class="badge badge-danger">
          <i class="fas fa-minus-circle"></i>
          {{ changeSummary.removed }} Removed
        </span>
        <span v-if="totalChanges === 0" class="badge badge-secondary">
          <i class="fas fa-check-circle"></i>
          No Changes
        </span>
      </div>
    </div>

    <!-- Controls -->
    <div class="feed-controls">
      <BaseButton
        variant="primary"
        size="sm"
        :loading="isScanning"
        @click="handleScanNow"
      >
        <i class="fas fa-search"></i>
        {{ isScanning ? 'Scanning...' : 'Scan Now' }}
      </BaseButton>

      <!-- Issue #425: Man Page Section Filter -->
      <div class="section-filter">
        <label class="filter-label">
          <i class="fas fa-book"></i>
          Section:
        </label>
        <select v-model="selectedSections" multiple class="section-select">
          <option value="1">1 - User Commands</option>
          <option value="2">2 - System Calls</option>
          <option value="3">3 - Library Functions</option>
          <option value="4">4 - Special Files</option>
          <option value="5">5 - File Formats</option>
          <option value="6">6 - Games</option>
          <option value="7">7 - Miscellaneous</option>
          <option value="8">8 - System Admin</option>
        </select>
      </div>

      <div class="auto-refresh-toggle">
        <label class="toggle-label">
          <input
            type="checkbox"
            v-model="autoRefreshEnabled"
            @change="handleAutoRefreshToggle"
          />
          <span>Auto-refresh (30m)</span>
        </label>
      </div>

      <div class="auto-vectorize-toggle">
        <label class="toggle-label">
          <input
            type="checkbox"
            v-model="autoVectorizeEnabled"
          />
          <span>Auto-vectorize changes</span>
        </label>
      </div>

      <div v-if="lastScanTime" class="last-scan">
        <i class="fas fa-clock"></i>
        Last scan: {{ formatRelativeTime(lastScanTime) }}
      </div>
    </div>

    <!-- Vectorization Status -->
    <div v-if="lastVectorizationResult" class="vectorization-status">
      <div class="status-header">
        <i class="fas fa-vector-square"></i>
        Vectorization Results
      </div>
      <div class="status-stats">
        <span class="stat-item stat-success">
          <i class="fas fa-check-circle"></i>
          {{ lastVectorizationResult.successful }} successful
        </span>
        <span class="stat-item stat-failed" v-if="lastVectorizationResult.failed > 0">
          <i class="fas fa-times-circle"></i>
          {{ lastVectorizationResult.failed }} failed
        </span>
        <span class="stat-item stat-skipped" v-if="lastVectorizationResult.skipped > 0">
          <i class="fas fa-minus-circle"></i>
          {{ lastVectorizationResult.skipped }} skipped
        </span>
      </div>
    </div>

    <!-- Change Feed -->
    <div class="change-list" v-if="recentChanges.length > 0">
      <div class="change-filters">
        <BaseButton
          :variant="activeFilter === 'all' ? 'primary' : 'outline'"
          size="sm"
          @click="activeFilter = 'all'"
        >
          All ({{ totalChanges }})
        </BaseButton>
        <BaseButton
          :variant="activeFilter === 'added' ? 'primary' : 'outline'"
          size="sm"
          @click="activeFilter = 'added'"
          v-if="changeSummary.added > 0"
        >
          Added ({{ changeSummary.added }})
        </BaseButton>
        <BaseButton
          :variant="activeFilter === 'updated' ? 'primary' : 'outline'"
          size="sm"
          @click="activeFilter = 'updated'"
          v-if="changeSummary.updated > 0"
        >
          Updated ({{ changeSummary.updated }})
        </BaseButton>
        <BaseButton
          :variant="activeFilter === 'removed' ? 'primary' : 'outline'"
          size="sm"
          @click="activeFilter = 'removed'"
          v-if="changeSummary.removed > 0"
        >
          Removed ({{ changeSummary.removed }})
        </BaseButton>
      </div>

      <div class="change-items">
        <div
          v-for="change in filteredChanges"
          :key="`${change.document_id}-${change.timestamp.getTime()}`"
          class="change-item"
          :class="`change-${change.change_type}`"
        >
          <div class="change-icon">
            <i :class="getChangeIcon(change.change_type)"></i>
          </div>

          <div class="change-content">
            <div class="change-title">
              {{ change.title }}
              <span v-if="change.command" class="change-command">({{ change.command }})</span>
            </div>

            <div class="change-meta">
              <span class="change-type-label">
                {{ getChangeTypeName(change.change_type) }}
              </span>
              <span class="change-time">
                {{ formatRelativeTime(change.timestamp) }}
              </span>
              <span v-if="change.content_size" class="change-size">
                {{ formatBytes(change.content_size) }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <EmptyState
      v-else
      icon="fas fa-inbox"
      message="No recent changes detected"
    >
      <template #actions>
        <BaseButton variant="secondary" @click="handleScanNow">
          Scan for Changes
        </BaseButton>
      </template>
    </EmptyState>

    <!-- Actions -->
    <div class="feed-actions" v-if="recentChanges.length > 0">
      <BaseButton variant="outline" size="sm" @click="handleClearChanges">
        <i class="fas fa-trash"></i>
        Clear History
      </BaseButton>
      <BaseButton variant="outline" size="sm" @click="handleExportChanges">
        <i class="fas fa-download"></i>
        Export Changes
      </BaseButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import { useDocumentChanges } from '@/composables/useDocumentChanges'

const logger = createLogger('DocumentChangeFeed')
import type { DocumentChange } from '@/composables/useDocumentChanges'
import { formatBytes } from '@/utils/formatHelpers'
import EmptyState from '@/components/ui/EmptyState.vue'
import BaseButton from '@/components/base/BaseButton.vue'

// Composable
const {
  recentChanges,
  changeSummary,
  isScanning,
  lastScanTime,
  machineId,
  totalChanges,
  hasChanges,
  lastVectorizationResult,
  scanForChanges,
  getChangeIcon,
  getChangeTypeName,
  formatRelativeTime,
  clearChanges,
  startAutoRefresh,
  stopAutoRefresh,
  setMachineId,
  exportChanges
} = useDocumentChanges()

// Local state
const autoRefreshEnabled = ref(false)
const autoVectorizeEnabled = ref(false)
const activeFilter = ref<'all' | 'added' | 'updated' | 'removed'>('all')
// Issue #425: Section filter for man pages
const selectedSections = ref<string[]>(['1', '8'])  // Default: User Commands and System Admin

// Computed
const filteredChanges = computed(() => {
  let changes = recentChanges.value

  // Issue #425: Filter by change type
  if (activeFilter.value !== 'all') {
    changes = changes.filter(change => change.change_type === activeFilter.value)
  }

  // Issue #425: Filter by man page section if sections are selected
  if (selectedSections.value.length > 0 && selectedSections.value.length < 8) {
    changes = changes.filter(change => {
      // Check if this is a man page change with section metadata
      const section = (change as DocumentChangeWithSection).section
      if (!section) return true  // Non-man-page changes pass through
      return selectedSections.value.includes(section)
    })
  }

  return changes
})

// Issue #425: Extended type for man page changes
interface DocumentChangeWithSection extends DocumentChange {
  section?: string
}

// Methods
const handleScanNow = async () => {
  const result = await scanForChanges(false, autoVectorizeEnabled.value)
  if (result) {
    logger.info('Scan completed:', result)
    if (result.vectorization) {
      logger.info('Vectorization results:', result.vectorization)
    }
  }
}

const handleAutoRefreshToggle = () => {
  if (autoRefreshEnabled.value) {
    startAutoRefresh(30) // 30 minutes
  } else {
    stopAutoRefresh()
  }
}

const handleClearChanges = () => {
  if (confirm('Clear all change history? This cannot be undone.')) {
    clearChanges()
    activeFilter.value = 'all'
  }
}

const handleExportChanges = () => {
  const json = exportChanges()
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `document-changes-${machineId.value}-${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
}

// Lifecycle
onMounted(() => {
  // Set machine ID from environment or use default
  const hostId = import.meta.env.VITE_MACHINE_ID || 'default-host'
  setMachineId(hostId)

  // Initial scan
  scanForChanges(false)
})

onUnmounted(() => {
  stopAutoRefresh()
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.document-change-feed {
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.feed-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--border-default);
}

.feed-title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.change-badges {
  display: flex;
  gap: 0.5rem;
}

.badge {
  padding: 0.25rem 0.75rem;
  border-radius: 9999px;
  font-size: 0.875rem;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
}

.badge-success {
  background: var(--color-success-bg);
  color: var(--color-success-dark);
}

.badge-info {
  background: var(--color-info-bg);
  color: var(--color-info-dark);
}

.badge-danger {
  background: var(--color-error-bg);
  color: var(--color-error-dark);
}

.badge-secondary {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

.feed-controls {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}

/* Issue #425: Section filter styles */
.section-filter {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.filter-label {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.875rem;
  color: var(--text-secondary);
  white-space: nowrap;
}

.section-select {
  padding: 0.375rem 0.5rem;
  font-size: 0.875rem;
  border: 1px solid var(--border-light);
  border-radius: 4px;
  background: var(--bg-card);
  color: var(--text-secondary);
  min-width: 180px;
  max-height: 100px;
}

.section-select:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px var(--color-primary-alpha, rgba(59, 130, 246, 0.2));
}

.auto-refresh-toggle {
  display: flex;
  align-items: center;
}

.auto-vectorize-toggle {
  display: flex;
  align-items: center;
}

.toggle-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  user-select: none;
}

.toggle-label input[type="checkbox"] {
  cursor: pointer;
}

.last-scan {
  margin-left: auto;
  color: var(--text-tertiary);
  font-size: 0.875rem;
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.vectorization-status {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  padding: 0.75rem 1rem;
  margin-bottom: 1rem;
}

.status-header {
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 0.5rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.status-stats {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.875rem;
  font-weight: 500;
}

.stat-success {
  color: var(--color-success);
}

.stat-failed {
  color: var(--color-error);
}

.stat-skipped {
  color: var(--color-warning);
}

.change-filters {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}

.change-list {
  margin-bottom: 1rem;
}

.change-items {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.change-item {
  display: flex;
  gap: 0.75rem;
  padding: 0.75rem;
  border-radius: 6px;
  transition: all 0.2s;
}

.change-item:hover {
  background: var(--bg-tertiary);
}

.change-added {
  border-left: 3px solid var(--color-success);
}

.change-updated {
  border-left: 3px solid var(--color-primary);
}

.change-removed {
  border-left: 3px solid var(--color-error);
}

.change-icon {
  flex-shrink: 0;
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.25rem;
}

.change-content {
  flex: 1;
  min-width: 0;
}

.change-title {
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 0.25rem;
  word-break: break-word;
}

.change-command {
  color: var(--text-tertiary);
  font-weight: 400;
  font-size: 0.875rem;
}

.change-meta {
  display: flex;
  gap: 0.75rem;
  font-size: 0.8125rem;
  color: var(--text-tertiary);
  flex-wrap: wrap;
}

.change-type-label {
  font-weight: 500;
}


.feed-actions {
  display: flex;
  gap: 0.75rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-default);
}

/* Dark mode support handled automatically by CSS custom properties */
</style>
