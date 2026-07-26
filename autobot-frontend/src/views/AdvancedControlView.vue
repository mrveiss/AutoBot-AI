<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  AdvancedControlView — admin-only Advanced Control panel (#12162, #12102,
  #11506 T1 — Stage 1; #12169, #12102 — Stage 2 streaming sessions;
  #12173, #12102 — Stage 3 system monitoring + emergency-stop). Tabbed
  shell wired to AdvancedControlApiClient's takeover-management, desktop
  streaming, and system-monitoring endpoints.
-->
<template>
  <div class="advanced-control-view view-container">
    <div class="page-header">
      <div class="page-header-content">
        <h2 class="page-title">{{ t('advancedControl.title') }}</h2>
        <p class="page-subtitle">{{ t('advancedControl.subtitle') }}</p>
      </div>
      <div class="header-actions">
        <button class="btn-action-secondary" :disabled="loading" @click="loadTakeovers">
          <Icon name="sync-alt" :spin="loading" />
          {{ t('common.refresh') }}
        </button>
      </div>
    </div>

    <!-- Tab bar -->
    <div
      ref="tablistRef"
      class="acv-tabs"
      role="tablist"
      :aria-label="t('advancedControl.tabListAriaLabel')"
    >
      <button
        v-for="tab in tabs"
        :key="tab.id"
        v-bind="tabAttrs(tab.id)"
        class="acv-tab"
        :class="{ 'acv-tab--active': activeTab === tab.id }"
        :disabled="tab.disabled"
        @click="!tab.disabled && selectTab(tab.id)"
        @keydown="handleKeydown"
      >
        <Icon :name="tab.icon" />
        {{ tab.label }}
        <span v-if="tab.disabled" class="acv-tab__soon">{{ t('advancedControl.tabs.comingSoon') }}</span>
      </button>
    </div>

    <!-- Takeover Queue tab -->
    <div v-if="activeTab === 'takeover'" v-bind="panelAttrs('takeover')" class="acv-content">
      <div v-if="error" class="error-banner">
        <Icon name="exclamation-circle" />
        <span>{{ error }}</span>
        <button class="btn-dismiss" :aria-label="t('common.dismiss')" @click="clearError"><Icon name="times" /></button>
      </div>

      <!-- Status summary -->
      <div v-if="takeoverStatus" class="status-summary">
        <div class="status-card">
          <span class="status-value">{{ takeoverStatus.pending_requests_count }}</span>
          <span class="status-label">{{ t('advancedControl.summary.pending') }}</span>
        </div>
        <div class="status-card">
          <span class="status-value">{{ takeoverStatus.active_sessions_count }}</span>
          <span class="status-label">{{ t('advancedControl.summary.active') }}</span>
        </div>
        <div class="status-card">
          <span class="status-value">{{ takeoverStatus.paused_tasks_count }}</span>
          <span class="status-label">{{ t('advancedControl.summary.paused') }}</span>
        </div>
        <div class="status-card">
          <span class="status-value">{{ takeoverStatus.total_completed_sessions }}</span>
          <span class="status-label">{{ t('advancedControl.summary.completed') }}</span>
        </div>
        <div class="status-card status-card--system" :class="`status-card--${takeoverStatus.system_status}`">
          <span class="status-label">{{ t('advancedControl.summary.systemStatus') }}</span>
          <span class="badge" :class="systemStatusBadgeClass">{{ systemStatusLabel }}</span>
        </div>
      </div>

      <div v-if="loading && pendingTakeovers.length === 0 && activeTakeovers.length === 0" class="loading-state">
        <Icon name="sync-alt" :spin="true" /> {{ t('advancedControl.loading') }}
      </div>

      <template v-else>
        <!-- Pending requests -->
        <section class="table-section">
          <h3 class="section-title">{{ t('advancedControl.pending.title') }}</h3>
          <table v-if="pendingTakeovers.length > 0" class="data-table">
            <thead>
              <tr>
                <th>{{ t('advancedControl.pending.colTrigger') }}</th>
                <th>{{ t('advancedControl.pending.colReason') }}</th>
                <th>{{ t('advancedControl.pending.colPriority') }}</th>
                <th>{{ t('advancedControl.pending.colRequestedBy') }}</th>
                <th>{{ t('advancedControl.pending.colCreatedAt') }}</th>
                <th>{{ t('advancedControl.pending.colActions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="req in pendingTakeovers" :key="req.request_id">
                <td>{{ req.trigger }}</td>
                <td class="reason-cell">{{ req.reason }}</td>
                <td><span class="badge" :class="priorityBadgeClass(req.priority)">{{ req.priority }}</span></td>
                <td>{{ req.requesting_agent || t('advancedControl.pending.unknownAgent') }}</td>
                <td>{{ formatDate(req.created_at) }}</td>
                <td class="actions-cell">
                  <button
                    class="btn-icon btn-success"
                    :title="t('advancedControl.actions.approve')"
                    :disabled="loading"
                    @click="onApprove(req.request_id)"
                  >
                    <Icon name="check-circle" />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <EmptyState
            v-else
            icon="check-circle"
            :title="t('advancedControl.pending.emptyTitle')"
            :message="t('advancedControl.pending.emptyMessage')"
            compact
          />
        </section>

        <!-- Active sessions -->
        <section class="table-section">
          <h3 class="section-title">{{ t('advancedControl.active.title') }}</h3>
          <table v-if="activeTakeovers.length > 0" class="data-table">
            <thead>
              <tr>
                <th>{{ t('advancedControl.active.colOperator') }}</th>
                <th>{{ t('advancedControl.active.colStatus') }}</th>
                <th>{{ t('advancedControl.active.colStartedAt') }}</th>
                <th>{{ t('advancedControl.active.colActionsExecuted') }}</th>
                <th>{{ t('advancedControl.pending.colActions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="session in activeTakeovers" :key="session.session_id">
                <td>{{ session.human_operator }}</td>
                <td><span class="badge" :class="statusBadgeClass(session.status)">{{ session.status }}</span></td>
                <td>{{ formatDate(session.started_at) }}</td>
                <td>{{ session.actions_executed }}</td>
                <td class="actions-cell">
                  <button
                    v-if="session.status === 'active'"
                    class="btn-icon btn-warning"
                    :title="t('advancedControl.actions.pause')"
                    :disabled="loading"
                    @click="onPause(session.session_id)"
                  >
                    <Icon name="pause-circle" />
                  </button>
                  <button
                    v-if="session.status === 'paused'"
                    class="btn-icon btn-info"
                    :title="t('advancedControl.actions.resume')"
                    :disabled="loading"
                    @click="onResume(session.session_id)"
                  >
                    <Icon name="play-circle" />
                  </button>
                  <button
                    class="btn-icon btn-danger"
                    :title="t('advancedControl.actions.complete')"
                    :disabled="loading"
                    @click="onComplete(session.session_id)"
                  >
                    <Icon name="stop-circle" />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <EmptyState
            v-else
            icon="hand-paper"
            :title="t('advancedControl.active.emptyTitle')"
            :message="t('advancedControl.active.emptyMessage')"
            compact
          />
        </section>
      </template>
    </div>

    <!-- Streaming Sessions tab -->
    <div v-else-if="activeTab === 'streaming'" v-bind="panelAttrs('streaming')" class="acv-content">
      <div v-if="error" class="error-banner">
        <Icon name="exclamation-circle" />
        <span>{{ error }}</span>
        <button class="btn-dismiss" :aria-label="t('common.dismiss')" @click="clearError"><Icon name="times" /></button>
      </div>

      <!-- Capabilities summary -->
      <div v-if="streamingCapabilities" class="status-summary">
        <div class="status-card">
          <span class="status-value">{{ streamingCapabilities.vnc_available ? t('common.yes') : t('common.no') }}</span>
          <span class="status-label">{{ t('advancedControl.streaming.capVncAvailable') }}</span>
        </div>
        <div class="status-card">
          <span class="status-value">{{ streamingCapabilities.novnc_available ? t('common.yes') : t('common.no') }}</span>
          <span class="status-label">{{ t('advancedControl.streaming.capNovncAvailable') }}</span>
        </div>
        <div class="status-card">
          <span class="status-value">{{ streamingCapabilities.max_sessions }}</span>
          <span class="status-label">{{ t('advancedControl.streaming.capMaxSessions') }}</span>
        </div>
      </div>

      <div v-if="loading && streamingSessions.length === 0" class="loading-state">
        <Icon name="sync-alt" :spin="true" /> {{ t('advancedControl.loading') }}
      </div>

      <template v-else>
        <section class="table-section">
          <h3 class="section-title section-title--with-action">
            <span>{{ t('advancedControl.streaming.title') }}</span>
            <button class="btn-action-secondary" @click="toggleCreateForm">
              <Icon name="plus-circle" />
              {{ t('advancedControl.streaming.newSession') }}
            </button>
          </h3>

          <form v-if="showCreateForm" class="streaming-create-form" @submit.prevent="onCreateStreaming">
            <div class="form-field">
              <label for="streaming-user-id">{{ t('advancedControl.streaming.formUserIdLabel') }}</label>
              <input
                id="streaming-user-id"
                v-model="createForm.userId"
                type="text"
                required
                :placeholder="t('advancedControl.streaming.formUserIdPlaceholder')"
              />
            </div>
            <div class="form-field">
              <label for="streaming-resolution">{{ t('advancedControl.streaming.formResolutionLabel') }}</label>
              <input
                id="streaming-resolution"
                v-model="createForm.resolution"
                type="text"
                :placeholder="t('advancedControl.streaming.formResolutionPlaceholder')"
              />
            </div>
            <div class="form-field">
              <label for="streaming-depth">{{ t('advancedControl.streaming.formDepthLabel') }}</label>
              <input id="streaming-depth" v-model.number="createForm.depth" type="number" min="1" />
            </div>
            <div class="form-actions">
              <button type="button" class="btn-action-secondary" @click="toggleCreateForm">
                {{ t('common.cancel') }}
              </button>
              <button type="submit" class="btn-action-primary" :disabled="loading">
                {{ t('common.create') }}
              </button>
            </div>
          </form>

          <table v-if="streamingSessions.length > 0" class="data-table">
            <thead>
              <tr>
                <th>{{ t('advancedControl.streaming.colSessionId') }}</th>
                <th>{{ t('advancedControl.streaming.colUser') }}</th>
                <th>{{ t('advancedControl.streaming.colStatus') }}</th>
                <th>{{ t('advancedControl.streaming.colDisplay') }}</th>
                <th>{{ t('advancedControl.streaming.colCreatedAt') }}</th>
                <th>{{ t('advancedControl.streaming.colActions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="session in streamingSessions" :key="session.session_id">
                <td>{{ session.session_id }}</td>
                <td>{{ session.user_id }}</td>
                <td><span class="badge" :class="streamingStatusBadgeClass(session.status)">{{ session.status }}</span></td>
                <td>{{ session.display }}</td>
                <td>{{ formatDate(session.created_at) }}</td>
                <td class="actions-cell">
                  <button
                    class="btn-icon btn-danger"
                    :title="t('advancedControl.streaming.terminate')"
                    :disabled="loading"
                    @click="onTerminateStreaming(session.session_id)"
                  >
                    <Icon name="trash-alt" />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <EmptyState
            v-else
            icon="window-restore"
            :title="t('advancedControl.streaming.emptyTitle')"
            :message="t('advancedControl.streaming.emptyMessage')"
            compact
          />
        </section>
      </template>
    </div>

    <!-- Monitoring tab (#12173, #12102 — Stage 3) -->
    <div v-else-if="activeTab === 'monitoring'" v-bind="panelAttrs('monitoring')" class="acv-content">
      <div v-if="error" class="error-banner">
        <Icon name="exclamation-circle" />
        <span>{{ error }}</span>
        <button class="btn-dismiss" :aria-label="t('common.dismiss')" @click="clearError"><Icon name="times" /></button>
      </div>

      <div v-if="loading && !systemHealth && !systemStatus" class="loading-state">
        <Icon name="sync-alt" :spin="true" /> {{ t('advancedControl.monitoring.loading') }}
      </div>

      <template v-else-if="systemHealth || systemStatus">
        <!-- Health summary -->
        <section v-if="systemHealth" class="table-section">
          <h3 class="section-title">{{ t('advancedControl.monitoring.healthTitle') }}</h3>
          <div class="status-summary status-summary--padded">
            <div class="status-card status-card--system" :class="`status-card--${healthStatusClass}`">
              <span class="status-label">{{ t('advancedControl.monitoring.healthStatus') }}</span>
              <span class="badge" :class="healthStatusBadgeClass">{{ healthStatusLabel }}</span>
            </div>
            <div class="status-card">
              <span class="status-value">{{ systemHealth.desktop_streaming_available ? t('common.yes') : t('common.no') }}</span>
              <span class="status-label">{{ t('advancedControl.monitoring.desktopStreamingAvailable') }}</span>
            </div>
            <div class="status-card">
              <span class="status-value">{{ systemHealth.novnc_available ? t('common.yes') : t('common.no') }}</span>
              <span class="status-label">{{ t('advancedControl.monitoring.novncAvailable') }}</span>
            </div>
            <div class="status-card">
              <span class="status-value">{{ systemHealth.active_streaming_sessions }}</span>
              <span class="status-label">{{ t('advancedControl.monitoring.activeStreamingSessions') }}</span>
            </div>
            <div class="status-card">
              <span class="status-value">{{ systemHealth.pending_takeovers }}</span>
              <span class="status-label">{{ t('advancedControl.monitoring.pendingTakeovers') }}</span>
            </div>
            <div class="status-card">
              <span class="status-value">{{ systemHealth.active_takeovers }}</span>
              <span class="status-label">{{ t('advancedControl.monitoring.activeTakeovers') }}</span>
            </div>
            <div class="status-card">
              <span class="status-value">{{ systemHealth.paused_tasks }}</span>
              <span class="status-label">{{ t('advancedControl.monitoring.pausedTasks') }}</span>
            </div>
          </div>
        </section>

        <!-- Resource usage -->
        <section v-if="systemStatus" class="table-section">
          <h3 class="section-title">{{ t('advancedControl.monitoring.resourceTitle') }}</h3>
          <div class="status-summary status-summary--padded">
            <div class="status-card">
              <span class="status-value">{{ formatPercent(systemStatus.resource_usage.cpu_percent) }}</span>
              <span class="status-label">{{ t('advancedControl.monitoring.cpuUsage') }}</span>
            </div>
            <div class="status-card">
              <span class="status-value">{{ formatPercent(systemStatus.resource_usage.memory_percent) }}</span>
              <span class="status-label">{{ t('advancedControl.monitoring.memoryUsage') }}</span>
            </div>
            <div class="status-card">
              <span class="status-value">{{ formatPercent(systemStatus.resource_usage.disk_usage) }}</span>
              <span class="status-label">{{ t('advancedControl.monitoring.diskUsage') }}</span>
            </div>
            <div class="status-card">
              <span class="status-value">{{ systemStatus.resource_usage.process_count }}</span>
              <span class="status-label">{{ t('advancedControl.monitoring.processCount') }}</span>
            </div>
            <div class="status-card">
              <span class="status-value">{{ formatLoadAverage(systemStatus.resource_usage.load_average) }}</span>
              <span class="status-label">{{ t('advancedControl.monitoring.loadAverage') }}</span>
            </div>
            <div class="status-card">
              <span class="status-value">{{ formatUptime(systemStatus.system_status.uptime_seconds) }}</span>
              <span class="status-label">{{ t('advancedControl.monitoring.uptime') }}</span>
            </div>
          </div>
        </section>

        <!-- Emergency stop danger zone -->
        <section class="table-section danger-zone-section">
          <h3 class="section-title danger-heading">
            <Icon name="exclamation-triangle" />
            {{ t('advancedControl.monitoring.emergencyStopTitle') }}
          </h3>
          <div class="danger-card">
            <div class="danger-content">
              <div class="danger-icon">
                <Icon name="power-off" />
              </div>
              <div class="danger-text">
                <h4>{{ t('advancedControl.monitoring.emergencyStop') }}</h4>
                <p>{{ t('advancedControl.monitoring.emergencyStopDescription') }}</p>
              </div>
            </div>
            <button
              class="btn-danger-full"
              :disabled="loading"
              @click="onEmergencyStop"
            >
              <Icon name="power-off" />
              {{ t('advancedControl.monitoring.emergencyStop') }}
            </button>
          </div>
        </section>
      </template>

      <EmptyState
        v-else
        icon="tachometer-alt"
        :title="t('advancedControl.monitoring.emptyTitle')"
        :message="t('advancedControl.monitoring.emptyMessage')"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { formatUptime } from '@/utils/formatHelpers'
import { useI18n } from 'vue-i18n'
import { useTabs } from '@/composables/useTabs'
import { useAdvancedControl } from '@/composables/useAdvancedControl'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useNotificationBus } from '@/composables/useNotificationBus'
import Icon from '@/components/ui/Icon.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import type {
  TakeoverPriority,
  TakeoverStatus,
  StreamingSession,
  StreamingSessionRequest,
} from '@/utils/AdvancedControlApiClient'

const { t } = useI18n()
const { confirm } = useConfirmDialog()
const { notifySuccess } = useNotificationBus()

const {
  pendingTakeovers,
  activeTakeovers,
  takeoverStatus,
  streamingSessions,
  streamingCapabilities,
  systemStatus,
  systemHealth,
  loading,
  error,
  loadTakeovers,
  approve,
  pause,
  resume,
  complete,
  loadStreaming,
  createStreaming,
  terminateStreaming,
  loadMonitoring,
  emergencyStop,
} = useAdvancedControl()

const TAB_IDS = ['takeover', 'streaming', 'monitoring'] as const
type TabId = (typeof TAB_IDS)[number]

const { activeTab, tabAttrs, panelAttrs, handleKeydown, tablistRef, selectTab } = useTabs(TAB_IDS)

interface TabDef {
  id: TabId
  label: string
  icon: 'hand-paper' | 'window-restore' | 'tachometer-alt'
  disabled: boolean
}

const tabs = computed<TabDef[]>(() => [
  { id: 'takeover', label: t('advancedControl.tabs.takeoverQueue'), icon: 'hand-paper', disabled: false },
  { id: 'streaming', label: t('advancedControl.tabs.streaming'), icon: 'window-restore', disabled: false },
  { id: 'monitoring', label: t('advancedControl.tabs.monitoring'), icon: 'tachometer-alt', disabled: false },
])

// Refresh cadence for the Monitoring tab while it is active. A named
// module-level constant rather than a magic number inline (no live-push
// WS is wired here — see startMonitoringPoll below for rationale).
const MONITORING_POLL_INTERVAL_MS = 10000
let monitoringPollTimer: ReturnType<typeof setInterval> | null = null

function stopMonitoringPoll(): void {
  if (monitoringPollTimer !== null) {
    clearInterval(monitoringPollTimer)
    monitoringPollTimer = null
  }
}

function startMonitoringPoll(): void {
  stopMonitoringPoll()
  monitoringPollTimer = setInterval(() => {
    void loadMonitoring()
  }, MONITORING_POLL_INTERVAL_MS)
}

// Load streaming/monitoring data lazily the first time each tab becomes
// active, mirroring the eager onMounted(loadTakeovers) call used for the
// (always-visible) Takeover Queue tab. Monitoring additionally polls
// while active — the backend's /ws/monitoring endpoint only pushes the
// `health` slice (not the full status/resource-usage payload) and,
// unlike its REST siblings, currently has no admin-auth check, so this
// stage intentionally keeps the simpler poll instead of adopting it.
watch(activeTab, (tab) => {
  if (tab === 'streaming') {
    void loadStreaming()
  } else if (tab === 'monitoring') {
    void loadMonitoring()
    startMonitoringPoll()
  } else {
    stopMonitoringPoll()
  }
})

onUnmounted(stopMonitoringPoll)

function clearError(): void {
  error.value = null
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

const priorityBadgeClasses: Record<TakeoverPriority, string> = {
  LOW: 'badge-info',
  MEDIUM: 'badge-bundle',
  HIGH: 'badge-admin',
  CRITICAL: 'badge-inactive',
}

function priorityBadgeClass(priority: TakeoverPriority): string {
  return priorityBadgeClasses[priority] ?? 'badge-bundle'
}

const statusBadgeClasses: Record<TakeoverStatus, string> = {
  pending: 'badge-admin',
  approved: 'badge-bundle',
  active: 'badge-active',
  paused: 'badge-admin',
  completed: 'badge-active',
  rejected: 'badge-inactive',
}

function statusBadgeClass(status: TakeoverStatus): string {
  return statusBadgeClasses[status] ?? 'badge-bundle'
}

const systemStatusLabel = computed(() => {
  const status = takeoverStatus.value?.system_status
  if (status === 'takeover_active') return t('advancedControl.summary.statusTakeoverActive')
  if (status === 'emergency') return t('advancedControl.summary.statusEmergency')
  return t('advancedControl.summary.statusNormal')
})

const systemStatusBadgeClass = computed(() => {
  const status = takeoverStatus.value?.system_status
  if (status === 'emergency') return 'badge-inactive'
  if (status === 'takeover_active') return 'badge-admin'
  return 'badge-active'
})

async function onApprove(requestId: string): Promise<void> {
  await approve(requestId)
}

async function onPause(sessionId: string): Promise<void> {
  await pause(sessionId)
}

async function onResume(sessionId: string): Promise<void> {
  await resume(sessionId)
}

async function onComplete(sessionId: string): Promise<void> {
  await complete(sessionId)
}

const streamingStatusBadgeClasses: Record<StreamingSession['status'], string> = {
  active: 'badge-active',
  paused: 'badge-admin',
  terminated: 'badge-inactive',
}

function streamingStatusBadgeClass(status: StreamingSession['status']): string {
  return streamingStatusBadgeClasses[status] ?? 'badge-bundle'
}

const showCreateForm = ref(false)
const createForm = reactive<{ userId: string; resolution: string; depth: number | null }>({
  userId: '',
  resolution: '',
  depth: null,
})

function resetCreateForm(): void {
  createForm.userId = ''
  createForm.resolution = ''
  createForm.depth = null
}

function toggleCreateForm(): void {
  showCreateForm.value = !showCreateForm.value
  if (!showCreateForm.value) resetCreateForm()
}

async function onCreateStreaming(): Promise<void> {
  if (!createForm.userId.trim()) return
  const request: StreamingSessionRequest = { user_id: createForm.userId.trim() }
  if (createForm.resolution.trim()) request.resolution = createForm.resolution.trim()
  if (createForm.depth != null) request.depth = createForm.depth

  const success = await createStreaming(request)
  if (success) {
    showCreateForm.value = false
    resetCreateForm()
  }
}

async function onTerminateStreaming(sessionId: string): Promise<void> {
  await terminateStreaming(sessionId)
}

// ── Monitoring tab (#12173, #12102 — Stage 3) ──────────────────────────────

const healthStatusClass = computed(() => (systemHealth.value?.status === 'unhealthy' ? 'emergency' : 'normal'))

const healthStatusLabel = computed(() => {
  return systemHealth.value?.status === 'unhealthy'
    ? t('advancedControl.monitoring.statusUnhealthy')
    : t('advancedControl.monitoring.statusHealthy')
})

const healthStatusBadgeClass = computed(() =>
  systemHealth.value?.status === 'unhealthy' ? 'badge-inactive' : 'badge-active'
)

function formatPercent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return `${value.toFixed(1)}%`
}

function formatLoadAverage(loadAverage: [number, number, number] | null): string {
  if (!loadAverage) return '—'
  return loadAverage.map((v) => v.toFixed(2)).join(' / ')
}

async function onEmergencyStop(): Promise<void> {
  const ok = await confirm({
    title: t('advancedControl.monitoring.emergencyStopConfirmTitle'),
    message: t('advancedControl.monitoring.emergencyStopConfirmMessage'),
  })
  if (!ok) return

  const success = await emergencyStop()
  if (success) {
    notifySuccess(t('advancedControl.monitoring.emergencyStopSuccess'))
  }
}

onMounted(loadTakeovers)
</script>

<style scoped>
.advanced-control-view {
  padding: var(--spacing-6);
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: var(--spacing-6);
  gap: var(--spacing-4);
  flex-wrap: wrap;
}

.page-title {
  font-size: var(--text-2xl);
  font-weight: 600;
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-1);
}

.page-subtitle {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: var(--spacing-0);
}

.header-actions {
  display: flex;
  gap: var(--spacing-2);
}

/* ── Tabs ───────────────────────────────────────────────────────────────── */

.acv-tabs {
  display: flex;
  gap: var(--spacing-1);
  border-bottom: 1px solid var(--border-default);
  margin-bottom: var(--spacing-5);
}

.acv-tab {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-secondary);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
}

.acv-tab:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.acv-tab--active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}

.acv-tab__soon {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  background: var(--bg-tertiary);
  padding: var(--spacing-0-5) var(--spacing-1-5);
  border-radius: var(--radius-full);
}

.acv-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-6);
}

/* ── Status summary ─────────────────────────────────────────────────────── */

.status-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--spacing-3);
}

.status-card {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  padding: var(--spacing-4);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
}

.status-card--system {
  justify-content: center;
}

.status-value {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text-primary);
}

.status-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* ── Error banner ───────────────────────────────────────────────────────── */

.error-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  border-radius: var(--radius-lg);
  color: var(--color-error);
}

