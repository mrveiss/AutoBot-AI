<template>
  <div class="audit-logs-view view-container">
    <div class="w-full px-4 pt-4 pb-6">
      <!-- Page Header -->
      <div class="page-header">
        <div class="header-content">
          <h1>
            <i class="fas fa-shield-halved"></i>
            Audit Logs
          </h1>
          <p class="header-description">
            Security audit trail and activity monitoring
          </p>
        </div>
        <div class="header-actions">
          <button
            :class="['btn', isPolling ? 'btn-active' : 'btn-secondary']"
            @click="togglePolling"
          >
            <i :class="isPolling ? 'fas fa-pause' : 'fas fa-play'"></i>
            {{ isPolling ? 'Pause Updates' : 'Auto-refresh' }}
          </button>
          <button class="btn btn-danger" @click="showCleanupModal = true">
            <i class="fas fa-trash-alt"></i>
            Cleanup
          </button>
        </div>
      </div>

      <!-- Tab Navigation -->
      <div class="tab-nav">
        <button
          :class="['tab-btn', { active: activeTab === 'dashboard' }]"
          @click="activeTab = 'dashboard'"
        >
          <i class="fas fa-chart-pie"></i>
          Dashboard
        </button>
        <button
          :class="['tab-btn', { active: activeTab === 'logs' }]"
          @click="activeTab = 'logs'"
        >
          <i class="fas fa-list-alt"></i>
          Audit Logs
        </button>
        <button
          :class="['tab-btn', { active: activeTab === 'failures' }]"
          @click="loadFailuresTab"
        >
          <i class="fas fa-exclamation-triangle"></i>
          Failed Operations
        </button>
      </div>

      <!-- Error Banner -->
      <div v-if="initError" class="error-banner">
        <i class="fas fa-exclamation-circle"></i>
        <span>{{ initError }}</span>
        <button class="btn btn-secondary btn-small" @click="initError = null">
          <i class="fas fa-times"></i>
        </button>
      </div>

      <!-- Dashboard Tab -->
      <div v-if="activeTab === 'dashboard'" class="tab-content">
        <AuditStatistics
          :statistics="statistics"
          :vm-info="vmInfo"
          :loading="loadingStats"
          @user-click="openUserTrail"
        />
      </div>

      <!-- Logs Tab -->
      <div v-if="activeTab === 'logs'" class="tab-content">
        <AuditFilters
          :filter="filter"
          :operation-categories="operationCategories"
          @update:filter="updateFilter"
          @apply="loadLogs"
          @reset="resetFilter"
        />

        <AuditLogTable
          :entries="entries"
          :loading="loading"
          :has-more="hasMore"
          :current-page="currentPage"
          @refresh="loadLogs"
          @export="downloadExport"
          @entry-select="selectEntry"
          @user-click="openUserTrail"
          @session-click="openSessionTrail"
          @next-page="nextPage"
          @prev-page="prevPage"
        />
      </div>

      <!-- Failures Tab -->
      <div v-if="activeTab === 'failures'" class="tab-content">
        <div class="failures-header">
          <div class="failure-filter">
            <label for="failure-hours">Time Range:</label>
            <select
              id="failure-hours"
              v-model="failureHours"
              @change="loadFailedOperations(failureHours)"
            >
              <option :value="1">Last Hour</option>
              <option :value="6">Last 6 Hours</option>
              <option :value="24">Last 24 Hours</option>
              <option :value="48">Last 48 Hours</option>
              <option :value="168">Last 7 Days</option>
            </select>
          </div>
        </div>

        <AuditLogTable
          :entries="entries"
          :loading="loading"
          :has-more="false"
          :current-page="1"
          @refresh="loadFailedOperations(failureHours)"
          @export="downloadExport"
          @entry-select="selectEntry"
          @user-click="openUserTrail"
          @session-click="openSessionTrail"
        />
      </div>

      <!-- Session/User Timeline Drawer -->
      <div v-if="showTimeline" class="timeline-drawer">
        <div class="drawer-backdrop" @click="closeTimeline"></div>
        <div class="drawer-content">
          <AuditTimeline
            :type="timelineType"
            :entity-id="timelineEntityId"
            :entries="timelineType === 'session' ? sessionTrail : userTrail"
            :loading="loadingTrail"
            @close="closeTimeline"
            @refresh="refreshTimeline"
          />
        </div>
      </div>

      <!-- Cleanup Modal -->
      <div v-if="showCleanupModal" class="modal-overlay" @click="showCleanupModal = false">
        <div class="modal-content" @click.stop>
          <div class="modal-header">
            <h3>
              <i class="fas fa-trash-alt"></i>
              Cleanup Audit Logs
            </h3>
            <button class="btn btn-icon" @click="showCleanupModal = false">
              <i class="fas fa-times"></i>
            </button>
          </div>
          <div class="modal-body">
            <div class="warning-banner">
              <i class="fas fa-exclamation-triangle"></i>
              <span>This action is irreversible. Deleted logs cannot be recovered.</span>
            </div>
            <div class="cleanup-form">
              <label for="days-to-keep">Keep logs from the last:</label>
              <select id="days-to-keep" v-model="cleanupDays">
                <option :value="7">7 days</option>
                <option :value="30">30 days</option>
                <option :value="60">60 days</option>
                <option :value="90">90 days (default)</option>
                <option :value="180">180 days</option>
                <option :value="365">1 year</option>
              </select>
            </div>
            <div class="cleanup-confirm">
              <label>
                <input type="checkbox" v-model="cleanupConfirmed" />
                I understand this will permanently delete old audit logs
              </label>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showCleanupModal = false">
              Cancel
            </button>
            <button
              class="btn btn-danger"
              :disabled="!cleanupConfirmed"
              @click="performCleanup"
            >
              <i class="fas fa-trash-alt"></i>
              Delete Old Logs
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useAuditState } from '@/composables/useAuditApi'
import AuditStatistics from '@/components/audit/AuditStatistics.vue'
import AuditFilters from '@/components/audit/AuditFilters.vue'
import AuditLogTable from '@/components/audit/AuditLogTable.vue'
import AuditTimeline from '@/components/audit/AuditTimeline.vue'
import type { AuditFilter, AuditEntry } from '@/types/audit'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('AuditLogsView')

