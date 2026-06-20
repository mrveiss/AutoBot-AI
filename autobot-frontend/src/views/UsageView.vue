// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
<template>
  <div class="usage-view">
    <div class="page-header">
      <div class="page-header-content">
        <h2 class="page-title">Usage &amp; Cost Tracking</h2>
        <p class="page-subtitle">Token usage, LLM costs, and billing-ready metrics</p>
      </div>
      <div class="header-actions">
        <select v-model="days" class="period-select" @change="load">
          <option :value="7">Last 7 days</option>
          <option :value="30">Last 30 days</option>
          <option :value="90">Last 90 days</option>
        </select>
        <button class="btn-action-secondary" :disabled="loading" @click="load">
          <Icon name="sync-alt" :spin="loading" />
          Refresh
        </button>
        <button v-if="isAdmin" class="btn-action-secondary" :disabled="csvLoading" @click="downloadCsv">
          <Icon name="download" :spin="csvLoading" />
          Export CSV
        </button>
      </div>
    </div>

    <div v-if="error" class="error-banner">
      <Icon name="exclamation-circle" />
      <span>{{ error }}</span>
      <button class="btn-dismiss" :aria-label="$t('common.dismiss')" @click="error = null"><Icon name="times" /></button>
    </div>

    <!-- Tabs -->
    <div class="tab-bar">
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'personal' }"
        @click="activeTab = 'personal'"
      >
        My Usage
      </button>
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'realtime' }"
        @click="activeTab = 'realtime'; loadRealtimeSessions()"
      >
        Realtime Sessions
      </button>
      <button
        v-if="isAdmin"
        class="tab-btn"
        :class="{ active: activeTab === 'admin' }"
        @click="activeTab = 'admin'"
      >
        System Overview
      </button>
    </div>

    <!-- Personal Tab -->
    <template v-if="activeTab === 'personal'">
      <div v-if="loading" class="loading-row">
        <Icon name="sync-alt" :spin="true" /> Loading...
      </div>
      <template v-else-if="personal">
        <div class="summary-grid">
          <div class="stat-card">
            <div class="stat-label">My Total Tokens</div>
            <div class="stat-value">
              {{ ((personal.input_tokens ?? 0) + (personal.output_tokens ?? 0)).toLocaleString() }}
            </div>
            <div class="stat-sub">
              {{ (personal.input_tokens ?? 0).toLocaleString() }} in /
              {{ (personal.output_tokens ?? 0).toLocaleString() }} out
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-label">My Total Cost</div>
            <div class="stat-value">${{ (personal.total_cost_usd ?? 0).toFixed(4) }}</div>
            <div class="stat-sub">All time</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">My Requests</div>
            <div class="stat-value">{{ (personal.call_count ?? 0).toLocaleString() }}</div>
            <div class="stat-sub">LLM API calls</div>
          </div>
        </div>

        <!-- Recent requests -->
        <div class="table-section">
          <h3 class="section-title">Recent Requests</h3>
          <table v-if="personalRecent.length" class="usage-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Provider</th>
                <th>Model</th>
                <th>Input Tokens</th>
                <th>Output Tokens</th>
                <th>Cost (USD)</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in personalRecent" :key="i">
                <td>{{ r.timestamp ? new Date(r.timestamp).toLocaleString() : '—' }}</td>
                <td>{{ r.provider ?? '—' }}</td>
                <td>{{ r.model ?? '—' }}</td>
                <td>{{ (r.input_tokens ?? 0).toLocaleString() }}</td>
                <td>{{ (r.output_tokens ?? 0).toLocaleString() }}</td>
                <td>${{ (r.cost_usd ?? 0).toFixed(6) }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-row">No recent request history available.</div>
        </div>
      </template>
      <div v-else class="empty-row">No personal usage data available.</div>
    </template>

    <!-- Realtime Sessions Tab (Issue #7421) -->
    <template v-if="activeTab === 'realtime'">
      <div v-if="realtimeLoading" class="loading-row">
        <Icon name="sync-alt" :spin="true" /> Loading Realtime sessions...
      </div>
      <template v-else>
        <div class="summary-grid">
          <div class="stat-card">
            <div class="stat-label">Sessions</div>
            <div class="stat-value">{{ realtimeSessions.length }}</div>
            <div class="stat-sub">Last {{ limit }} loaded</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Total Duration</div>
            <div class="stat-value">{{ fmtSeconds(realtimeTotalDuration) }}</div>
            <div class="stat-sub">Audio in + out</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Estimated Cost</div>
            <div class="stat-value">${{ realtimeTotalCost.toFixed(4) }}</div>
            <div class="stat-sub">Audio + token charges</div>
          </div>
        </div>

        <div class="table-section">
          <h3 class="section-title">Realtime Sessions</h3>
          <table v-if="realtimeSessions.length" class="usage-table">
            <thead>
              <tr>
                <th>Started</th>
                <th>Model</th>
                <th>Duration</th>
                <th>Audio In</th>
                <th>Audio Out</th>
                <th>Tokens In</th>
                <th>Tokens Out</th>
                <th>Tool Calls</th>
                <th>Cost (USD)</th>
                <th>Ended</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="s in realtimeSessions" :key="s.session_id">
                <td>{{ fmtDate(s.started_at) }}</td>
                <td>{{ s.model }}</td>
                <td>{{ fmtSeconds(s.duration_s) }}</td>
                <td>{{ fmtSeconds(s.audio_in_s) }}</td>
                <td>{{ fmtSeconds(s.audio_out_s) }}</td>
                <td>{{ s.input_tokens.toLocaleString() }}</td>
                <td>{{ s.output_tokens.toLocaleString() }}</td>
                <td>{{ s.tool_calls }}</td>
                <td>${{ s.estimated_cost_usd.toFixed(4) }}</td>
                <td :class="{ 'text-warning': s.disconnect_reason !== 'normal' }">
                  {{ s.disconnect_reason }}
                </td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-row">No Realtime session history found.</div>
        </div>
      </template>
    </template>

    <!-- Admin Tab -->
    <template v-if="activeTab === 'admin' && isAdmin">
      <div v-if="loading" class="loading-row">
        <Icon name="sync-alt" :spin="true" /> Loading...
      </div>
      <template v-else>
        <!-- Summary Cards -->
        <div v-if="summary" class="summary-grid">
          <div class="stat-card">
            <div class="stat-label">Total Tokens</div>
            <div class="stat-value">{{ summary.tokens.total.toLocaleString() }}</div>
            <div class="stat-sub">
              {{ summary.tokens.input.toLocaleString() }} in /
              {{ summary.tokens.output.toLocaleString() }} out
            </div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Total Cost</div>
            <div class="stat-value">${{ summary.cost_usd.toFixed(4) }}</div>
            <div class="stat-sub">Last {{ summary.period.days }} days</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Requests</div>
            <div class="stat-value">{{ summary.requests.toLocaleString() }}</div>
            <div class="stat-sub">{{ summary.active_users }} active users</div>
          </div>
        </div>

        <!-- Per-User Table -->
        <div class="table-section">
          <h3 class="section-title">Usage by User</h3>
          <table v-if="users.length" class="usage-table">
            <thead>
              <tr>
                <th>User</th>
                <th>Requests</th>
                <th>Input Tokens</th>
                <th>Output Tokens</th>
                <th>Cost (USD)</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in users" :key="u.user_id">
                <td>{{ u.user_id || '(unknown)' }}</td>
                <td>{{ u.call_count.toLocaleString() }}</td>
                <td>{{ u.input_tokens.toLocaleString() }}</td>
                <td>{{ u.output_tokens.toLocaleString() }}</td>
                <td>${{ u.total_cost_usd.toFixed(4) }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-row">No usage data available.</div>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getApiBase } from '@/config/ssot-config'
import { useApiClient } from '@/plugins/api'
import { useUserStore } from '@/stores/useUserStore'
import { createLogger } from '@/utils/debugUtils'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import Icon from '@/components/ui/Icon.vue'

const logger = createLogger('UsageView')
const api = useApiClient()
const userStore = useUserStore()
const isAdmin = computed(() => userStore.isAdmin)

interface UsageSummary {
  period: { days: number; start: string; end: string }
  tokens: { input: number; output: number; total: number }
  cost_usd: number
  requests: number
  active_users: number
}

interface UserUsage {
  user_id: string
  call_count: number
  input_tokens: number
  output_tokens: number
  total_cost_usd: number
}

interface PersonalUsage {
  user_id?: string
  call_count?: number
  input_tokens?: number
  output_tokens?: number
  total_cost_usd?: number
  recent_requests?: RecentRequest[]
}

interface RecentRequest {
  timestamp?: string
  provider?: string
  model?: string
  input_tokens?: number
  output_tokens?: number
  cost_usd?: number
}

// Issue #7421: Realtime session record type (mirrors SessionSummary on backend)
interface RealtimeSession {
  session_id: string
  user_id: string | null
  model: string
  started_at: string
  ended_at: string | null
  duration_s: number
  audio_in_s: number
  audio_out_s: number
  input_tokens: number
  output_tokens: number
  tool_calls: number
  estimated_cost_usd: number
  disconnect_reason: string
}

const activeTab = ref<'personal' | 'admin' | 'realtime'>('personal')
const days = ref(30)
const loading = ref(false)
const csvLoading = ref(false)
const error = ref<string | null>(null)
const summary = ref<UsageSummary | null>(null)
const users = ref<UserUsage[]>([])
const personal = ref<PersonalUsage | null>(null)
const personalRecent = computed<RecentRequest[]>(() => personal.value?.recent_requests ?? [])

// Issue #7421: Realtime sessions state
const realtimeSessions = ref<RealtimeSession[]>([])
const realtimeLoading = ref(false)
const limit = 20
const realtimeTotalDuration = computed(() => realtimeSessions.value.reduce((s, r) => s + r.duration_s, 0))
const realtimeTotalCost = computed(() => realtimeSessions.value.reduce((s, r) => s + r.estimated_cost_usd, 0))

async function load() {
  loading.value = true
  error.value = null
  try {
    const personalResult = await api.get<PersonalUsage>(`${getApiBase()}/usage/me`)
    personal.value = personalResult

    if (isAdmin.value) {
      const [sum, byUser] = await Promise.all([
        api.get<UsageSummary>(`${getApiBase()}/usage/summary?days=${days.value}`),
        api.get<{ users: UserUsage[] }>(`${getApiBase()}/usage/by-user`),
      ])
      summary.value = sum
      users.value = byUser.users ?? []
    }
  } catch (e) {
    logger.error('Failed to load usage data:', e)
    error.value = 'Failed to load usage data.'
  } finally {
    loading.value = false
  }
}

async function downloadCsv() {
  csvLoading.value = true
  try {
    const res = await fetchWithAuth(`${getApiBase()}/usage/export/csv?days=${days.value}`)
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `usage_${days.value}d.csv`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    logger.error('CSV export failed:', e)
    error.value = 'CSV export failed. Check that you have admin access.'
  } finally {
    csvLoading.value = false
  }
}

// Issue #7421: load recent Realtime sessions
async function loadRealtimeSessions() {
  realtimeLoading.value = true
  try {
    const res = await fetchWithAuth(`${getApiBase()}/voice/realtime/sessions?limit=${limit}`)
    if (!res.ok) throw new Error(`${res.status}`)
    realtimeSessions.value = (await res.json()) as RealtimeSession[]
  } catch (e) {
    logger.error('Failed to load Realtime sessions:', e)
  } finally {
    realtimeLoading.value = false
  }
}

function fmtSeconds(s: number): string {
  if (s < 60) return `${s.toFixed(0)}s`
  const m = Math.floor(s / 60)
  const sec = Math.round(s % 60)
  return `${m}m ${sec}s`
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString()
}

onMounted(load)
</script>

<style scoped>
@reference "../assets/tailwind.css";

.usage-view {
  contain: layout style paint;
  display: flex;
  flex-direction: column;
  min-height: 100%;
  padding: var(--spacing-5);
  background: var(--bg-primary);
  overflow-y: auto;
  gap: var(--spacing-5);
}

.header-actions {
  display: flex;
  gap: var(--spacing-2);
  align-items: center;
}

.period-select {
  padding: var(--spacing-2) var(--spacing-3);
  font-size: var(--text-sm);
  color: var(--text-primary);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
}

.btn-action-secondary {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  text-decoration: none;
  transition: background var(--duration-150) var(--ease-in-out);
}

.btn-action-secondary:hover:not(:disabled) {
  background: var(--bg-tertiary);
}

.btn-action-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-3) var(--spacing-4);
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  border-radius: var(--radius-md);
  color: var(--color-error);
}

.error-banner span { flex: 1; font-size: var(--text-sm); }

.btn-dismiss {
  padding: var(--spacing-1) var(--spacing-2);
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-md);
}