.btn-dismiss {
  margin-left: auto;
  background: none;
  border: none;
  cursor: pointer;
  color: inherit;
}

/* ── Tables ─────────────────────────────────────────────────────────────── */

.table-section {
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  overflow: hidden;
}

.section-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  margin: var(--spacing-0);
  padding: var(--spacing-4);
  border-bottom: 1px solid var(--border-default);
}

.loading-state {
  padding: var(--spacing-8);
  text-align: center;
  color: var(--text-secondary);
}

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th {
  text-align: left;
  padding: var(--spacing-3) var(--spacing-4);
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-default);
}

.data-table td {
  padding: var(--spacing-3) var(--spacing-4);
  border-bottom: 1px solid var(--border-default);
  font-size: var(--text-sm);
}

.data-table tr:last-child td {
  border-bottom: none;
}

.reason-cell {
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.badge {
  display: inline-block;
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: 600;
}

.badge-admin {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.badge-active {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.badge-inactive {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.badge-bundle {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.badge-info {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.actions-cell {
  display: flex;
  gap: var(--spacing-1);
}

.btn-icon {
  width: 2rem;
  height: 2rem;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xs);
}

.btn-icon:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-warning {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.btn-info {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.btn-success {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.btn-danger {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.btn-action-secondary,
.btn-action-primary {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 500;
  border: 1px solid var(--border-default);
  background: transparent;
  color: var(--text-primary);
  cursor: pointer;
}

.btn-action-primary {
  border-color: transparent;
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.btn-action-secondary:disabled,
.btn-action-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ── Streaming tab ──────────────────────────────────────────────────────── */

.section-title--with-action {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-3);
}

.streaming-create-form {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-tertiary);
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.form-field label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-secondary);
}

.form-field input {
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-surface);
  color: var(--text-primary);
  font-size: var(--text-sm);
}

.form-actions {
  display: flex;
  gap: var(--spacing-2);
  margin-left: auto;
}

/* ── Monitoring tab (#12173, #12102 — Stage 3) ──────────────────────────── */

.status-summary--padded {
  padding: var(--spacing-4);
}

.danger-zone-section {
  border-color: var(--color-error-light);
  background: var(--color-error-bg);
}

.danger-heading {
  color: var(--color-error-dark);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.danger-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-4);
  flex-wrap: wrap;
  padding: var(--spacing-4);
}

.danger-content {
  display: flex;
  gap: var(--spacing-4);
  align-items: flex-start;
  flex: 1;
  min-width: 0;
}

.danger-icon {
  width: 2.5rem;
  height: 2.5rem;
  border-radius: var(--radius-full);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xl);
  background: var(--color-error-bg-hover);
  color: var(--color-error);
  flex-shrink: 0;
}

.danger-text h4 {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  margin: var(--spacing-0) var(--spacing-0) var(--spacing-1);
}

.danger-text p {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: var(--spacing-0);
  line-height: 1.5;
}

.btn-danger-full {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1-5);
  padding: var(--spacing-2) var(--spacing-4);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  font-weight: 600;
  border: 1px solid var(--color-error);
  background: var(--color-error);
  color: var(--text-on-primary);
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
}

.btn-danger-full:hover:not(:disabled) {
  background: var(--color-error-dark);
  border-color: var(--color-error-dark);
}

.btn-danger-full:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
