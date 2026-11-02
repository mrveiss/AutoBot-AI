<script setup lang="ts">
import { BaseButton } from '@autobot/ui'
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Process Monitor Tab (#1406)
 *
 * Table of background processes with status, logs, and signal controls.
 *
 * #13079: the REST calls reach the autobot backend through `useAutobotApi`,
 * the SLM app's single client for that backend, instead of a private `fetch`
 * that sent only `Bearer ${authStore.token}` (no `autobot_access_token`
 * fallback, no 401 cleanup, no timeout). The live-log WebSocket below stays on
 * the native transport — `useAutobotApi` is HTTP-only and a socket has no
 * equivalent there.
 *
 * #16374: the nginx `/autobot-api/` location now runs an `auth_request`
 * session check before it forwards anything to the backend. A browser
 * WebSocket handshake cannot carry a custom `Authorization` header, so the
 * log-stream socket carries the SLM session token as a `Sec-WebSocket-Protocol`
 * subprotocol instead (`new WebSocket(url, ['bearer', token])`) — the
 * dedicated nginx stream location reads it from that header, never the URL,
 * so the JWT never lands in an access log, browser history, or the request
 * forwarded to the backend.
 */

import { useI18n } from 'vue-i18n'
import { ref, computed } from 'vue'
import { getBackendUrl } from '@/config/ssot-config'
import { useAuthStore } from '@/stores/auth'
import { formatDuration, createDateFormatter } from '@/utils/formatHelpers'
import {
  useAutobotApi,
  autobotApiErrorMessage,
  type ProcessRun,
} from '@/composables/useAutobotApi'

const { t } = useI18n()
const api = useAutobotApi()
const authStore = useAuthStore()
const processes = ref<ProcessRun[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const agentId = ref('')
const statusFilter = ref('')
const selectedProcess = ref<ProcessRun | null>(null)
const fullLog = ref<string | null>(null)
const fullLogLoading = ref(false)
const showSpawnForm = ref(false)
const showKillConfirm = ref<string | null>(null)
const streamSocket = ref<WebSocket | null>(null)
const isStreaming = ref(false)

const spawnForm = ref({
  agent_id: '',
  command: '',
  args: '',
  timeout_seconds: 300,
})

async function fetchProcesses() {
  if (!agentId.value) return
  loading.value = true
  error.value = null
  selectedProcess.value = null
  fullLog.value = null
  try {
    processes.value = await api.getAgentProcesses(agentId.value, {
      limit: 50,
      status: statusFilter.value || undefined,
    })
  } catch (err) {
    error.value = autobotApiErrorMessage(err, t('agents.processMonitorTab.loadFailed'))
    processes.value = []
  } finally {
    loading.value = false
  }
}

async function fetchFullLog(processId: string) {
  fullLogLoading.value = true
  try {
    fullLog.value = await api.getProcessLogs(processId)
  } catch {
    fullLog.value = 'Failed to load log'
  } finally {
    fullLogLoading.value = false
  }
}

function stopStream() {
  if (streamSocket.value) {
    streamSocket.value.close()
    streamSocket.value = null
  }
  isStreaming.value = false
}

function buildWsUrl(path: string): string {
  const base = getBackendUrl()
  if (!base) {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${window.location.host}${path}`
  }
  const proto = base.startsWith('https') ? 'wss:' : 'ws:'
  const wsBase = base.replace(/^https?:\/\//, '').replace(/\/$/, '')
  return `${proto}//${wsBase}${path}`
}

/**
 * #16374: a native `new WebSocket()` handshake cannot set an `Authorization`
 * header, so the SLM session token rides in the `Sec-WebSocket-Protocol`
 * subprotocol list instead of the URL — JWT characters (base64url plus the
 * `.` segment separators) are all valid HTTP token characters (RFC 7230
 * `tchar`), so the token is a legal subprotocol value. nginx's dedicated
 * stream location reads it back out of that header (never the URL) to run
 * the session check, then strips it before proxying to the backend, which
 * accepts the same `bearer` subprotocol so the browser completes the
 * handshake (RFC 6455 4.2.2 requires the server to echo one of the offered
 * subprotocols).
 */
function streamLogs(processId: string) {
  stopStream()
  fullLog.value = ''
  isStreaming.value = true
  const ws = authStore.token
    ? new WebSocket(buildWsUrl(`/processes/${processId}/stream`), ['bearer', authStore.token])
    : new WebSocket(buildWsUrl(`/processes/${processId}/stream`))
  streamSocket.value = ws
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.done) {
        isStreaming.value = false
        fetchProcesses()
      }
    } catch {
      fullLog.value = (fullLog.value || '') + event.data
    }
  }
  ws.onclose = () => {
    isStreaming.value = false
  }
  ws.onerror = () => {
    isStreaming.value = false
    if (!fullLog.value) fetchFullLog(processId)
  }
}