// Use the audit state composable
const {
  entries,
  statistics,
  vmInfo,
  operationCategories,
  loading,
  loadingStats,
  hasMore,
  filter,
  currentPage,
  isPolling,
  sessionTrail,
  userTrail,
  loadingTrail,
  loadLogs,
  loadStatistics,
  loadOperationCategories,
  loadSessionTrail,
  loadUserTrail,
  loadFailedOperations,
  cleanupLogs,
  setFilter,
  resetFilter,
  nextPage,
  prevPage,
  startPolling,
  stopPolling,
  downloadExport
} = useAuditState()

// Local UI state
const activeTab = ref<'dashboard' | 'logs' | 'failures'>('dashboard')
const showTimeline = ref(false)
const timelineType = ref<'session' | 'user'>('session')
const timelineEntityId = ref('')
const failureHours = ref(24)
const showCleanupModal = ref(false)
const cleanupDays = ref(90)
const cleanupConfirmed = ref(false)
const initError = ref<string | null>(null)

// Initialize on mount
onMounted(async () => {
  logger.debug('AuditLogsView mounted, initializing...')
  initError.value = null
  try {
    await Promise.all([loadLogs(), loadStatistics(), loadOperationCategories()])
    logger.debug('Audit data loaded successfully')
  } catch (error) {
    initError.value = 'Failed to load audit data. Please refresh the page or check your connection.'
    logger.error('Failed to initialize audit view:', error)
  }
})

// Cleanup on unmount
onUnmounted(() => {
  stopPolling()
})

// Toggle auto-refresh polling
function togglePolling() {
  if (isPolling.value) {
    stopPolling()
  } else {
    startPolling(30000) // 30 second intervals
  }
}

// Update filter from child component
function updateFilter(newFilter: Partial<AuditFilter>) {
  setFilter(newFilter)
}

// Select entry for detail view
function selectEntry(entry: AuditEntry) {
  logger.debug('Entry selected:', entry.id)
}

// Open session trail in drawer
function openSessionTrail(sessionId: string) {
  timelineType.value = 'session'
  timelineEntityId.value = sessionId
  showTimeline.value = true
  loadSessionTrail(sessionId)
}

// Open user trail in drawer
function openUserTrail(userId: string) {
  timelineType.value = 'user'
  timelineEntityId.value = userId
  showTimeline.value = true
  loadUserTrail(userId)
}

// Close timeline drawer
function closeTimeline() {
  showTimeline.value = false
}

// Refresh timeline data
function refreshTimeline() {
  if (timelineType.value === 'session') {
    loadSessionTrail(timelineEntityId.value)
  } else {
    loadUserTrail(timelineEntityId.value)
  }
}

// Load failures tab
function loadFailuresTab() {
  activeTab.value = 'failures'
  loadFailedOperations(failureHours.value)
}

// Perform cleanup
async function performCleanup() {
  if (!cleanupConfirmed.value) return

  try {
    const result = await cleanupLogs(cleanupDays.value, true)
    if (result?.success) {
      showCleanupModal.value = false
      cleanupConfirmed.value = false
      logger.debug('Cleanup completed successfully')
    }
  } catch (error) {
    logger.error('Cleanup failed:', error)
  }
}
</script>

