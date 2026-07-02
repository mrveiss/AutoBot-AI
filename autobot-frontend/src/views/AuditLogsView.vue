<template>
  <div class="audit-logs-view">
      <!-- Page Header -->
      <div class="page-header">
        <div class="page-header-content">
          <h2 class="page-title">{{ $t('views.auditLogs.title') }}</h2>
          <p class="page-subtitle">{{ $t('views.auditLogs.subtitle') }}</p>
        </div>
        <div class="header-actions">
          <button
            :class="['btn-action-secondary', { 'btn-polling-active': isPolling }]"
            @click="togglePolling"
          >
            <Icon :name="isPolling ? 'pause' : 'play'" />
            {{ isPolling ? $t('views.auditLogs.pauseUpdates') : $t('views.auditLogs.autoRefresh') }}
          </button>
          <button class="btn-action-danger" @click="showCleanupModal = true">
            <Icon name="trash" />
            {{ $t('views.auditLogs.cleanup') }}
          </button>
        </div>
      </div>

      <!-- Tab Navigation -->
      <div class="tab-nav">
        <button
          :class="['tab-btn', { active: activeTab === 'dashboard' }]"
          @click="activeTab = 'dashboard'"
        >
          <Icon name="chart-pie" />
          {{ $t('views.auditLogs.dashboard') }}
        </button>
        <button
          :class="['tab-btn', { active: activeTab === 'logs' }]"
          @click="activeTab = 'logs'"
        >
          <Icon name="list-alt" />
          {{ $t('views.auditLogs.auditLogs') }}
        </button>
        <button
          :class="['tab-btn', { active: activeTab === 'failures' }]"
          @click="loadFailuresTab"
        >
          <Icon name="exclamation-triangle" />
          {{ $t('views.auditLogs.failedOperations') }}
        </button>
      </div>

      <!-- Error Banner -->
      <div v-if="initError" class="error-banner">
        <Icon name="exclamation-circle" />
        <span>{{ initError }}</span>
        <button class="btn-dismiss" @click="initError = null">
          <Icon name="times" />
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
            <label for="failure-hours">{{ $t('views.auditLogs.timeRange') }}</label>
            <select
              id="failure-hours"
              v-model="failureHours"
              @change="loadFailedOperations(failureHours)"
            >
              <option :value="1">{{ $t('views.auditLogs.lastHour') }}</option>
              <option :value="6">{{ $t('views.auditLogs.last6Hours') }}</option>
              <option :value="24">{{ $t('views.auditLogs.last24Hours') }}</option>
              <option :value="48">{{ $t('views.auditLogs.last48Hours') }}</option>
              <option :value="168">{{ $t('views.auditLogs.last7Days') }}</option>
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
      <BaseModal
        v-model="showCleanupModal"
        :title="$t('views.auditLogs.cleanupTitle')"
        size="sm"
      >
        <template #title>
          <span class="cleanup-title">
            <Icon name="trash" />
            {{ $t('views.auditLogs.cleanupTitle') }}
          </span>
        </template>
            <div class="warning-banner">
              <Icon name="exclamation-triangle" />
              <span>{{ $t('views.auditLogs.cleanupWarning') }}</span>
            </div>
            <div class="cleanup-form">
              <label for="days-to-keep">{{ $t('views.auditLogs.keepLogsLabel') }}</label>
              <select id="days-to-keep" v-model="cleanupDays">
                <option :value="7">{{ $t('views.auditLogs.days7') }}</option>
                <option :value="30">{{ $t('views.auditLogs.days30') }}</option>
                <option :value="60">{{ $t('views.auditLogs.days60') }}</option>
                <option :value="90">{{ $t('views.auditLogs.days90Default') }}</option>
                <option :value="180">{{ $t('views.auditLogs.days180') }}</option>
                <option :value="365">{{ $t('views.auditLogs.days365') }}</option>
              </select>
            </div>
            <div class="cleanup-confirm">
              <label>
                <input type="checkbox" v-model="cleanupConfirmed" />
                {{ $t('views.auditLogs.cleanupConfirm') }}
              </label>
            </div>
        <template #actions>
          <button class="btn-action-secondary" @click="showCleanupModal = false">
            {{ $t('views.auditLogs.cancel') }}
          </button>
          <button
            class="btn-action-danger"
            :disabled="!cleanupConfirmed"
            @click="performCleanup"
          >
            <Icon name="trash" />
            {{ $t('views.auditLogs.deleteOldLogs') }}
          </button>
        </template>
      </BaseModal>
  </div>
</template>

<script setup lang="ts">
// Issue #1359: i18n string extraction
import { ref, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuditState } from '@/composables/useAuditApi'
import AuditStatistics from '@/components/audit/AuditStatistics.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import AuditFilters from '@/components/audit/AuditFilters.vue'
import AuditLogTable from '@/components/audit/AuditLogTable.vue'
import AuditTimeline from '@/components/audit/AuditTimeline.vue'
import Icon from '@/components/ui/Icon.vue'
import type { AuditFilter, AuditEntry } from '@/types/audit'
import { createLogger } from '@/utils/debugUtils'

const { t } = useI18n()
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
    initError.value = t('views.auditLogs.initError')
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
@reference "../assets/tailwind.css";
.audit-logs-view {
  contain: layout style paint;
  display: flex;
  flex-direction: column;
  min-height: 100%;
  padding: var(--spacing-5);
  background: var(--bg-primary);
  overflow-y: auto;
}

/* Header actions */
.header-actions {
  display: flex;
  gap: var(--spacing-2);
}

/* Polling active state override */
.btn-polling-active {
  background: var(--color-primary);
  color: var(--text-on-primary);
  border-color: var(--color-primary);
}

/* Danger button */
.btn-action-danger {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-on-error);
  background: var(--color-error);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background var(--duration-150) var(--ease-in-out);
}

.btn-action-danger:hover:not(:disabled) {
  background: var(--color-error-hover);
}

.btn-action-danger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Error banner */
.error-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  border-radius: var(--radius-md);
  color: var(--color-error);
  margin-bottom: var(--spacing-4);
}

.error-banner span {
  flex: 1;
  font-size: var(--text-sm);
}

.btn-dismiss {
  padding: var(--spacing-1) var(--spacing-2);
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-md);
}

.btn-dismiss:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

/* Tab content */
.tab-content {
  animation: fadeIn var(--duration-200) var(--ease-in-out);
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Failures filter */
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
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  background: var(--bg-input);
  color: var(--text-primary);
}

/* Timeline Drawer */
.timeline-drawer {
  position: fixed;
  inset: 0;
  z-index: var(--z-dropdown);
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
  background: var(--bg-primary);
  box-shadow: var(--shadow-xl);
  animation: slideIn var(--duration-300) var(--ease-in-out);
}

@keyframes slideIn {
  from { transform: translateX(100%); }
  to { transform: translateX(0); }
}

/* Cleanup Modal */
.cleanup-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  color: var(--color-error);
}

.warning-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3);
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning-border);
  border-radius: var(--radius-md);
  color: var(--color-warning);
  font-size: var(--text-sm);
  margin-bottom: var(--spacing-4);
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
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  background: var(--bg-input);
  color: var(--text-primary);
}

.cleanup-confirm {
  padding: var(--spacing-3);
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
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

@media (max-width: 768px) {
  .header-actions {
    width: 100%;
    justify-content: flex-end;
  }

  .drawer-content {
    width: 100%;
  }

  .modal-content {
    margin: var(--spacing-2);
  }
}
</style>