async function signalProcess(processId: string, sig: string) {
  try {
    await api.signalProcess(processId, sig)
    showKillConfirm.value = null
    await fetchProcesses()
  } catch (err) {
    error.value = autobotApiErrorMessage(err, t('agents.processMonitorTab.signalFailed'))
  }
}

async function spawnProcess() {
  error.value = null
  try {
    await api.spawnProcess({
      agent_id: spawnForm.value.agent_id || agentId.value,
      command: spawnForm.value.command,
      args: spawnForm.value.args ? spawnForm.value.args.split(' ').filter(Boolean) : [],
      timeout_seconds: spawnForm.value.timeout_seconds,
    })
    showSpawnForm.value = false
    spawnForm.value = { agent_id: '', command: '', args: '', timeout_seconds: 300 }
    await fetchProcesses()
  } catch (err) {
    error.value = autobotApiErrorMessage(err, t('agents.processMonitorTab.spawnFailed'))
  }
}

function selectProcess(proc: ProcessRun) {
  stopStream()
  if (selectedProcess.value?.id === proc.id) {
    selectedProcess.value = null
    fullLog.value = null
    return
  }
  selectedProcess.value = proc
  fullLog.value = null
  if (proc.status === 'running') {
    streamLogs(proc.id)
  }
}

function statusBadgeClass(status: string): string {
  const map: Record<string, string> = {
    queued: 'badge-gray',
    running: 'badge-blue badge-pulse',
    completed: 'badge-green',
    failed: 'badge-red',
    timed_out: 'badge-orange',
    cancelled: 'badge-gray',
  }
  return map[status] || 'badge-gray'
}

const DURATION_OPTIONS = computed(() => ({
  style: 'msMinutesSeconds',
  nullText: '—',
  units: {
    seconds: t('agents.processMonitorTab.durationSeconds'),
    minutes: t('agents.processMonitorTab.durationMinutes'),
  },
}) as const)

const formatTime = createDateFormatter({ emptyText: '—' })
</script>

