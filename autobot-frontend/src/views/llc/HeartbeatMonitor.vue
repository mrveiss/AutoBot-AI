<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="heartbeat-monitor">
    <div class="monitor-header">
      <h2 class="view-title">Heartbeat Monitor</h2>
      <span class="refresh-note">Auto-refreshes every 15s</span>
    </div>

    <div v-if="isLoading && agents.length === 0" class="state-msg">Loading agents...</div>
    <div v-else-if="heartbeatAgents.length === 0" class="state-msg">No heartbeat-enabled agents found.</div>

    <div v-else class="agent-grid-wrapper">
      <table class="agent-grid">
        <thead>
          <tr>
            <th>Agent</th>
            <th>Adapter</th>
            <th>Last Heartbeat</th>
            <th>Status</th>
            <th>Run Duration</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="agent in heartbeatAgents"
            :key="agent.id"
            class="agent-row"
            @click="openHistory(agent)"
          >
            <td class="agent-name">{{ agent.name }}</td>
            <td class="agent-adapter">{{ agent.adapter_type ?? '—' }}</td>
            <td class="agent-hb">{{ formatDate(agent.last_heartbeat_at) }}</td>
            <td>
              <span class="status-dot" :class="`status-${agent.last_run_status ?? 'unknown'}`" />
              <span class="status-label" :class="`status-${agent.last_run_status ?? 'unknown'}`">
                {{ agent.last_run_status ?? 'unknown' }}
              </span>
            </td>
            <td class="agent-duration">{{ formatDuration(agent.current_run_started_at) }}</td>
            <td @click.stop>
              <button
                class="btn-trigger"
                :disabled="triggering.has(agent.id)"
                @click="triggerHeartbeat(agent)"
              >
                {{ triggering.has(agent.id) ? 'Triggering...' : 'Trigger Now' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Run history drawer -->
    <div v-if="selectedAgent" class="drawer-overlay" @click.self="selectedAgent = null">
      <div class="history-drawer">
        <div class="drawer-header">
          <h3>Run History – {{ selectedAgent.name }}</h3>
          <button class="btn-close" @click="selectedAgent = null">✕</button>
        </div>
        <div v-if="historyLoading" class="state-msg">Loading runs...</div>
        <div v-else-if="runHistory.length === 0" class="state-msg">No runs found.</div>
        <div v-else class="run-list">
          <div v-for="run in runHistory" :key="run.id" class="run-item">
            <div class="run-meta">
              <span class="status-dot" :class="`status-${run.status}`" />
              <span class="run-status" :class="`status-${run.status}`">{{ run.status }}</span>
              <span class="run-date">{{ formatDate(run.started_at) }}</span>
              <span v-if="run.finished_at" class="run-duration">
                {{ computeDuration(run.started_at, run.finished_at) }}
              </span>
            </div>
            <div class="run-actions">
              <button class="toggle-payload" @click="toggleRun(run.id)">
                {{ expandedRuns.has(run.id) ? 'Hide' : 'Show' }} Context
              </button>
              <button
                class="btn-replay"
                :disabled="replayingRuns.has(run.id)"
                @click="triggerReplay(run)"
              >
                {{ replayingRuns.has(run.id) ? 'Replaying...' : 'Replay' }}
              </button>
              <button class="btn-replay-log" @click="openReplayPanel(run)">
                Step-Browse
              </button>
              <button
                v-if="selectedAgent"
                class="btn-fixture"
                :disabled="downloadingFixture.has(run.id)"
                @click="downloadFixture(run)"
              >{{ downloadingFixture.has(run.id) ? 'Exporting...' : 'Export Fixture' }}</button>
            </div>
            <pre v-if="expandedRuns.has(run.id)" class="run-context">{{ formatJson(run.context_snapshot) }}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- Replay step-browser panel -->
    <div v-if="replayPanelRun && selectedAgent" class="drawer-overlay" @click.self="replayPanelRun = null">
      <div class="history-drawer replay-panel">
        <div class="drawer-header">
          <h3>Replay Log – {{ replayPanelRun.id.slice(0, 8) }}</h3>
          <div class="header-actions">
            <label class="redact-label">
              <input v-model="redactPii" type="checkbox" />
              Redact PII
            </label>
            <button class="btn-close" @click="replayPanelRun = null">✕</button>
          </div>
        </div>
        <div v-if="replayLogLoading" class="state-msg">Loading replay log...</div>
        <div v-else-if="!replayLog" class="state-msg">No replay log recorded for this run yet.</div>
        <div v-else class="replay-body">
          <div class="replay-meta">
            <span class="meta-item">Status: <strong>{{ replayLog.final_status ?? '—' }}</strong></span>
            <span class="meta-item">Events: <strong>{{ (replayLog.recorded_events ?? []).length }}</strong></span>
            <span v-if="replayLog.replay_of_run_id" class="meta-item">
              Replay of: <code>{{ replayLog.replay_of_run_id.slice(0, 8) }}</code>
            </span>
          </div>

          <!-- Event timeline step-browser -->
          <div v-if="(replayLog.recorded_events ?? []).length > 0" class="event-browser">
            <div class="event-nav">
              <button :disabled="eventIdx === 0" @click="eventIdx = Math.max(0, eventIdx - 1)">Prev</button>
              <span>{{ eventIdx + 1 }} / {{ replayLog.recorded_events!.length }}</span>
              <button :disabled="eventIdx >= (replayLog.recorded_events!.length - 1)" @click="eventIdx = Math.min(replayLog.recorded_events!.length - 1, eventIdx + 1)">Next</button>
            </div>
            <pre class="event-detail">{{ formatJson(replayLog.recorded_events![eventIdx]) }}</pre>
          </div>

          <!-- Output diff section (shown when a replay run exists) -->
          <div v-if="replayDiff" class="diff-section">
            <h4 class="diff-title">Output Diff (original vs replay)</h4>
            <pre class="diff-content" :class="{ 'diff-identical': replayDiff.identical }">{{ replayDiff.identical ? '(outputs are identical)' : replayDiff.diff }}</pre>
          </div>

          <!-- Output text -->
          <div v-if="replayLog.output_text" class="output-section">
            <h4 class="output-title">Captured Output</h4>
            <pre class="run-context">{{ replayLog.output_text }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useApiClient } from '@/plugins/api'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const props = defineProps<{ companyId?: string }>()
const companyId = computed(() => props.companyId ?? '')

const logger = createLogger('HeartbeatMonitor')
const api = useApiClient()

interface Agent {
  id: string
  name: string
  adapter_type?: string
  heartbeat_enabled: boolean
  last_heartbeat_at?: string
  last_run_status?: string
  current_run_started_at?: string
}

interface AgentRun {
  id: string
  status: string
  started_at: string
  finished_at?: string
  completed_at?: string
  context_snapshot?: Record<string, unknown>
}

interface ReplayLog {
  id: string
  run_id: string | null
  replay_of_run_id: string | null
  agent_id: string
  inputs_snapshot: Record<string, unknown> | null
  agent_snapshot: Record<string, unknown> | null
  recorded_events: Record<string, unknown>[] | null
  output_text: string | null
  final_status: string | null
  created_at: string | null
}

interface RunDiff {
  run_id_a: string
  run_id_b: string
  diff: string
  identical: boolean
}

const agents = ref<Agent[]>([])
const isLoading = ref(false)
const triggering = ref<Set<string>>(new Set())
const selectedAgent = ref<Agent | null>(null)
const runHistory = ref<AgentRun[]>([])
const historyLoading = ref(false)
const expandedRuns = ref<Set<string>>(new Set())

// Replay state
const replayingRuns = ref<Set<string>>(new Set())
const replayPanelRun = ref<AgentRun | null>(null)
const replayLog = ref<ReplayLog | null>(null)
const replayLogLoading = ref(false)
const replayDiff = ref<RunDiff | null>(null)
const redactPii = ref(false)
const eventIdx = ref(0)
const downloadingFixture = ref<Set<string>>(new Set())

const heartbeatAgents = computed(() => agents.value.filter(a => a.heartbeat_enabled))

function formatDate(iso?: string) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

function formatDuration(startedAt?: string) {
  if (!startedAt) return '—'
  const ms = Date.now() - new Date(startedAt).getTime()
  if (ms < 0) return '—'
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m ${s % 60}s`
}

function computeDuration(start: string, end: string) {
  const ms = new Date(end).getTime() - new Date(start).getTime()
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m ${s % 60}s`
}

function formatJson(data?: Record<string, unknown>) {
  if (!data) return '(empty)'
  try {
    return JSON.stringify(data, null, 2)
  } catch {
    return String(data)
  }
}

function toggleRun(id: string) {
  const next = new Set(expandedRuns.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedRuns.value = next
}

async function triggerReplay(run: AgentRun) {
  if (!selectedAgent.value) return
  const next = new Set(replayingRuns.value)
  next.add(run.id)
  replayingRuns.value = next
  try {
    const result = await api.post<{ new_run_id: string; status: string }>(
      `/api/llc/agents/${selectedAgent.value.id}/runs/${run.id}/replay`,
      {},
    )
    logger.info('Replay triggered, new run:', result.new_run_id)
    await openHistory(selectedAgent.value)
  } catch (err) {
    logger.error('Replay trigger failed', err)
  } finally {
    const s = new Set(replayingRuns.value)
    s.delete(run.id)
    replayingRuns.value = s
  }
}

async function fetchReplayLog(agentId: string, run: AgentRun): Promise<void> {
  replayLogLoading.value = true
  try {
    // Literal `?` kept outside the interpolation so the llc-wiring-audit can
    // strip the query string and match the route path.
    const url = `/api/llc/agents/${agentId}/runs/${run.id}/replay-log?redact_pii=${redactPii.value}`
    replayLog.value = await api.get<ReplayLog>(url)
  } catch (err) {
    logger.error('Failed to load replay log', err)
    replayLog.value = null
  } finally {
    replayLogLoading.value = false
  }
}

async function fetchReplayDiff(agentId: string, run: AgentRun): Promise<void> {
  const replayOfId = (replayLog.value as ReplayLog | null)?.replay_of_run_id
  if (!replayOfId) return
  try {
    const url = `/api/llc/agents/${agentId}/runs/${replayOfId}/diff/${run.id}`
    replayDiff.value = await api.get<RunDiff>(url)
  } catch (err) {
    logger.error('Failed to load replay diff', err)
    replayDiff.value = null
  }
}

async function openReplayPanel(run: AgentRun) {
  if (!selectedAgent.value) return
  replayPanelRun.value = run
  replayLog.value = null
  replayDiff.value = null
  eventIdx.value = 0
  const agentId = selectedAgent.value.id
  await fetchReplayLog(agentId, run)
  // M2: fetch diff when this run is itself a replay (has replay_of_run_id).
  const currentLog = replayLog.value as ReplayLog | null
  if (currentLog?.replay_of_run_id) {
    await fetchReplayDiff(agentId, run)
  }
}

// L4: re-fetch replay log when redactPii toggles while panel is open.
watch(redactPii, async () => {
  if (replayPanelRun.value && selectedAgent.value) {
    await fetchReplayLog(selectedAgent.value.id, replayPanelRun.value)
  }
})

// M1: download fixture via authenticated fetch → blob (no bare <a href> 401).
async function downloadFixture(run: AgentRun) {
  if (!selectedAgent.value) return
  const next = new Set(downloadingFixture.value)
  next.add(run.id)
  downloadingFixture.value = next
  try {
    const url = `${getApiBase()}/llc/agents/${selectedAgent.value.id}/runs/${run.id}/fixture`
    const res = await fetchWithAuth(url)
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    const blob = await res.blob()
    const objectUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = objectUrl
    a.download = `fixture_${run.id.slice(0, 8)}.json`
    a.click()
    URL.revokeObjectURL(objectUrl)
  } catch (err) {
    logger.error('Fixture export failed', err)
  } finally {
    const s = new Set(downloadingFixture.value)
    s.delete(run.id)
    downloadingFixture.value = s
  }
}

async function fetchAgents() {
  isLoading.value = true
  try {
    // company_id passed as a query param; backend defaults to the caller's
    // org when omitted (companyId is always present via the :companyId route).
    const data = await api.get<Agent[] | { items: Agent[] }>(
      `/api/llc/agents?company_id=${companyId.value}`,
    )
    agents.value = Array.isArray(data) ? data : (data as { items: Agent[] }).items ?? []
  } catch (err) {
    logger.error('Failed to fetch agents', err)
  } finally {
    isLoading.value = false
  }
}

async function triggerHeartbeat(agent: Agent) {
  const next = new Set(triggering.value)
  next.add(agent.id)
  triggering.value = next
  try {
    await api.post<{ run_id: string; status: string }>(`/api/llc/agents/${agent.id}/heartbeat/trigger`, {})
    await fetchAgents()
  } catch (err) {
    logger.error('Heartbeat trigger failed', err)
  } finally {
    const s = new Set(triggering.value)
    s.delete(agent.id)
    triggering.value = s
  }
}

async function openHistory(agent: Agent) {
  selectedAgent.value = agent
  expandedRuns.value = new Set()
  historyLoading.value = true
  try {
    const data = await api.get<AgentRun[] | { items: AgentRun[] }>(`/api/llc/agents/${agent.id}/runs`)
    runHistory.value = Array.isArray(data) ? data : (data as { items: AgentRun[] }).items ?? []
  } catch (err) {
    logger.error('Failed to fetch run history', err)
    runHistory.value = []
  } finally {
    historyLoading.value = false
  }
}

let refreshInterval: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  fetchAgents()
  refreshInterval = setInterval(fetchAgents, 15_000)
})

onUnmounted(() => {
  if (refreshInterval !== null) clearInterval(refreshInterval)
})
</script>

<style scoped>
.heartbeat-monitor {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 1.5rem;
  gap: 1rem;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.monitor-header {
  display: flex;
  align-items: baseline;
  gap: 1rem;
}

.view-title {
  font-size: 1.5rem;
  font-weight: 600;
  margin: 0;
}

.refresh-note {
  font-size: 0.8rem;
  color: var(--text-secondary, #9ca3af);
}

.state-msg {
  text-align: center;
  padding: 3rem;
  color: var(--text-secondary, #9ca3af);
}

.agent-grid-wrapper {
  overflow: auto;
  border: 1px solid var(--border-default, #e5e7eb);
  border-radius: 0.5rem;
  flex: 1;
}

.agent-grid {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.agent-grid th {
  padding: 0.625rem 0.75rem;
  text-align: left;
  font-weight: 600;
  background: var(--bg-elevated, #f9fafb);
  border-bottom: 1px solid var(--border-default, #e5e7eb);
  white-space: nowrap;
}

.agent-row {
  border-bottom: 1px solid var(--border-default, #f3f4f6);
  cursor: pointer;
  transition: background 0.1s;
}

.agent-row:hover {
  background: var(--bg-hover, #f9fafb);
}

.agent-grid td {
  padding: 0.625rem 0.75rem;
}

.agent-name {
  font-weight: 500;
}

.status-dot {
  display: inline-block;
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  margin-right: 0.375rem;
  vertical-align: middle;
}

.status-label {
  font-size: 0.8rem;
  font-weight: 500;
  text-transform: capitalize;
}

.status-succeeded { color: #10b981; }
.status-succeeded.status-dot { background: #10b981; }
.status-running { color: #3b82f6; }
.status-running.status-dot { background: #3b82f6; }
.status-queued { color: #f59e0b; }
.status-queued.status-dot { background: #f59e0b; }
.status-failed { color: #ef4444; }
.status-failed.status-dot { background: #ef4444; }
.status-timed_out { color: #ef4444; }
.status-timed_out.status-dot { background: #ef4444; }
.status-unknown { color: var(--text-secondary, #9ca3af); }
.status-unknown.status-dot { background: var(--border-default, #d1d5db); }

.btn-trigger {
  padding: 0.3rem 0.75rem;
  background: var(--color-primary, #3b82f6);
  color: white;
  border: none;
  border-radius: 0.375rem;
  font-size: 0.8rem;
  cursor: pointer;
  white-space: nowrap;
}

.btn-trigger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.drawer-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 50;
  display: flex;
  justify-content: flex-end;
}

.history-drawer {
  width: 480px;
  max-width: 100%;
  height: 100%;
  background: var(--bg-surface, #fff);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border-default, #e5e7eb);
}

.drawer-header h3 {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
}

.btn-close {
  background: none;
  border: none;
  font-size: 1.125rem;
  cursor: pointer;
  color: var(--text-secondary, #6b7280);
}

.run-list {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.run-item {
  border: 1px solid var(--border-default, #e5e7eb);
  border-radius: 0.375rem;
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.run-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
}

.run-date,
.run-duration {
  font-size: 0.8rem;
  color: var(--text-secondary, #6b7280);
}

.toggle-payload {
  font-size: 0.8rem;
  padding: 0.2rem 0.5rem;
  border: 1px solid var(--border-default, #d1d5db);
  border-radius: 0.25rem;
  background: var(--bg-elevated, #f9fafb);
  cursor: pointer;
  align-self: flex-start;
}

.run-context {
  background: var(--bg-elevated, #f9fafb);
  border: 1px solid var(--border-default, #e5e7eb);
  border-radius: 0.375rem;
  padding: 0.75rem;
  font-size: 0.8rem;
  overflow-x: auto;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.run-actions {
  display: flex;
  gap: 0.375rem;
  flex-wrap: wrap;
  align-items: center;
}

.btn-replay,
.btn-replay-log {
  padding: 0.2rem 0.5rem;
  border: 1px solid var(--border-default, #d1d5db);
  border-radius: 0.25rem;
  background: var(--bg-elevated, #f9fafb);
  cursor: pointer;
  font-size: 0.8rem;
}

.btn-replay:hover,
.btn-replay-log:hover {
  background: var(--bg-hover, #f3f4f6);
}

.btn-replay:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-fixture {
  padding: 0.2rem 0.5rem;
  border: 1px solid var(--border-default, #d1d5db);
  border-radius: 0.25rem;
  background: var(--bg-elevated, #f9fafb);
  font-size: 0.8rem;
  text-decoration: none;
  color: var(--text-primary, #374151);
}

.replay-panel {
  width: 560px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.redact-label {
  font-size: 0.8rem;
  display: flex;
  align-items: center;
  gap: 0.25rem;
  cursor: pointer;
}

.replay-body {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.replay-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  font-size: 0.875rem;
}

.meta-item {
  color: var(--text-secondary, #6b7280);
}

.event-browser {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.event-nav {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
}

.event-nav button {
  padding: 0.2rem 0.5rem;
  border: 1px solid var(--border-default, #d1d5db);
  border-radius: 0.25rem;
  background: var(--bg-elevated, #f9fafb);
  cursor: pointer;
  font-size: 0.8rem;
}

.event-nav button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.event-detail {
  background: var(--bg-elevated, #f9fafb);
  border: 1px solid var(--border-default, #e5e7eb);
  border-radius: 0.375rem;
  padding: 0.75rem;
  font-size: 0.8rem;
  overflow-x: auto;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow-y: auto;
}

.diff-section,
.output-section {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.diff-title,
.output-title {
  margin: 0;
  font-size: 0.875rem;
  font-weight: 600;
}

.diff-content {
  background: var(--bg-elevated, #f9fafb);
  border: 1px solid var(--border-default, #e5e7eb);
  border-radius: 0.375rem;
  padding: 0.75rem;
  font-size: 0.75rem;
  overflow-x: auto;
  margin: 0;
  white-space: pre;
  max-height: 250px;
  overflow-y: auto;
}

.diff-identical {
  color: var(--text-secondary, #6b7280);
}
</style>
