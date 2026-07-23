<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  AdvancedControlView — minimal admin panel for the #11506 agent-operated
  desktop-session feature. Wires in AdvancedControlApiClient (#12102):
  desktop streaming sessions + human takeover management over the live
  /api/advanced-control/* backend routes.
-->
<template>
  <div class="advanced-control-view view-container">
    <header class="page-header">
      <div class="page-header-content">
        <h2 class="page-title">{{ t('advancedControl.title') }}</h2>
        <p class="page-subtitle">{{ t('advancedControl.subtitle') }}</p>
      </div>
      <div class="header-actions">
        <button class="ac-btn ac-btn-secondary" :disabled="loading" @click="loadAll">
          <Icon name="sync-alt" :spin="loading" />
          {{ t('common.refresh') }}
        </button>
      </div>
    </header>

    <div v-if="error" class="ac-error-banner" role="alert">
      <Icon name="exclamation-circle" />
      <span>{{ error }}</span>
      <button class="ac-dismiss" :aria-label="t('common.dismiss')" @click="error = null">
        <Icon name="times" />
      </button>
    </div>

    <!-- ============================ STREAMING ============================ -->
    <section class="ac-section" aria-labelledby="ac-streaming-title">
      <h3 id="ac-streaming-title" class="ac-section-title">
        {{ t('advancedControl.streamingTitle') }}
      </h3>

      <div class="ac-cards">
        <div class="ac-card">
          <h4 class="ac-card-title">{{ t('advancedControl.capabilitiesTitle') }}</h4>
          <dl v-if="capabilities" class="ac-defs">
            <div><dt>{{ t('advancedControl.capVnc') }}</dt><dd>{{ yesNo(capabilities.vnc_available) }}</dd></div>
            <div><dt>{{ t('advancedControl.capNoVnc') }}</dt><dd>{{ yesNo(capabilities.novnc_available) }}</dd></div>
            <div><dt>{{ t('advancedControl.capMaxSessions') }}</dt><dd>{{ capabilities.max_sessions }}</dd></div>
            <div><dt>{{ t('advancedControl.capResolutions') }}</dt><dd>{{ capabilities.supported_resolutions.join(', ') || '—' }}</dd></div>
            <div><dt>{{ t('advancedControl.capDepths') }}</dt><dd>{{ capabilities.supported_depths.join(', ') || '—' }}</dd></div>
          </dl>
          <p v-else class="ac-muted">{{ t('advancedControl.noCapabilities') }}</p>
        </div>

        <div class="ac-card">
          <h4 class="ac-card-title">{{ t('advancedControl.createSessionTitle') }}</h4>
          <form class="ac-form" @submit.prevent="onCreateSession">
            <label class="ac-field">
              <span class="ac-label">{{ t('advancedControl.fieldUserId') }} <span class="ac-req">*</span></span>
              <input v-model.trim="createForm.user_id" class="ac-input" required
                     :placeholder="t('advancedControl.fieldUserIdPlaceholder')" />
            </label>
            <div class="ac-field-row">
              <label class="ac-field">
                <span class="ac-label">{{ t('advancedControl.fieldResolution') }}</span>
                <input v-model.trim="createForm.resolution" class="ac-input" placeholder="1920x1080" />
              </label>
              <label class="ac-field">
                <span class="ac-label">{{ t('advancedControl.fieldDepth') }}</span>
                <input v-model.number="createForm.depth" type="number" min="8" max="32" class="ac-input" placeholder="24" />
              </label>
            </div>
            <button type="submit" class="ac-btn ac-btn-primary" :disabled="busy.create || !createForm.user_id">
              <Icon v-if="busy.create" name="sync-alt" :spin="true" />
              {{ t('advancedControl.createSession') }}
            </button>
          </form>
        </div>
      </div>

      <div class="ac-table-wrap">
        <div v-if="loading && sessions.length === 0" class="ac-empty">{{ t('common.loading') }}</div>
        <div v-else-if="sessions.length === 0" class="ac-empty">{{ t('advancedControl.noSessions') }}</div>
        <table v-else class="ac-table">
          <thead>
            <tr>
              <th>{{ t('advancedControl.colSessionId') }}</th>
              <th>{{ t('advancedControl.colUser') }}</th>
              <th>{{ t('advancedControl.colDisplay') }}</th>
              <th>{{ t('advancedControl.colVncPort') }}</th>
              <th>{{ t('advancedControl.colStatus') }}</th>
              <th>{{ t('advancedControl.colCreated') }}</th>
              <th class="ac-actions-col">{{ t('common.actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in sessions" :key="s.session_id">
              <td class="ac-mono">{{ s.session_id }}</td>
              <td>{{ s.user_id }}</td>
              <td class="ac-mono">{{ s.display }}</td>
              <td>{{ s.vnc_port }}</td>
              <td><span class="ac-badge" :class="statusClass(s.status)">{{ s.status }}</span></td>
              <td>{{ formatTime(s.created_at) }}</td>
              <td class="ac-actions-col">
                <button class="ac-btn ac-btn-danger ac-btn-sm"
                        :disabled="busy.terminate === s.session_id"
                        @click="onTerminate(s.session_id)">
                  {{ t('advancedControl.terminate') }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- ============================ TAKEOVER ============================ -->
    <section class="ac-section" aria-labelledby="ac-takeover-title">
      <h3 id="ac-takeover-title" class="ac-section-title">
        {{ t('advancedControl.takeoverTitle') }}
      </h3>

      <div v-if="takeoverStatus" class="ac-stats">
        <div class="ac-stat"><span class="ac-stat-value">{{ takeoverStatus.pending_requests_count }}</span><span class="ac-stat-label">{{ t('advancedControl.statPending') }}</span></div>
        <div class="ac-stat"><span class="ac-stat-value">{{ takeoverStatus.active_sessions_count }}</span><span class="ac-stat-label">{{ t('advancedControl.statActive') }}</span></div>
        <div class="ac-stat"><span class="ac-stat-value">{{ takeoverStatus.paused_tasks_count }}</span><span class="ac-stat-label">{{ t('advancedControl.statPaused') }}</span></div>
        <div class="ac-stat"><span class="ac-stat-value">{{ takeoverStatus.total_completed_sessions }}</span><span class="ac-stat-label">{{ t('advancedControl.statCompleted') }}</span></div>
        <div class="ac-stat"><span class="ac-stat-value ac-stat-sys">{{ takeoverStatus.system_status }}</span><span class="ac-stat-label">{{ t('advancedControl.statSystem') }}</span></div>
      </div>

      <div class="ac-card">
        <h4 class="ac-card-title">{{ t('advancedControl.requestTitle') }}</h4>
        <form class="ac-form" @submit.prevent="onRequestTakeover">
          <div class="ac-field-row">
            <label class="ac-field">
              <span class="ac-label">{{ t('advancedControl.fieldTrigger') }}</span>
              <select v-model="requestForm.trigger" class="ac-input">
                <option v-for="trg in triggers" :key="trg" :value="trg">{{ trg }}</option>
              </select>
            </label>
            <label class="ac-field">
              <span class="ac-label">{{ t('advancedControl.fieldPriority') }}</span>
              <select v-model="requestForm.priority" class="ac-input">
                <option v-for="p in priorities" :key="p" :value="p">{{ p }}</option>
              </select>
            </label>
          </div>
          <label class="ac-field">
            <span class="ac-label">{{ t('advancedControl.fieldReason') }} <span class="ac-req">*</span></span>
            <input v-model.trim="requestForm.reason" class="ac-input" required
                   :placeholder="t('advancedControl.fieldReasonPlaceholder')" />
          </label>
          <label class="ac-field">
            <span class="ac-label">{{ t('advancedControl.fieldAgent') }}</span>
            <input v-model.trim="requestForm.requesting_agent" class="ac-input"
                   :placeholder="t('advancedControl.fieldAgentPlaceholder')" />
          </label>
          <button type="submit" class="ac-btn ac-btn-primary" :disabled="busy.request || !requestForm.reason">
            <Icon v-if="busy.request" name="sync-alt" :spin="true" />
            {{ t('advancedControl.requestTakeover') }}
          </button>
        </form>
      </div>

      <!-- Pending requests -->
      <h4 class="ac-subtitle">{{ t('advancedControl.pendingTitle') }}</h4>
      <div class="ac-table-wrap">
        <div v-if="pending.length === 0" class="ac-empty">{{ t('advancedControl.noPending') }}</div>
        <table v-else class="ac-table">
          <thead>
            <tr>
              <th>{{ t('advancedControl.colRequestId') }}</th>
              <th>{{ t('advancedControl.colTrigger') }}</th>
              <th>{{ t('advancedControl.colReason') }}</th>
              <th>{{ t('advancedControl.colPriority') }}</th>
              <th>{{ t('advancedControl.colCreatedAt') }}</th>
              <th class="ac-actions-col">{{ t('advancedControl.colApprove') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in pending" :key="r.request_id">
              <td class="ac-mono">{{ r.request_id }}</td>
              <td>{{ r.trigger }}</td>
              <td>{{ r.reason }}</td>
              <td><span class="ac-badge" :class="priorityClass(r.priority)">{{ r.priority }}</span></td>
              <td>{{ formatTime(r.created_at) }}</td>
              <td class="ac-actions-col ac-approve-cell">
                <input v-model.trim="operatorInputs[r.request_id]" class="ac-input ac-input-sm"
                       :placeholder="t('advancedControl.fieldOperatorPlaceholder')" />
                <button class="ac-btn ac-btn-primary ac-btn-sm"
                        :disabled="busy.approve === r.request_id || !operatorInputs[r.request_id]"
                        @click="onApprove(r.request_id)">
                  {{ t('advancedControl.approve') }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Active takeover sessions -->
      <h4 class="ac-subtitle">{{ t('advancedControl.activeTitle') }}</h4>
      <div class="ac-table-wrap">
        <div v-if="active.length === 0" class="ac-empty">{{ t('advancedControl.noActive') }}</div>
        <table v-else class="ac-table">
          <thead>
            <tr>
              <th>{{ t('advancedControl.colSessionId') }}</th>
              <th>{{ t('advancedControl.colOperator') }}</th>
              <th>{{ t('advancedControl.colStatus') }}</th>
              <th>{{ t('advancedControl.colActionsExecuted') }}</th>
              <th>{{ t('advancedControl.colStarted') }}</th>
              <th class="ac-actions-col">{{ t('common.actions') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in active" :key="a.session_id">
              <td class="ac-mono">{{ a.session_id }}</td>
              <td>{{ a.human_operator }}</td>
              <td><span class="ac-badge" :class="statusClass(a.status)">{{ a.status }}</span></td>
              <td>{{ a.actions_executed }}</td>
              <td>{{ formatTime(a.started_at) }}</td>
              <td class="ac-actions-col">
                <button class="ac-btn ac-btn-secondary ac-btn-sm"
                        :disabled="busy.session === a.session_id || a.status === 'paused'"
                        @click="onPause(a.session_id)">
                  {{ t('advancedControl.pause') }}
                </button>
                <button class="ac-btn ac-btn-secondary ac-btn-sm"
                        :disabled="busy.session === a.session_id || a.status !== 'paused'"
                        @click="onResume(a.session_id)">
                  {{ t('advancedControl.resume') }}
                </button>
                <button class="ac-btn ac-btn-primary ac-btn-sm"
                        :disabled="busy.session === a.session_id"
                        @click="onComplete(a.session_id)">
                  {{ t('advancedControl.complete') }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '@/components/ui/Icon.vue'
import { createLogger } from '@/utils/debugUtils'
import type { ApiResponse } from '@/types/api'
import advancedControlApiClient, {
  type StreamingSession,
  type StreamingCapabilities,
  type PendingTakeoverRequest,
  type ActiveTakeoverSession,
  type TakeoverSystemStatus,
  type TakeoverTrigger,
  type TakeoverPriority,
} from '@/utils/AdvancedControlApiClient'

const { t } = useI18n()
const logger = createLogger('AdvancedControlView')

const loading = ref(false)
const error = ref<string | null>(null)

const capabilities = ref<StreamingCapabilities | null>(null)
const sessions = ref<StreamingSession[]>([])
const takeoverStatus = ref<TakeoverSystemStatus | null>(null)
const pending = ref<PendingTakeoverRequest[]>([])
const active = ref<ActiveTakeoverSession[]>([])

const triggers: TakeoverTrigger[] = [
  'MANUAL_REQUEST', 'CRITICAL_ERROR', 'SECURITY_CONCERN',
  'USER_INTERVENTION_REQUIRED', 'SYSTEM_OVERLOAD', 'APPROVAL_REQUIRED', 'TIMEOUT_EXCEEDED',
]
const priorities: TakeoverPriority[] = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']

const createForm = reactive<{ user_id: string; resolution: string; depth: number | null }>({
  user_id: '', resolution: '', depth: null,
})
const requestForm = reactive<{ trigger: TakeoverTrigger; priority: TakeoverPriority; reason: string; requesting_agent: string }>({
  trigger: 'MANUAL_REQUEST', priority: 'HIGH', reason: '', requesting_agent: '',
})
const operatorInputs = reactive<Record<string, string>>({})

const busy = reactive<{ create: boolean; request: boolean; terminate: string | null; approve: string | null; session: string | null }>({
  create: false, request: false, terminate: null, approve: null, session: null,
})

/** Unwrap an ApiResponse, surfacing the error into the banner on failure. */
async function unwrap<T>(fn: () => Promise<ApiResponse<T>>): Promise<T | null> {
  const res = await fn()
  if (res.success && res.data !== undefined) return res.data as T
  error.value = res.error || t('advancedControl.genericError')
  logger.warn('Advanced-control request failed:', res.error)
  return null
}

async function loadCapabilities() {
  capabilities.value = await unwrap(() => advancedControlApiClient.getStreamingCapabilities())
}
async function loadSessions() {
  const data = await unwrap(() => advancedControlApiClient.listStreamingSessions())
  if (data) sessions.value = data.sessions
}
async function loadTakeoverStatus() {
  takeoverStatus.value = await unwrap(() => advancedControlApiClient.getTakeoverStatus())
}
async function loadPending() {
  const data = await unwrap(() => advancedControlApiClient.getPendingTakeovers())
  if (data) pending.value = data.pending_requests
}
async function loadActive() {
  const data = await unwrap(() => advancedControlApiClient.getActiveTakeovers())
  if (data) active.value = data.active_sessions
}

async function loadAll() {
  loading.value = true
  error.value = null
  await Promise.all([loadCapabilities(), loadSessions(), loadTakeoverStatus(), loadPending(), loadActive()])
  loading.value = false
}

async function onCreateSession() {
  if (!createForm.user_id) return
  busy.create = true
  const data = await unwrap(() => advancedControlApiClient.createStreamingSession({
    user_id: createForm.user_id,
    resolution: createForm.resolution || undefined,
    depth: createForm.depth ?? undefined,
  }))
  busy.create = false
  if (data) {
    createForm.user_id = ''
    await loadSessions()
  }
}

async function onTerminate(sessionId: string) {
  busy.terminate = sessionId
  const data = await unwrap(() => advancedControlApiClient.terminateStreamingSession(sessionId))
  busy.terminate = null
  if (data) await loadSessions()
}

async function onRequestTakeover() {
  if (!requestForm.reason) return
  busy.request = true
  const data = await unwrap(() => advancedControlApiClient.requestTakeover({
    trigger: requestForm.trigger,
    reason: requestForm.reason,
    priority: requestForm.priority,
    requesting_agent: requestForm.requesting_agent || undefined,
  }))
  busy.request = false
  if (data) {
    requestForm.reason = ''
    requestForm.requesting_agent = ''
    await Promise.all([loadPending(), loadTakeoverStatus()])
  }
}

async function onApprove(requestId: string) {
  const operator = operatorInputs[requestId]
  if (!operator) return
  busy.approve = requestId
  const data = await unwrap(() => advancedControlApiClient.approveTakeover(requestId, { human_operator: operator }))
  busy.approve = null
  if (data) await Promise.all([loadPending(), loadActive(), loadTakeoverStatus()])
}

async function onPause(sessionId: string) {
  busy.session = sessionId
  const data = await unwrap(() => advancedControlApiClient.pauseTakeoverSession(sessionId))
  busy.session = null
  if (data) await loadActive()
}

async function onResume(sessionId: string) {
  busy.session = sessionId
  const data = await unwrap(() => advancedControlApiClient.resumeTakeoverSession(sessionId))
  busy.session = null
  if (data) await loadActive()
}

async function onComplete(sessionId: string) {
  busy.session = sessionId
  const data = await unwrap(() => advancedControlApiClient.completeTakeoverSession(sessionId, {
    resolution: t('advancedControl.completedResolution'),
  }))
  busy.session = null
  if (data) await Promise.all([loadActive(), loadTakeoverStatus()])
}

function yesNo(v: boolean): string {
  return v ? t('common.yes') : t('common.no')
}
function formatTime(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}
function statusClass(status: string): string {
  if (status === 'active' || status === 'approved') return 'ac-badge-success'
  if (status === 'paused') return 'ac-badge-warning'
  if (status === 'terminated' || status === 'rejected') return 'ac-badge-danger'
  return 'ac-badge-neutral'
}
function priorityClass(p: string): string {
  if (p === 'CRITICAL' || p === 'HIGH') return 'ac-badge-danger'
  if (p === 'MEDIUM') return 'ac-badge-warning'
  return 'ac-badge-neutral'
}

onMounted(loadAll)
</script>

<style scoped>
.advanced-control-view {
  padding: var(--spacing-6);
  color: var(--text-primary);
}
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}
.page-title {
  font-size: var(--text-2xl);
  font-weight: 600;
  color: var(--text-primary);
}
.page-subtitle {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.ac-error-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-3);
  margin-bottom: var(--spacing-4);
  border: 1px solid var(--color-error-border);
  background: var(--color-error-bg);
  color: var(--color-error);
  border-radius: var(--radius-md);
}
.ac-dismiss {
  margin-left: auto;
  background: transparent;
  border: none;
  color: inherit;
  cursor: pointer;
}
.ac-section {
  margin-bottom: var(--spacing-8);
}
.ac-section-title {
  font-size: var(--text-xl);
  font-weight: 600;
  margin-bottom: var(--spacing-4);
  color: var(--text-primary);
}
.ac-subtitle {
  font-size: var(--text-base);
  font-weight: 600;
  margin: var(--spacing-4) 0 var(--spacing-2);
  color: var(--text-secondary);
}
.ac-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-4);
}
.ac-card {
  padding: var(--spacing-4);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-4);
}
.ac-card-title {
  font-size: var(--text-base);
  font-weight: 600;
  margin-bottom: var(--spacing-3);
}
.ac-defs {
  display: grid;
  gap: var(--spacing-2);
}
.ac-defs > div {
  display: flex;
  justify-content: space-between;
  gap: var(--spacing-4);
  font-size: var(--text-sm);
}
.ac-defs dt {
  color: var(--text-secondary);
}
.ac-defs dd {
  color: var(--text-primary);
  font-weight: 500;
}
.ac-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}
.ac-field {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  flex: 1;
}
.ac-field-row {
  display: flex;
  gap: var(--spacing-3);
}
.ac-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}
.ac-req {
  color: var(--color-error);
}
.ac-input {
  padding: var(--spacing-2);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--bg-input);
  color: var(--text-primary);
  font-size: var(--text-sm);
}
.ac-input-sm {
  padding: var(--spacing-1) var(--spacing-2);
}
.ac-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  background: var(--bg-surface);
  color: var(--text-primary);
}
.ac-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.ac-btn-sm {
  padding: var(--spacing-1) var(--spacing-2);
  font-size: var(--text-xs);
}
.ac-btn-primary {
  background: var(--color-primary);
  color: var(--text-on-primary);
  border-color: var(--color-primary);
}
.ac-btn-primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
}
.ac-btn-secondary {
  background: var(--bg-secondary);
}
.ac-btn-danger {
  background: var(--color-error);
  color: var(--text-on-error);
  border-color: var(--color-error);
}
.ac-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-4);
}
.ac-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--spacing-4);
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
}
.ac-stat-value {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--color-primary);
}
.ac-stat-sys {
  font-size: var(--text-base);
}
.ac-stat-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  text-transform: uppercase;
}
.ac-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  margin-bottom: var(--spacing-4);
}
.ac-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}
.ac-table th,
.ac-table td {
  padding: var(--spacing-2) var(--spacing-3);
  text-align: left;
  border-bottom: 1px solid var(--border-default);
}
.ac-table th {
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-weight: 600;
  font-size: var(--text-xs);
  text-transform: uppercase;
}
.ac-mono {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}
.ac-actions-col {
  display: flex;
  gap: var(--spacing-1);
  flex-wrap: wrap;
}
.ac-approve-cell {
  align-items: center;
}
.ac-empty {
  padding: var(--spacing-6);
  text-align: center;
  color: var(--text-tertiary);
  font-size: var(--text-sm);
}
.ac-muted {
  color: var(--text-tertiary);
  font-size: var(--text-sm);
}
.ac-badge {
  display: inline-block;
  padding: var(--spacing-0-5, 2px) var(--spacing-2);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: 600;
}
.ac-badge-success {
  background: var(--color-success-bg);
  color: var(--color-success);
}
.ac-badge-warning {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}
.ac-badge-danger {
  background: var(--color-error-bg);
  color: var(--color-error);
}
.ac-badge-neutral {
  background: var(--bg-secondary);
  color: var(--text-secondary);
}
</style>
