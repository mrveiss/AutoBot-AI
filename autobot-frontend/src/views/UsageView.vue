<template>
  <div class="usage-view">
    <div class="page-header">
      <div class="page-header-content">
        <h2 class="page-title">Usage &amp; Cost Tracking</h2>
        <p class="page-subtitle">Token usage, LLM costs, and billing-ready metrics</p>
      </div>
      <div class="header-actions">
        <button class="btn-action-secondary" :disabled="loading" @click="load">
          <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i>
          Refresh
        </button>
        <button class="btn-action-secondary" :disabled="csvLoading" @click="downloadCsv">
          <i class="fas fa-download" :class="{ 'fa-spin': csvLoading }"></i>
          Export CSV
        </button>
      </div>
    </div>

    <div v-if="error" class="error-banner">
      <i class="fas fa-exclamation-circle"></i>
      <span>{{ error }}</span>
      <button class="btn-dismiss" @click="error = null"><i class="fas fa-times"></i></button>
    </div>

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
      <div v-if="loading" class="loading-row">
        <i class="fas fa-spinner fa-spin"></i> Loading...
      </div>
      <table v-else-if="users.length" class="usage-table">
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getApiBase } from '@/config/ssot-config'
import { useApi } from '@/composables/useApi'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('UsageView')
const api = useApi()

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

const loading = ref(false)
const csvLoading = ref(false)
const error = ref<string | null>(null)
const summary = ref<UsageSummary | null>(null)
const users = ref<UserUsage[]>([])

async function load() {
  loading.value = true
  error.value = null
  try {
    const [sum, byUser] = await Promise.all([
      api.get<UsageSummary>('/usage/summary'),
      api.get<{ users: UserUsage[] }>('/usage/by-user'),
    ])
    summary.value = sum
    users.value = byUser.users ?? []
  } catch (e) {
    logger.error('Failed to load usage data:', e)
    error.value = 'Failed to load usage data. Check that you have admin access.'
  } finally {
    loading.value = false
  }
}

async function downloadCsv() {
  csvLoading.value = true
  try {
    const token = localStorage.getItem('authToken') || ''
    const res = await fetch(`${getApiBase()}/usage/export/csv`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'usage.csv'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    logger.error('CSV export failed:', e)
    error.value = 'CSV export failed. Check that you have admin access.'
  } finally {
    csvLoading.value = false
  }
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
  margin: 0;
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
</style>