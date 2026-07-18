<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Process Monitor Tab (#1406)
 *
 * Table of background processes with status, logs, and signal controls.
 * Uses /autobot-api proxy to main backend.
 */

import { computed, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { getBackendUrl } from '@/config/ssot-config'

interface ProcessRun {
  id: string
  agent_id: string
  task_id: string | null
  command: string
  args: string[]
  status: string
  exit_code: number | null
  signal: string | null
  log_excerpt: string | null
  log_path: string | null
  timeout_seconds: number
  started_at: string | null
  completed_at: string | null
  created_at: string | null
}

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

const headers = computed(() => ({
  Authorization: `Bearer ${authStore.token}`,
  'Content-Type': 'application/json',
}))

async function fetchProcesses() {
  if (!agentId.value) return
  loading.value = true
  error.value = null
  selectedProcess.value = null
  fullLog.value = null
  try {
    let url = `${getBackendUrl()}/agents/${agentId.value}/processes?limit=50`
    if (statusFilter.value) url += `&status=${statusFilter.value}`
    const res = await fetch(url, { headers: headers.value })
    if (!res.ok) throw new Error(`Failed to load processes: ${res.status}`)
    const data = await res.json()
    processes.value = data.processes || []
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load processes'
    processes.value = []
  } finally {
    loading.value = false
  }
}

async function fetchFullLog(processId: string) {
  fullLogLoading.value = true
  try {
    const res = await fetch(`${getBackendUrl()}/processes/${processId}/logs`, {
      headers: headers.value,
    })
    fullLog.value = res.ok ? await res.text() : 'Failed to load log'
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

function streamLogs(processId: string) {
  stopStream()
  fullLog.value = ''
  isStreaming.value = true
  const ws = new WebSocket(buildWsUrl(`/processes/${processId}/stream`))
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
    const res = await fetch(`${getBackendUrl()}/processes/${processId}/signal`, {
      method: 'POST',
      headers: headers.value,
      body: JSON.stringify({ signal: sig }),
    })
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(data.detail || `Signal failed: ${res.status}`)
    }
    showKillConfirm.value = null
    await fetchProcesses()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Signal failed'
  }
}

async function spawnProcess() {
  error.value = null
  try {
    const payload = {
      agent_id: spawnForm.value.agent_id || agentId.value,
      command: spawnForm.value.command,
      args: spawnForm.value.args
        ? spawnForm.value.args.split(' ').filter(Boolean)
        : [],
      timeout_seconds: spawnForm.value.timeout_seconds,
    }
    const res = await fetch(`${getBackendUrl()}/processes/spawn`, {
      method: 'POST',
      headers: headers.value,
      body: JSON.stringify(payload),
    })
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(data.detail || `Spawn failed: ${res.status}`)
    }
    showSpawnForm.value = false
    spawnForm.value = { agent_id: '', command: '', args: '', timeout_seconds: 300 }
    await fetchProcesses()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Spawn failed'
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

function formatDuration(start: string | null, end: string | null): string {
  if (!start) return '—'
  const s = new Date(start).getTime()
  const e = end ? new Date(end).getTime() : Date.now()
  const secs = Math.round((e - s) / 1000)
  if (secs < 60) return `${secs}s`
  return `${Math.floor(secs / 60)}m ${secs % 60}s`
}

function formatTime(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}
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
      <button class="btn-primary" @click="fetchProcesses" :disabled="!agentId">
        {{ $t('agents.processMonitorTab.load') }}
      </button>
      <button class="btn-secondary" @click="showSpawnForm = !showSpawnForm">
        {{ $t('agents.processMonitorTab.spawnProcess') }}
      </button>
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
        <button class="btn-primary" @click="spawnProcess">{{ $t('agents.processMonitorTab.spawn') }}</button>
        <button class="btn-cancel" @click="showSpawnForm = false">{{ $t('agents.processMonitorTab.cancel') }}</button>
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
            <td>{{ formatDuration(proc.started_at, proc.completed_at) }}</td>
            <td class="time-cell">{{ formatTime(proc.started_at) }}</td>
            <td>
              <button
                v-if="proc.status === 'running'"
                class="btn-kill"
                @click.stop="showKillConfirm = proc.id"
              >
                {{ $t('agents.processMonitorTab.kill') }}
              </button>
              <div v-if="showKillConfirm === proc.id" class="kill-confirm" @click.stop>
                <button class="btn-confirm" @click="signalProcess(proc.id, 'SIGTERM')">
                  SIGTERM
                </button>
                <button class="btn-confirm btn-danger" @click="signalProcess(proc.id, 'SIGKILL')">
                  SIGKILL
                </button>
                <button class="btn-cancel-sm" @click="showKillConfirm = null">x</button>
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
          <button
            v-if="selectedProcess.status === 'running' && !isStreaming"
            class="btn-secondary"
            @click="streamLogs(selectedProcess.id)"
          >
            {{ $t('agents.processMonitorTab.streamLive') }}
          </button>
          <button
            v-if="isStreaming"
            class="btn-cancel"
            @click="stopStream"
          >
            {{ $t('agents.processMonitorTab.stopStream') }}
          </button>
          <button
            v-if="!isStreaming && !fullLog"
            class="btn-secondary"
            :disabled="fullLogLoading"
            @click="fetchFullLog(selectedProcess.id)"
          >
            {{ fullLogLoading ? $t('agents.processMonitorTab.loading') : $t('agents.processMonitorTab.viewFullLog') }}
          </button>
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
.btn-primary { background: var(--slm-indigo-500); color: white; border: none; padding: var(--spacing-2) var(--spacing-4); border-radius: var(--radius-md); font-size: var(--text-sm); font-weight: 500; cursor: pointer; }
.btn-primary:hover { background: var(--slm-indigo-600); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-secondary { background: white; color: var(--slm-gray-700); border: 1px solid var(--slm-gray-300); padding: var(--spacing-2) var(--spacing-4); border-radius: var(--radius-md); font-size: var(--text-sm); cursor: pointer; }
.btn-secondary:hover { background: var(--slm-gray-100); }
.spawn-form-panel { background: white; border-radius: var(--radius-xl); box-shadow: 0 1px 3px rgba(0,0,0,0.1); padding: var(--spacing-5); margin-bottom: var(--spacing-5); }
.spawn-form-panel h4 { font-size: var(--text-base); font-weight: 600; margin: 0 0 var(--spacing-4) 0; color: var(--text-primary); }
.spawn-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--spacing-3); margin-bottom: var(--spacing-4); }
.spawn-actions { display: flex; gap: var(--spacing-2); }
.btn-cancel { background: var(--slm-gray-200); color: var(--slm-gray-700); border: none; padding: var(--spacing-2) var(--spacing-4); border-radius: var(--radius-md); font-size: var(--text-sm); cursor: pointer; }
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
.badge-red { background: var(--slm-red-100); color: var(--color-danger-600); }
.badge-orange { background: var(--slm-orange-100); color: var(--slm-orange-600); }
.badge-pulse { animation: pulse 2s ease-in-out infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
.btn-kill { background: var(--color-danger-500); color: white; border: none; padding: var(--spacing-1) 10px; border-radius: var(--radius-default); font-size: var(--text-xs); font-weight: 500; cursor: pointer; }
.btn-kill:hover { background: var(--color-danger-600); }
.kill-confirm { display: flex; gap: var(--spacing-1); align-items: center; }
.btn-confirm { background: var(--slm-amber-500); color: white; border: none; padding: var(--spacing-1) var(--spacing-2); border-radius: var(--radius-default); font-size: 11px; cursor: pointer; }
.btn-danger { background: var(--color-danger-500); }
.btn-cancel-sm { background: var(--slm-gray-200); color: var(--slm-gray-700); border: none; padding: 2px 6px; border-radius: var(--radius-default); font-size: 11px; cursor: pointer; }
.log-panel { background: white; border-radius: var(--radius-xl); box-shadow: 0 1px 3px rgba(0,0,0,0.1); padding: var(--spacing-5); margin-top: var(--spacing-5); }
.log-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--spacing-3); }
.log-header h4 { font-size: var(--text-base); font-weight: 600; margin: 0; color: var(--text-primary); display: flex; align-items: center; gap: var(--spacing-2); }
.log-actions { display: flex; gap: var(--spacing-2); }
.streaming-badge { font-size: 10px; padding: 2px var(--spacing-2); border-radius: var(--radius-default); font-weight: 600; background: var(--color-danger-600); color: white; animation: pulse 1.5s ease-in-out infinite; }
.log-content { background: var(--slm-slate-800); color: var(--slm-slate-200); border-radius: var(--radius-lg); padding: var(--spacing-4); font-family: 'IBM Plex Mono', monospace; font-size: var(--text-xs); line-height: 1.6; overflow-x: auto; max-height: 400px; overflow-y: auto; white-space: pre-wrap; word-break: break-word; }
.error-banner { background: var(--slm-red-100); border: 1px solid var(--color-danger-500); color: var(--slm-red-700); padding: var(--spacing-3) var(--spacing-4); border-radius: var(--radius-lg); margin-bottom: var(--spacing-4); display: flex; justify-content: space-between; align-items: center; }
.loading { text-align: center; color: var(--text-secondary); padding: 60px; }
.empty-state { text-align: center; color: var(--text-secondary); padding: 60px; }
</style>