<style scoped>
.audit-logs-view {
  min-height: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-6);
}

.header-content h1 {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  margin: 0 0 var(--spacing-1) 0;
  font-size: var(--font-size-2xl);
  font-weight: 700;
  color: var(--text-primary);
}

.header-content h1 i {
  color: var(--color-primary);
}

.header-description {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.header-actions {
  display: flex;
  gap: var(--spacing-2);
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-default);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-in-out);
  border: none;
}

.btn-secondary {
  background: var(--bg-secondary);
  color: var(--text-primary);
  border: 1px solid var(--border-default);
}

.btn-secondary:hover {
  background: var(--bg-hover);
}

.btn-active {
  background: var(--color-primary);
  color: white;
}

.btn-danger {
  background: var(--color-error);
  color: white;
}

.btn-danger:hover:not(:disabled) {
  background: var(--color-error-dark);
}

.btn-danger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-icon {
  padding: var(--spacing-2);
  background: transparent;
  border: none;
  color: var(--text-secondary);
}

.btn-icon:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.error-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3) var(--spacing-4);
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: var(--radius-default);
  color: rgb(185, 28, 28);
  margin-bottom: var(--spacing-4);
}

.error-banner i:first-child {
  font-size: var(--text-lg);
}

.error-banner span {
  flex: 1;
  font-size: var(--text-sm);
}

.btn-small {
  padding: var(--spacing-1) var(--spacing-2);
}

.tab-nav {
  display: flex;
  gap: var(--spacing-1);
  margin-bottom: var(--spacing-4);
  border-bottom: 1px solid var(--border-default);
  padding-bottom: var(--spacing-1);
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  background: transparent;
  border: none;
  border-radius: var(--radius-default) var(--radius-default) 0 0;
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-in-out);
}

.tab-btn:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.tab-btn.active {
  color: var(--color-primary);
  background: var(--bg-card);
  border-bottom: 2px solid var(--color-primary);
}

.tab-content {
  animation: fadeIn var(--duration-200) var(--ease-in-out);
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.failures-header {
  display: flex;
  justify-content: flex-end;
  margin-bottom: var(--spacing-4);
}

.failure-filter {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.failure-filter label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.failure-filter select {
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-default);
  font-size: var(--text-sm);
  background: var(--bg-input);
  color: var(--text-primary);
}

/* Timeline Drawer */
.timeline-drawer {
  position: fixed;
  inset: 0;
  z-index: 50;
}

.drawer-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
}

.drawer-content {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 480px;
  max-width: 100%;
  background: var(--bg-base);
  box-shadow: var(--shadow-xl);
  animation: slideIn var(--duration-300) var(--ease-in-out);
}

@keyframes slideIn {
  from {
    transform: translateX(100%);
  }
  to {
    transform: translateX(0);
  }
}

/* Cleanup Modal */
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
  border-radius: var(--radius-lg);
  max-width: 500px;
  width: 100%;
  overflow: hidden;
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
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.modal-header h3 i {
  color: var(--color-error);
}

.modal-body {
  padding: var(--spacing-4);
}

.warning-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3);
  background: rgba(234, 179, 8, 0.1);
  border: 1px solid rgba(234, 179, 8, 0.3);
  border-radius: var(--radius-default);
  color: rgb(161, 98, 7);
  font-size: var(--text-sm);
  margin-bottom: var(--spacing-4);
}

.warning-banner i {
  font-size: var(--text-lg);
}

.cleanup-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
  margin-bottom: var(--spacing-4);
}

.cleanup-form label {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.cleanup-form select {
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-default);
  font-size: var(--text-sm);
  background: var(--bg-input);
  color: var(--text-primary);
}

.cleanup-confirm {
  padding: var(--spacing-3);
  background: var(--bg-secondary);
  border-radius: var(--radius-default);
}

.cleanup-confirm label {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: var(--text-sm);
  color: var(--text-primary);
  cursor: pointer;
}

.cleanup-confirm input[type="checkbox"] {
  width: 18px;
  height: 18px;
  accent-color: var(--color-primary);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-2);
  padding: var(--spacing-4);
  border-top: 1px solid var(--border-default);
  background: var(--bg-secondary);
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    gap: var(--spacing-4);
  }

  .header-actions {
    width: 100%;
    justify-content: flex-end;
  }

  .tab-nav {
    overflow-x: auto;
  }

  .drawer-content {
    width: 100%;
  }

  .modal-content {
    margin: var(--spacing-2);
  }
}
</style>
