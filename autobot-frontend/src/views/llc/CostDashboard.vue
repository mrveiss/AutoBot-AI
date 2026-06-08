<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="cost-dashboard">
    <div class="dash-header">
      <h2 class="view-title">Cost Dashboard</h2>
      <button class="btn-export" @click="exportCsv">Export CSV</button>
    </div>

    <div v-if="!companyId" class="state-msg">Select a company to view costs.</div>

    <template v-else>
    <!-- Summary cards -->
    <div class="summary-cards">
      <div class="summary-card">
        <div class="card-label">Total This Month</div>
        <div class="card-value">${{ totalThisMonth.toFixed(4) }}</div>
      </div>
      <div class="summary-card">
        <div class="card-label">By Company</div>
        <div class="card-value">${{ totalByCompany.toFixed(4) }}</div>
        <div class="card-sub">{{ companyId }}</div>
      </div>
      <div v-if="totalTokensThisMonth > 0" class="summary-card">
        <div class="card-label">Total Tokens This Month</div>
        <div class="card-value">{{ formatTokens(totalTokensThisMonth) }}</div>
        <div class="card-sub">{{ tokenModeAgents }} token-mode agents</div>
      </div>
      <div
        v-for="agent in topAgents"
        :key="agent.id"
        class="summary-card"
      >
        <div class="card-label">{{ agent.name }}</div>
        <div class="card-value">${{ agent.cost.toFixed(4) }}</div>
        <div class="card-sub">top agent</div>
      </div>
    </div>

    <!-- Budget health -->
    <div v-if="budgets.length > 0" class="budget-section">
      <h3 class="section-title">Budget Health</h3>
      <div class="budget-rows">
        <div v-for="b in budgets" :key="b.agent_id" class="budget-row">
          <span class="budget-agent">{{ b.agent_name ?? b.agent_id }}</span>
          <span class="mode-badge" :class="`mode-${b.budget_mode}`">
            {{ b.budget_mode === 'tokens' ? 'Tokens' : '$' }}
          </span>
          <div class="gauge-track">
            <div
              class="gauge-fill"
              :class="{ 'gauge-warn': budgetPct(b) >= 80, 'gauge-over': budgetPct(b) >= 100 }"
              :style="{ width: Math.min(budgetPct(b), 100) + '%' }"
            />
          </div>
          <span class="gauge-label" :class="{ 'text-warn': budgetPct(b) >= 80 }">
            {{ budgetPct(b).toFixed(0) }}%
            <span v-if="budgetPct(b) >= 80"> ⚠</span>
          </span>
          <span class="budget-amounts">
            <template v-if="b.budget_mode === 'tokens'">
              {{ formatTokens(b.tokens_spent) }} / {{ b.token_limit !== null ? formatTokens(b.token_limit) : '—' }}
              <span v-if="parseFloat(b.budget_spent) > 0" class="shadow-cost">
                (~${{ parseFloat(b.budget_spent).toFixed(2) }})
              </span>
            </template>
            <template v-else>
              ${{ parseFloat(b.budget_spent).toFixed(4) }} / ${{ parseFloat(b.budget_limit).toFixed(4) }}
            </template>
          </span>
          <button class="btn-settings" title="Edit budget settings" @click="openSettings(b)">⚙</button>
        </div>
      </div>
    </div>

    <!-- Budget settings modal -->
    <div v-if="settingsModal.visible" class="modal-overlay" @click.self="closeSettings">
      <div class="modal-box">
        <div class="modal-header">
          <h3 class="modal-title">Budget Settings</h3>
          <button class="btn-close" @click="closeSettings">✕</button>
        </div>
        <div class="modal-agent-name">{{ settingsModal.budget?.agent_name ?? settingsModal.budget?.agent_id }}</div>

        <div class="field-group">
          <label class="field-label">Budget Mode</label>
          <div class="mode-toggle">
            <button
              :class="{ active: settingsForm.budget_mode === 'dollars' }"
              @click="settingsForm.budget_mode = 'dollars'"
            >
              Dollar Limit
            </button>
            <button
              :class="{ active: settingsForm.budget_mode === 'tokens' }"
              @click="settingsForm.budget_mode = 'tokens'"
            >
              Token Limit
            </button>
          </div>
        </div>

        <div v-if="settingsForm.budget_mode === 'dollars'" class="field-group">
          <label class="field-label">Monthly Dollar Limit</label>
          <div class="input-prefix-wrap">
            <span class="input-prefix">$</span>
            <input
              v-model.number="settingsForm.budget_limit"
              type="number"
              step="1"
              min="0"
              class="field-input with-prefix"
            />
          </div>
        </div>

        <div v-else class="field-group">
          <label class="field-label">Monthly Token Limit</label>
          <input
            v-model.number="settingsForm.token_limit"
            type="number"
            step="100000"
            min="0"
            class="field-input"
            placeholder="e.g. 1000000"
          />
          <p class="field-hint">Recommended: 1M–5M for subscription plans, 100K for free tier</p>
        </div>

        <div class="field-group">
          <label class="field-label">Alert Threshold: {{ settingsForm.alert_threshold_pct }}%</label>
          <input
            v-model.number="settingsForm.alert_threshold_pct"
            type="range"
            min="0"
            max="100"
            step="5"
            class="field-range"
          />
        </div>

        <div v-if="settingsModal.error" class="modal-error">{{ settingsModal.error }}</div>

        <div class="modal-actions">
          <button class="btn-secondary" @click="closeSettings">Cancel</button>
          <button class="btn-primary" :disabled="settingsModal.saving" @click="saveBudgetSettings">
            {{ settingsModal.saving ? 'Saving…' : 'Save' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Bar chart: daily spend -->
    <div class="chart-section">
      <h3 class="section-title">Daily Spend – Last 30 Days</h3>
      <div v-if="dailyBars.length === 0" class="state-msg">No spend data available.</div>
      <div v-else class="bar-chart">
        <div
          v-for="bar in dailyBars"
          :key="bar.date"
          class="bar-col"
          :title="`${bar.date}: $${bar.amount.toFixed(4)}`"
        >
          <div class="bar-fill" :style="{ height: bar.heightPct + '%' }" />
          <div class="bar-label">{{ bar.shortDate }}</div>
        </div>
      </div>
    </div>

    <!-- Filters -->
    <div class="table-filters">
      <select v-model="filters.agent" class="filter-select">
        <option value="">All Agents</option>
        <option v-for="a in agentOptions" :key="a" :value="a">{{ a }}</option>
      </select>
      <input v-model="filters.dateFrom" type="date" class="filter-date" />
      <span class="date-sep">to</span>
      <input v-model="filters.dateTo" type="date" class="filter-date" />
    </div>

    <!-- Cost events table -->
    <div class="table-wrapper">
      <div v-if="costEventsUnavailable" class="state-msg">
        Cost events endpoint not available (404).
      </div>
      <table v-else class="cost-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Agent</th>
            <th>Work Item</th>
            <th>Model</th>
            <th>Provider</th>
            <th>Input Tokens</th>
            <th>Output Tokens</th>
            <th>Cost</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="isLoading">
            <td colspan="8" class="state-msg">Loading...</td>
          </tr>
          <tr v-else-if="filteredEvents.length === 0">
            <td colspan="8" class="state-msg">No cost events match filters.</td>
          </tr>
          <tr v-for="ev in filteredEvents" :key="ev.id">
            <td>{{ formatDate(ev.created_at) }}</td>
            <td>{{ ev.agent_id }}</td>
            <td>{{ ev.work_item_id ?? '—' }}</td>
            <td>{{ ev.model }}</td>
            <td>{{ ev.provider }}</td>
            <td class="num-cell">{{ ev.input_tokens.toLocaleString() }}</td>
            <td class="num-cell">{{ ev.output_tokens.toLocaleString() }}</td>
            <td class="num-cell">${{ ev.cost.toFixed(6) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('CostDashboard')
const api = useApiClient()
const route = useRoute()

const props = defineProps<{ companyId?: string }>()
const companyId = computed(() => (route.params.companyId as string) ?? props.companyId ?? '')

interface BudgetEntry {
  agent_id: string
  agent_name?: string
  budget_mode: 'dollars' | 'tokens'
  budget_limit: string
  budget_spent: string
  token_limit: number | null
  tokens_spent: number
  remaining: string
  is_over_limit: boolean
  alert_triggered: boolean
  alert_threshold: number
}

interface CostEvent {
  id: string
  agent_id: string
  work_item_id?: string
  model: string
  provider: string
  input_tokens: number
  output_tokens: number
  cost: number
  created_at: string
}

const budgets = ref<BudgetEntry[]>([])
const costEvents = ref<CostEvent[]>([])
const isLoading = ref(false)
const costEventsUnavailable = ref(false)
const filters = ref({ agent: '', dateFrom: '', dateTo: '' })

const settingsModal = reactive({
  visible: false,
  budget: null as BudgetEntry | null,
  saving: false,
  error: '',
})

const settingsForm = reactive({
  budget_mode: 'dollars' as 'dollars' | 'tokens',
  budget_limit: 0,
  token_limit: 0,
  alert_threshold_pct: 80,
})

function budgetPct(b: BudgetEntry): number {
  if (b.budget_mode === 'tokens' && b.token_limit) {
    return (b.tokens_spent / b.token_limit) * 100
  }
  const limit = parseFloat(b.budget_limit)
  const spent = parseFloat(b.budget_spent)
  return limit > 0 ? (spent / limit) * 100 : 0
}

function formatTokens(n: number | null): string {
  if (n === null) return '—'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toLocaleString()
}

const totalTokensThisMonth = computed(() =>
  budgets.value.reduce((s, b) => s + b.tokens_spent, 0)
)

const tokenModeAgents = computed(() =>
  budgets.value.filter(b => b.budget_mode === 'tokens').length
)

const totalThisMonth = computed(() => {
  const now = new Date()
  return costEvents.value
    .filter(ev => {
      const d = new Date(ev.created_at)
      return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear()
    })
    .reduce((s, ev) => s + ev.cost, 0)
})

const totalByCompany = computed(() => costEvents.value.reduce((s, ev) => s + ev.cost, 0))

const agentTotals = computed(() => {
  const map: Record<string, number> = {}
  for (const ev of costEvents.value) {
    map[ev.agent_id] = (map[ev.agent_id] ?? 0) + ev.cost
  }
  return map
})

const topAgents = computed(() =>
  Object.entries(agentTotals.value)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([id, cost]) => ({ id, name: id, cost }))
)

const agentOptions = computed(() => [...new Set(costEvents.value.map(ev => ev.agent_id))])

const filteredEvents = computed(() => {
  return costEvents.value.filter(ev => {
    if (filters.value.agent && ev.agent_id !== filters.value.agent) return false
    if (filters.value.dateFrom && ev.created_at < filters.value.dateFrom) return false
    if (filters.value.dateTo && ev.created_at > filters.value.dateTo + 'T23:59:59') return false
    return true
  })
})

const dailyBars = computed(() => {
  const map: Record<string, number> = {}
  const now = new Date()
  for (let i = 29; i >= 0; i--) {
    const d = new Date(now)
    d.setDate(d.getDate() - i)
    const key = d.toISOString().slice(0, 10)
    map[key] = 0
  }
  for (const ev of costEvents.value) {
    const key = ev.created_at.slice(0, 10)
    if (key in map) map[key] += ev.cost
  }
  const entries = Object.entries(map)
  const max = Math.max(...entries.map(([, v]) => v), 0.0001)
  return entries.map(([date, amount]) => ({
    date,
    amount,
    shortDate: date.slice(5),
    heightPct: (amount / max) * 100,
  }))
})

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString()
}

function exportCsv() {
  const rows = [
    ['Date', 'Agent', 'Work Item', 'Model', 'Provider', 'Input Tokens', 'Output Tokens', 'Cost'],
    ...filteredEvents.value.map(ev => [
      formatDate(ev.created_at),
      ev.agent_id,
      ev.work_item_id ?? '',
      ev.model,
      ev.provider,
      String(ev.input_tokens),
      String(ev.output_tokens),
      ev.cost.toFixed(6),
    ]),
  ]
  const csv = rows.map(r => r.map(c => `"${c.replace(/"/g, '""')}"`).join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `cost-events-${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

function openSettings(b: BudgetEntry) {
  settingsModal.budget = b
  settingsModal.error = ''
  settingsForm.budget_mode = b.budget_mode
  settingsForm.budget_limit = parseFloat(b.budget_limit)
  settingsForm.token_limit = b.token_limit ?? 0
  settingsForm.alert_threshold_pct = Math.round(b.alert_threshold * 100)
  settingsModal.visible = true
}

function closeSettings() {
  settingsModal.visible = false
  settingsModal.budget = null
  settingsModal.error = ''
}

async function saveBudgetSettings() {
  if (!settingsModal.budget) return
  settingsModal.saving = true
  settingsModal.error = ''
  try {
    const body: Record<string, unknown> = {
      budget_mode: settingsForm.budget_mode,
      alert_threshold: settingsForm.alert_threshold_pct / 100,
    }
    if (settingsForm.budget_mode === 'dollars') {
      body.budget_limit = settingsForm.budget_limit.toFixed(2)
    } else {
      body.token_limit = settingsForm.token_limit
    }
    await api.patch(`/api/llc/budget/${settingsModal.budget.agent_id}/limit`, body)
    closeSettings()
    await fetchBudgets()
  } catch (err: unknown) {
    settingsModal.error = (err as { message?: string })?.message ?? 'Save failed'
    logger.error('Budget settings save failed', err)
  } finally {
    settingsModal.saving = false
  }
}

async function fetchBudgets() {
  if (!companyId.value) return
  try {
    const data = await api.get<BudgetEntry[] | { items: BudgetEntry[] }>(`/api/llc/budget?company_id=${companyId.value}`)
    budgets.value = Array.isArray(data) ? data : (data as { items: BudgetEntry[] }).items ?? []
  } catch (err) {
    logger.warn('Budget fetch failed', err)
  }
}

async function fetchCostEvents() {
  if (!companyId.value) return
  isLoading.value = true
  try {
    const data = await api.get<CostEvent[] | { items: CostEvent[] }>(`/api/llc/cost-events?company_id=${companyId.value}`)
    costEvents.value = Array.isArray(data) ? data : (data as { items: CostEvent[] }).items ?? []
    costEventsUnavailable.value = false
  } catch (err: unknown) {
    const status = (err as { status?: number })?.status
    if (status === 404) {
      costEventsUnavailable.value = true
    } else {
      logger.error('Cost events fetch failed', err)
    }
  } finally {
    isLoading.value = false
  }
}

onMounted(async () => {
  if (!companyId.value) return
  await Promise.all([fetchBudgets(), fetchCostEvents()])
})
</script>

<style scoped>
.cost-dashboard {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 1.5rem;
  gap: 1.25rem;
  background: var(--color-background);
  color: var(--color-text);
  overflow-y: auto;
}

.dash-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.view-title {
  font-size: 1.5rem;
  font-weight: 600;
  margin: 0;
}

.btn-export {
  padding: 0.4rem 1rem;
  background: var(--color-surface, #fff);
  color: var(--color-text);
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: 0.375rem;
  font-size: 0.875rem;
  cursor: pointer;
}

.summary-cards {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
}

.summary-card {
  flex: 1;
  min-width: 160px;
  padding: 1rem;
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.card-label {
  font-size: 0.8rem;
  color: var(--color-text-secondary, #6b7280);
  font-weight: 500;
}

.card-value {
  font-size: 1.375rem;
  font-weight: 700;
}

.card-sub {
  font-size: 0.75rem;
  color: var(--color-text-secondary, #9ca3af);
  word-break: break-all;
}

.section-title {
  font-size: 1rem;
  font-weight: 600;
  margin: 0 0 0.75rem;
}

.budget-section,
.chart-section {
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 0.5rem;
  padding: 1rem;
}

.budget-rows {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.budget-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.875rem;
}

.budget-agent {
  min-width: 9rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mode-badge {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 0.15rem 0.45rem;
  border-radius: 9999px;
  white-space: nowrap;
}

.mode-dollars {
  background: #dbeafe;
  color: #1d4ed8;
}

.mode-tokens {
  background: #fef3c7;
  color: #92400e;
}

.gauge-track {
  flex: 1;
  height: 0.5rem;
  background: var(--color-surface-elevated, #f3f4f6);
  border-radius: 9999px;
  overflow: hidden;
}

.gauge-fill {
  height: 100%;
  background: #10b981;
  border-radius: 9999px;
  transition: width 0.3s;
}

.gauge-warn { background: #f59e0b; }
.gauge-over { background: #ef4444; }

.gauge-label {
  min-width: 3.5rem;
  text-align: right;
  font-size: 0.8rem;
}

.text-warn { color: #f59e0b; font-weight: 600; }

.budget-amounts {
  min-width: 12rem;
  text-align: right;
  font-size: 0.8rem;
  color: var(--color-text-secondary, #6b7280);
}

.shadow-cost {
  color: var(--color-text-secondary, #9ca3af);
  font-size: 0.75rem;
  margin-left: 0.25rem;
}

.btn-settings {
  padding: 0.2rem 0.45rem;
  background: transparent;
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: 0.25rem;
  cursor: pointer;
  font-size: 0.85rem;
  color: var(--color-text-secondary, #6b7280);
  opacity: 0.6;
  transition: opacity 0.15s;
}

.btn-settings:hover { opacity: 1; }

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.modal-box {
  background: var(--color-surface, #fff);
  border-radius: 0.75rem;
  padding: 1.5rem;
  width: 100%;
  max-width: 26rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.modal-title {
  font-size: 1.1rem;
  font-weight: 600;
  margin: 0;
}

.btn-close {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 1rem;
  color: var(--color-text-secondary, #6b7280);
  padding: 0.2rem;
}

.modal-agent-name {
  font-size: 0.85rem;
  color: var(--color-text-secondary, #6b7280);
  margin-top: -0.5rem;
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.field-label {
  font-size: 0.85rem;
  font-weight: 500;
}

.mode-toggle {
  display: flex;
  gap: 0;
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: 0.375rem;
  overflow: hidden;
}

.mode-toggle button {
  flex: 1;
  padding: 0.45rem 0.75rem;
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 0.875rem;
  color: var(--color-text-secondary, #6b7280);
  transition: background 0.15s, color 0.15s;
}

.mode-toggle button.active {
  background: var(--color-primary, #3b82f6);
  color: #fff;
}

.input-prefix-wrap {
  display: flex;
  align-items: center;
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: 0.375rem;
  overflow: hidden;
}

.input-prefix {
  padding: 0.45rem 0.6rem;
  background: var(--color-surface-elevated, #f9fafb);
  border-right: 1px solid var(--color-border, #d1d5db);
  font-size: 0.875rem;
  color: var(--color-text-secondary, #6b7280);
}

.field-input {
  padding: 0.45rem 0.75rem;
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: 0.375rem;
  background: var(--color-surface, #fff);
  color: var(--color-text);
  font-size: 0.875rem;
  width: 100%;
}

.field-input.with-prefix {
  border: none;
  flex: 1;
}

.field-hint {
  font-size: 0.75rem;
  color: var(--color-text-secondary, #9ca3af);
  margin: 0;
}

.field-range {
  width: 100%;
  cursor: pointer;
}

.modal-error {
  font-size: 0.825rem;
  color: #ef4444;
  padding: 0.5rem 0.75rem;
  background: #fef2f2;
  border-radius: 0.375rem;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 0.25rem;
}

.btn-primary {
  padding: 0.45rem 1.25rem;
  background: var(--color-primary, #3b82f6);
  color: #fff;
  border: none;
  border-radius: 0.375rem;
  font-size: 0.875rem;
  cursor: pointer;
  font-weight: 500;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  padding: 0.45rem 1rem;
  background: transparent;
  color: var(--color-text);
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: 0.375rem;
  font-size: 0.875rem;
  cursor: pointer;
}

.bar-chart {
  display: flex;
  align-items: flex-end;
  gap: 0.125rem;
  height: 120px;
  padding-bottom: 1.25rem;
  position: relative;
}

.bar-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  height: 100%;
  gap: 0.2rem;
  cursor: default;
}

.bar-fill {
  width: 100%;
  background: var(--color-primary, #3b82f6);
  border-radius: 0.125rem 0.125rem 0 0;
  min-height: 2px;
  transition: height 0.3s;
}

.bar-label {
  font-size: 0.6rem;
  color: var(--color-text-secondary, #9ca3af);
  transform: rotate(-45deg);
  transform-origin: center;
  white-space: nowrap;
}

.table-filters {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.filter-select,
.filter-date {
  padding: 0.4rem 0.75rem;
  border: 1px solid var(--color-border, #d1d5db);
  border-radius: 0.375rem;
  background: var(--color-surface, #fff);
  color: var(--color-text);
  font-size: 0.875rem;
}

.date-sep {
  font-size: 0.875rem;
  color: var(--color-text-secondary, #6b7280);
}

.table-wrapper {
  overflow: auto;
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 0.5rem;
}

.cost-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.cost-table th {
  padding: 0.625rem 0.75rem;
  text-align: left;
  font-weight: 600;
  background: var(--color-surface-elevated, #f9fafb);
  border-bottom: 1px solid var(--color-border, #e5e7eb);
  white-space: nowrap;
}

.cost-table td {
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--color-border, #f3f4f6);
}

.num-cell {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.state-msg {
  text-align: center;
  padding: 2rem;
  color: var(--color-text-secondary, #9ca3af);
}
</style>