<template>
  <div class="process-monitor-tab">
    <div v-if="error" class="error-banner">
      {{ error }}
      <button @click="error = null">{{ $t('agents.processMonitorTab.dismiss') }}</button>
    </div>

    <!-- Controls -->
    <div class="controls-bar">
      <div class="control-group">
        <label>{{ $t('agents.processMonitorTab.agentID') }}</label>
        <input
          v-model="agentId"
          :placeholder="$t('agents.processMonitorTab.eGOrchestrator')"
          @keyup.enter="fetchProcesses"
        />
      </div>
      <div class="control-group">
        <label>{{ $t('agents.processMonitorTab.status') }}</label>
        <select v-model="statusFilter">
          <option value="">{{ $t('agents.processMonitorTab.all') }}</option>
          <option value="queued">{{ $t('agents.processMonitorTab.queued') }}</option>
          <option value="running">{{ $t('agents.processMonitorTab.running') }}</option>
          <option value="completed">{{ $t('agents.processMonitorTab.completed') }}</option>
          <option value="failed">{{ $t('agents.processMonitorTab.failed') }}</option>
          <option value="timed_out">{{ $t('agents.processMonitorTab.timedOut') }}</option>
        </select>
      </div>
      <BaseButton @click="fetchProcesses" :disabled="!agentId">
        {{ $t('agents.processMonitorTab.load') }}
      </BaseButton>
      <BaseButton variant="secondary" @click="showSpawnForm = !showSpawnForm">
        {{ $t('agents.processMonitorTab.spawnProcess') }}
      </BaseButton>
    </div>

    <!-- Spawn form -->
    <div v-if="showSpawnForm" class="spawn-form-panel">
      <h4>{{ $t('agents.processMonitorTab.spawnNewProcess') }}</h4>
      <div class="spawn-grid">
        <div class="control-group">
          <label>{{ $t('agents.processMonitorTab.agentID') }}</label>
          <input v-model="spawnForm.agent_id" :placeholder="agentId || 'agent_id'" />
        </div>
        <div class="control-group">
          <label>{{ $t('agents.processMonitorTab.command') }}</label>
          <input v-model="spawnForm.command" :placeholder="$t('agents.processMonitorTab.usrBinPython3')" />
        </div>
        <div class="control-group">
          <label>{{ $t('agents.processMonitorTab.arguments') }}</label>
          <input v-model="spawnForm.args" :placeholder="$t('agents.processMonitorTab.scriptPyFlag')" />
        </div>
        <div class="control-group">
          <label>{{ $t('agents.processMonitorTab.timeoutS') }}</label>
          <input v-model.number="spawnForm.timeout_seconds" type="number" min="1" max="86400" />
        </div>
      </div>
      <div class="spawn-actions">
        <BaseButton @click="spawnProcess">{{ $t('agents.processMonitorTab.spawn') }}</BaseButton>
        <BaseButton variant="secondary" @click="showSpawnForm = false">{{ $t('agents.processMonitorTab.cancel') }}</BaseButton>
      </div>
    </div>

    <div v-if="loading" class="loading">{{ $t('agents.processMonitorTab.loadingProcesses') }}</div>

    <!-- Process table -->
    <div v-else-if="processes.length" class="process-table-wrapper">
      <table class="process-table">
        <thead>
          <tr>
            <th>{{ $t('agents.processMonitorTab.status') }}</th>
            <th>{{ $t('agents.processMonitorTab.command') }}</th>
            <th>{{ $t('agents.processMonitorTab.exit') }}</th>
            <th>{{ $t('agents.processMonitorTab.duration') }}</th>
            <th>{{ $t('agents.processMonitorTab.started') }}</th>
            <th>{{ $t('agents.processMonitorTab.actions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="proc in processes"
            :key="proc.id"
            :class="{ selected: selectedProcess?.id === proc.id }"
            @click="selectProcess(proc)"
          >
            <td>
              <span :class="['status-badge', statusBadgeClass(proc.status)]">{{
                proc.status
              }}</span>
            </td>
            <td class="command-cell">
              {{ proc.command }} {{ (proc.args || []).join(' ') }}
            </td>
            <td>{{ proc.exit_code ?? '—' }}</td>
            <td>{{ formatDuration(proc.started_at, proc.completed_at, DURATION_OPTIONS) }}</td>
            <td class="time-cell">{{ formatTime(proc.started_at) }}</td>
            <td>
              <BaseButton variant="error" size="xs"
                v-if="proc.status === 'running'"
                @click.stop="showKillConfirm = proc.id"
              >
                {{ $t('agents.processMonitorTab.kill') }}
              </BaseButton>
              <div v-if="showKillConfirm === proc.id" class="kill-confirm" @click.stop>
                <BaseButton variant="warning" size="xs" @click="signalProcess(proc.id, 'SIGTERM')">
                  SIGTERM
                </BaseButton>
                <BaseButton variant="error" size="xs" @click="signalProcess(proc.id, 'SIGKILL')">
                  SIGKILL
                </BaseButton>
                <BaseButton variant="secondary" size="xs" @click="showKillConfirm = null">x</BaseButton>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-else-if="agentId && !loading" class="empty-state">{{ $t('agents.processMonitorTab.noProcessesFoundForAgentValue0', { value0: agentId }) }}</div>

    <!-- Log viewer -->
    <div v-if="selectedProcess" class="log-panel">
      <div class="log-header">
        <h4>{{ $t('agents.processMonitorTab.processValue0Logs', { value0: selectedProcess.id.slice(0, 8) }) }}<span v-if="isStreaming" class="streaming-badge">{{ $t('agents.processMonitorTab.lIVE') }}</span>
        </h4>
        <div class="log-actions">
          <BaseButton variant="secondary"
            v-if="selectedProcess.status === 'running' && !isStreaming"
            @click="streamLogs(selectedProcess.id)"
          >
            {{ $t('agents.processMonitorTab.streamLive') }}
          </BaseButton>
          <BaseButton variant="secondary"
            v-if="isStreaming"
            @click="stopStream"
          >
            {{ $t('agents.processMonitorTab.stopStream') }}
          </BaseButton>
          <BaseButton variant="secondary"
            v-if="!isStreaming && !fullLog"
            :disabled="fullLogLoading"
            @click="fetchFullLog(selectedProcess.id)"
          >
            {{ fullLogLoading ? $t('agents.processMonitorTab.loading') : $t('agents.processMonitorTab.viewFullLog') }}
          </BaseButton>
        </div>
      </div>
      <pre class="log-content">{{ fullLog || selectedProcess.log_excerpt || $t('agents.processMonitorTab.noLogOutput') }}</pre>
    </div>
  </div>
</template>

<style scoped>
.controls-bar { display: flex; align-items: flex-end; gap: var(--spacing-3); margin-bottom: var(--spacing-5); background: white; padding: var(--spacing-4) var(--spacing-5); border-radius: var(--radius-xl); box-shadow: 0 1px 3px rgba(0,0,0,0.1); flex-wrap: wrap; }
.control-group { display: flex; flex-direction: column; gap: var(--spacing-1); }
.control-group label { font-size: 13px; font-weight: 500; color: var(--text-secondary); }
.control-group input, .control-group select { padding: var(--spacing-2) var(--spacing-3); border: 1px solid var(--slm-gray-300); border-radius: var(--radius-lg); font-size: var(--text-sm); min-width: 160px; }
.spawn-form-panel { background: white; border-radius: var(--radius-xl); box-shadow: 0 1px 3px rgba(0,0,0,0.1); padding: var(--spacing-5); margin-bottom: var(--spacing-5); }
.spawn-form-panel h4 { font-size: var(--text-base); font-weight: 600; margin: 0 0 var(--spacing-4) 0; color: var(--text-primary); }
.spawn-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--spacing-3); margin-bottom: var(--spacing-4); }
.spawn-actions { display: flex; gap: var(--spacing-2); }
.process-table-wrapper { background: white; border-radius: var(--radius-xl); box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden; }
.process-table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
.process-table th { text-align: left; padding: var(--spacing-3) var(--spacing-4); background: var(--slm-gray-50); color: var(--text-secondary); font-weight: 600; font-size: var(--text-xs); text-transform: uppercase; border-bottom: 1px solid var(--slm-gray-200); }
.process-table td { padding: var(--spacing-3) var(--spacing-4); border-bottom: 1px solid var(--slm-gray-100); color: var(--text-primary); }
.process-table tr { cursor: pointer; }
.process-table tr:hover { background: var(--slm-gray-50); }
.process-table tr.selected { background: var(--slm-indigo-100); }
.command-cell { font-family: 'IBM Plex Mono', monospace; font-size: var(--text-xs); max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.time-cell { font-size: var(--text-xs); color: var(--text-secondary); }
.status-badge { font-size: 10px; padding: 2px var(--spacing-2); border-radius: var(--radius-default); font-weight: 600; text-transform: uppercase; }
.badge-gray { background: var(--slm-gray-100); color: var(--slm-gray-500); }
.badge-blue { background: var(--slm-blue-100); color: var(--slm-blue-600); }
.badge-green { background: var(--slm-emerald-100); color: var(--slm-emerald-600); }
.badge-red { background: var(--slm-red-100); color: var(--color-error-600); }
.badge-orange { background: var(--slm-orange-100); color: var(--slm-orange-600); }
.badge-pulse { animation: pulse 2s ease-in-out infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
.kill-confirm { display: flex; gap: var(--spacing-1); align-items: center; }
.log-panel { background: white; border-radius: var(--radius-xl); box-shadow: 0 1px 3px rgba(0,0,0,0.1); padding: var(--spacing-5); margin-top: var(--spacing-5); }
.log-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-3); }
.log-header h4 { font-size: var(--text-base); font-weight: 600; margin: 0; color: var(--text-primary); display: flex; align-items: center; gap: var(--spacing-2); }
.log-actions { display: flex; gap: var(--spacing-2); }
.streaming-badge { font-size: 10px; padding: 2px var(--spacing-2); border-radius: var(--radius-default); font-weight: 600; background: var(--color-error-600); color: white; animation: pulse 1.5s ease-in-out infinite; }
.log-content { background: var(--slm-slate-800); color: var(--slm-slate-200); border-radius: var(--radius-lg); padding: var(--spacing-4); font-family: 'IBM Plex Mono', monospace; font-size: var(--text-xs); line-height: 1.6; overflow-x: auto; max-height: 400px; overflow-y: auto; white-space: pre-wrap; word-break: break-word; }
.error-banner { background: var(--slm-red-100); border: 1px solid var(--color-error-500); color: var(--slm-red-700); padding: var(--spacing-3) var(--spacing-4); border-radius: var(--radius-lg); margin-bottom: var(--spacing-4); display: flex; justify-content: space-between; align-items: center; }
.loading { text-align: center; color: var(--text-secondary); padding: 60px; }
.empty-state { text-align: center; color: var(--text-secondary); padding: 60px; }
</style>
