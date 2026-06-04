<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="cost-dashboard">
    <div class="dash-header">
      <h2 class="view-title">Cost Dashboard</h2>
      <button class="btn-export" @click="exportCsv">Export CSV</button>
    </div>

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
          <div class="gauge-track">
            <div
              class="gauge-fill"
              :class="{ 'gauge-warn': b.pct >= 80, 'gauge-over': b.pct >= 100 }"
              :style="{ width: Math.min(b.pct, 100) + '%' }"
            />
          </div>
          <span class="gauge-label" :class="{ 'text-warn': b.pct >= 80 }">
            {{ b.pct.toFixed(0) }}%
            <span v-if="b.pct >= 80"> ⚠</span>
          </span>
          <span class="budget-amounts">${{ b.spent.toFixed(4) }} / ${{ b.budget.toFixed(4) }}</span>
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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('CostDashboard')
const api = useApiClient()

const props = defineProps<{ companyId?: string }>()
const companyId = computed(() => props.companyId ?? '00000000-0000-0000-0000-000000000000')

interface BudgetEntry {
  agent_id: string
  agent_name?: string
  budget: number
  spent: number
  pct: number
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

async function fetchBudgets() {
  try {
    const data = await api.get<BudgetEntry[] | { items: BudgetEntry[] }>(`/api/llc/budget?company_id=${companyId.value}`)
    const raw = Array.isArray(data) ? data : (data as { items: BudgetEntry[] }).items ?? []
    budgets.value = raw.map(b => ({
      ...b,
      pct: b.budget > 0 ? (b.spent / b.budget) * 100 : 0,
    }))
  } catch (err) {
    logger.warn('Budget fetch failed', err)
  }
}

async function fetchCostEvents() {
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
  min-width: 10rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  min-width: 10rem;
  text-align: right;
  font-size: 0.8rem;
  color: var(--color-text-secondary, #6b7280);
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