.tab-bar {
  display: flex;
  gap: var(--spacing-1);
  border-bottom: 1px solid var(--border-default);
}

.tab-btn {
  padding: var(--spacing-2) var(--spacing-4);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-secondary);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: color var(--duration-150) var(--ease-in-out);
  margin-bottom: -1px;
}

.tab-btn:hover {
  color: var(--text-primary);
}

.tab-btn.active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-4);
}

.stat-card {
  padding: var(--spacing-4);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
}

.stat-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-1);
}

.stat-value {
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.stat-sub {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  margin-top: var(--spacing-1);
}

.table-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.section-title {
  padding: var(--spacing-4) var(--spacing-5);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  border-bottom: 1px solid var(--border-default);
  margin: var(--spacing-0);
}

.usage-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}

.usage-table th {
  padding: var(--spacing-3) var(--spacing-4);
  text-align: left;
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-default);
}

.usage-table td {
  padding: var(--spacing-3) var(--spacing-4);
  color: var(--text-primary);
  border-bottom: 1px solid var(--border-subtle);
}

.usage-table tr:last-child td { border-bottom: none; }

.usage-table tr:hover td { background: var(--bg-hover); }

.loading-row,
.empty-row {
  padding: var(--spacing-8);
  text-align: center;
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.text-warning {
  color: var(--color-warning, #f59e0b);
  font-weight: var(--font-medium);
}
</style>
