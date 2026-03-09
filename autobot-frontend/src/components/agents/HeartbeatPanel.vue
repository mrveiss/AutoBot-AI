<template>
  <div class="heartbeat-panel">
    <div class="panel-header">
      <h3>Heartbeat Status</h3>
      <div class="agent-selector">
        <label for="agent-id-input">Agent ID</label>
        <input
          id="agent-id-input"
          v-model="agentId"
          type="text"
          placeholder="Enter agent ID"
          @keyup.enter="loadData"
        />
        <button class="btn-load" :disabled="!agentId || loading" @click="loadData">Load</button>
      </div>
    </div>

    <div v-if="error" class="error-banner">{{ error }}</div>

    <template v-if="config">
      <div class="card config-card">
        <div class="card-title">Configuration</div>
        <div class="config-grid">
          <div class="config-row">
            <span class="label">Enabled</span>
            <span :class="['badge', config.heartbeat_enabled ? 'badge-green' : 'badge-gray']">
              {{ config.heartbeat_enabled ? 'Active' : 'Disabled' }}
            </span>
          </div>
          <div class="config-row">
            <span class="label">Interval</span>
            <span class="value">{{ config.heartbeat_interval_seconds }}s</span>
          </div>
          <div class="config-row">
            <span class="label">Max Duration</span>
            <span class="value">{{ config.max_run_duration_seconds }}s</span>
          </div>
          <div class="config-row">
            <span class="label">Last Heartbeat</span>
            <span class="value">{{ formatTime(config.last_heartbeat_at) }}</span>
          </div>
          <div class="config-row">
            <span class="label">Current Task</span>
            <span class="value mono">{{ config.current_task_id || '—' }}</span>
          </div>
        </div>
        <div class="config-actions">
          <label class="toggle-label">
            <input v-model="editEnabled" type="checkbox" />
            Enable heartbeat
          </label>
          <div class="interval-input">
            <label>Interval (s)</label>
            <input v-model.number="editInterval" type="number" min="10" />
          </div>
          <div class="interval-input">
            <label>Max Duration (s)</label>
            <input v-model.number="editMaxDuration" type="number" min="10" />
          </div>
          <button class="btn-save" :disabled="saving" @click="saveConfig">
            {{ saving ? 'Saving…' : 'Save' }}
          </button>
          <button class="btn-trigger" :disabled="triggering" @click="triggerManual">
            {{ triggering ? 'Triggering…' : 'Run Now' }}
          </button>
        </div>
      </div>

      <div class="card">
        <div class="card-title">
          Wakeup Queue
          <span class="count-badge">{{ pendingWakeups.length }}</span>
          <button class="btn-sm btn-queue" :disabled="queueing" @click="queueWakeup">
            + Queue Wakeup
          </button>
        </div>
        <div v-if="pendingWakeups.length === 0" class="empty-state">No pending wakeup requests</div>
        <table v-else class="data-table">
          <thead>
            <tr>
              <th>Priority</th>
              <th>Reason</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="req in pendingWakeups" :key="req.id">
              <td>{{ req.priority }}</td>
              <td>{{ req.reason || '—' }}</td>
              <td class="mono">{{ formatTime(req.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card">
        <div class="card-title">Run History</div>
        <div v-if="runs.length === 0" class="empty-state">No runs recorded yet</div>
        <table v-else class="data-table">
          <thead>
            <tr>
              <th>Status</th>
              <th>Trigger</th>
              <th>Started</th>
              <th>Duration</th>
              <th>Tokens</th>
              <th>Cost</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="run in runs"
              :key="run.id"
              class="run-row"
              @click="toggleEvents(run.id)"
            >
              <td>
                <span :class="['badge', statusClass(run.status)]">{{ run.status }}</span>
              </td>
              <td class="mono">{{ run.trigger }}</td>
              <td class="mono">{{ formatTime(run.started_at) }}</td>
              <td class="mono">{{ duration(run) }}</td>
              <td class="mono">{{ run.tokens_used ?? '—' }}</td>
              <td class="mono">
                {{ run.cost_usd != null ? '$' + run.cost_usd.toFixed(4) : '—' }}
              </td>
              <td class="chevron">{{ expandedRunId === run.id ? '▲' : '▼' }}</td>
            </tr>
            <tr v-if="expandedRunId && expandedRun" class="events-row">
              <td colspan="7">
                <div class="events-container">
                  <div v-if="expandedRun.error_message" class="error-message">
                    {{ expandedRun.error_message }}
                  </div>
                  <div v-if="expandedRun.events.length === 0" class="empty-state">No events</div>
                  <div v-for="ev in expandedRun.events" :key="ev.id" class="event-row">
                    <span class="event-time mono">{{ ev.occurred_at.slice(11, 19) }}</span>
                    <span class="event-type">{{ ev.event_type }}</span>
                    <span v-if="ev.message" class="event-msg">{{ ev.message }}</span>
                  </div>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

import { getBackendUrl } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('HeartbeatPanel')

interface HeartbeatConfig {
  agent_id: string
  heartbeat_enabled: boolean
  heartbeat_interval_seconds: number
  max_run_duration_seconds: number
  current_task_id: string | null
  last_heartbeat_at: string | null
  session_params: Record<string, unknown> | null
  extra: Record<string, unknown> | null
  created_at: string | null
  updated_at: string | null
}

interface RunEvent {
  id: string
  event_type: string
  message: string | null
  payload: Record<string, unknown> | null
  occurred_at: string
}

interface HeartbeatRun {
  id: string
  agent_id: string
  status: string
  trigger: string
  wakeup_context: Record<string, unknown> | null
  started_at: string | null
  finished_at: string | null
  tokens_used: number | null
  cost_usd: number | null
  model: string | null
  provider: string | null
  error_message: string | null
  created_at: string | null
  events: RunEvent[]
}

interface WakeupRequest {
  id: string
  agent_id: string
  priority: number
  context: Record<string, unknown> | null
  reason: string | null
  consumed: boolean
  consumed_at: string | null
  created_at: string | null
}

const agentId = ref('')
const loading = ref(false)
const saving = ref(false)
const triggering = ref(false)
const queueing = ref(false)
const error = ref<string | null>(null)
const config = ref<HeartbeatConfig | null>(null)
const runs = ref<HeartbeatRun[]>([])
const pendingWakeups = ref<WakeupRequest[]>([])
const editEnabled = ref(false)
const editInterval = ref(300)
const editMaxDuration = ref(600)
const expandedRunId = ref<string | null>(null)
const expandedRun = computed(() => runs.value.find((r) => r.id === expandedRunId.value) ?? null)

function apiBase(): string {
  return `${getBackendUrl()}/api/heartbeat`
}

async function apiFetch(path: string, init?: RequestInit): Promise<unknown> {
  const token = localStorage.getItem('access_token')
  const resp = await fetch(`${apiBase()}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...init,
  })
  if (!resp.ok) {
    const text = await resp.text()
    throw new Error(`${resp.status}: ${text}`)
  }
  return resp.status === 204 ? null : resp.json()
}

async function loadData(): Promise<void> {
  if (!agentId.value) return
  loading.value = true
  error.value = null
  try {
    const [cfgRes, runsRes, wakeupsRes] = await Promise.all([
      apiFetch(`/${agentId.value}/config`),
      apiFetch(`/${agentId.value}/runs?limit=20`),
      apiFetch(`/${agentId.value}/wakeup`),
    ])
    config.value = cfgRes as HeartbeatConfig
    runs.value = runsRes as HeartbeatRun[]
    pendingWakeups.value = wakeupsRes as WakeupRequest[]
    editEnabled.value = config.value.heartbeat_enabled
    editInterval.value = config.value.heartbeat_interval_seconds
    editMaxDuration.value = config.value.max_run_duration_seconds
  } catch (err) {
    error.value = String(err)
    logger.error('Failed to load heartbeat data', err)
  } finally {
    loading.value = false
  }
}

async function saveConfig(): Promise<void> {
  if (!agentId.value) return
  saving.value = true
  error.value = null
  try {
    const updated = await apiFetch(`/${agentId.value}/config`, {
      method: 'PUT',
      body: JSON.stringify({
        heartbeat_enabled: editEnabled.value,
        heartbeat_interval_seconds: editInterval.value,
        max_run_duration_seconds: editMaxDuration.value,
      }),
    })
    config.value = updated as HeartbeatConfig
  } catch (err) {
    error.value = String(err)
  } finally {
    saving.value = false
  }
}

async function triggerManual(): Promise<void> {
  if (!agentId.value) return
  triggering.value = true
  error.value = null
  try {
    await apiFetch(`/${agentId.value}/trigger`, { method: 'POST' })
    setTimeout(() => loadData(), 1500)
  } catch (err) {
    error.value = String(err)
  } finally {
    triggering.value = false
  }
}

async function queueWakeup(): Promise<void> {
  if (!agentId.value) return
  queueing.value = true
  error.value = null
  try {
    await apiFetch(`/${agentId.value}/wakeup`, {
      method: 'POST',
      body: JSON.stringify({ priority: 0, reason: 'Manual wakeup from UI' }),
    })
    const wakeupsRes = await apiFetch(`/${agentId.value}/wakeup`)
    pendingWakeups.value = wakeupsRes as WakeupRequest[]
  } catch (err) {
    error.value = String(err)
  } finally {
    queueing.value = false
  }
}

function toggleEvents(runId: string): void {
  expandedRunId.value = expandedRunId.value === runId ? null : runId
}

function formatTime(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

function duration(run: HeartbeatRun): string {
  if (!run.started_at || !run.finished_at) return '—'
  const ms = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()
  return `${(ms / 1000).toFixed(1)}s`
}

function statusClass(status: string): string {
  const map: Record<string, string> = {
    queued: 'badge-blue',
    running: 'badge-yellow',
    completed: 'badge-green',
    failed: 'badge-red',
    timed_out: 'badge-orange',
    cancelled: 'badge-gray',
  }
  return map[status] ?? 'badge-gray'
}
</script>

<style scoped>
.heartbeat-panel {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  font-size: 0.875rem;
  color: var(--text-primary, #e2e8f0);
}
.panel-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}
.panel-header h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
}
.agent-selector {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.agent-selector label {
  color: var(--text-secondary, #94a3b8);
}
.agent-selector input {
  background: var(--bg-input, #1e293b);
  border: 1px solid var(--border, #334155);
  border-radius: 4px;
  color: inherit;
  padding: 0.25rem 0.5rem;
  width: 200px;
}
.error-banner {
  background: rgba(239, 68, 68, 0.15);
  border: 1px solid rgba(239, 68, 68, 0.4);
  border-radius: 6px;
  color: #fca5a5;
  padding: 0.5rem 0.75rem;
}
.card {
  background: var(--bg-card, #1e293b);
  border: 1px solid var(--border, #334155);
  border-radius: 8px;
  padding: 1rem;
}
.card-title {
  font-weight: 600;
  margin-bottom: 0.75rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.config-grid {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  margin-bottom: 1rem;
}
.config-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.config-row .label {
  width: 130px;
  color: var(--text-secondary, #94a3b8);
  flex-shrink: 0;
}
.mono {
  font-family: monospace;
}
.config-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
  border-top: 1px solid var(--border, #334155);
  padding-top: 0.75rem;
}
.toggle-label {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  cursor: pointer;
}
.interval-input {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.interval-input label {
  color: var(--text-secondary, #94a3b8);
  white-space: nowrap;
}
.interval-input input {
  width: 70px;
  background: var(--bg-input, #0f172a);
  border: 1px solid var(--border, #334155);
  border-radius: 4px;
  color: inherit;
  padding: 0.2rem 0.4rem;
}
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
}
.data-table th {
  text-align: left;
  color: var(--text-secondary, #94a3b8);
  padding: 0.3rem 0.5rem;
  border-bottom: 1px solid var(--border, #334155);
}
.data-table td {
  padding: 0.35rem 0.5rem;
  border-bottom: 1px solid rgba(51, 65, 85, 0.4);
}
.run-row {
  cursor: pointer;
}
.run-row:hover td {
  background: rgba(255, 255, 255, 0.03);
}
.chevron {
  text-align: right;
  color: var(--text-secondary, #94a3b8);
}
.events-row td {
  background: var(--bg-input, #0f172a);
  padding: 0;
}
.events-container {
  padding: 0.5rem 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.error-message {
  color: #fca5a5;
  margin-bottom: 0.5rem;
}
.event-row {
  display: flex;
  gap: 0.5rem;
  align-items: baseline;
}
.event-time {
  color: var(--text-secondary, #94a3b8);
  flex-shrink: 0;
}
.event-type {
  font-weight: 600;
  color: #60a5fa;
  flex-shrink: 0;
}
.event-msg {
  color: var(--text-primary, #e2e8f0);
}
.empty-state {
  color: var(--text-secondary, #94a3b8);
  font-style: italic;
  padding: 0.5rem 0;
}
.count-badge {
  background: var(--bg-input, #0f172a);
  border-radius: 10px;
  font-size: 0.75rem;
  padding: 0.1rem 0.4rem;
}
button {
  background: var(--bg-btn, #334155);
  border: 1px solid var(--border, #475569);
  border-radius: 4px;
  color: inherit;
  cursor: pointer;
  font-size: 0.8rem;
  padding: 0.3rem 0.6rem;
  transition: background 0.15s;
}
button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
button:not(:disabled):hover {
  background: var(--bg-btn-hover, #475569);
}
.btn-load,
.btn-save {
  background: #3b82f6;
  border-color: #2563eb;
}
.btn-load:not(:disabled):hover,
.btn-save:not(:disabled):hover {
  background: #2563eb;
}
.btn-trigger {
  background: #10b981;
  border-color: #059669;
}
.btn-trigger:not(:disabled):hover {
  background: #059669;
}
.btn-queue {
  background: #8b5cf6;
  border-color: #7c3aed;
}
.btn-sm {
  font-size: 0.75rem;
  padding: 0.15rem 0.45rem;
}
.badge {
  border-radius: 4px;
  font-size: 0.72rem;
  font-weight: 600;
  padding: 0.1rem 0.45rem;
  text-transform: uppercase;
}
.badge-green { background: rgba(16, 185, 129, 0.2); color: #34d399; }
.badge-gray { background: rgba(100, 116, 139, 0.2); color: #94a3b8; }
.badge-blue { background: rgba(59, 130, 246, 0.2); color: #60a5fa; }
.badge-yellow { background: rgba(234, 179, 8, 0.2); color: #facc15; }
.badge-red { background: rgba(239, 68, 68, 0.2); color: #f87171; }
.badge-orange { background: rgba(249, 115, 22, 0.2); color: #fb923c; }
</style>
