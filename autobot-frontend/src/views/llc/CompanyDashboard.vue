<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useApiClient } from '@/plugins/api'
import { useWebSocket } from '@/composables/useWebSocket'
import { getBackendUrl } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'
import { useRouter } from 'vue-router'
import { useLlcCompanyContext } from '@/composables/llc/useLlcCompanyContext'
import {
  agentStatusColor,
  runStatusToAgentStatus,
  runStatusToRunDisplayStatus,
} from '@/composables/llc/llcStatus'
import type { AgentDisplayStatus, RunDisplayStatus } from '@/composables/llc/llcStatus'

const logger = createLogger('CompanyDashboard')
const api = useApiClient()
const router = useRouter()
const { resolveCompanyId } = useLlcCompanyContext()

// Resolved at mount: the top-level /llc/dashboard nav entry carries no
// :companyId, so fall back to ?company= or the first company (#9861).
const companyId = ref<string>('')

interface AgentStatus {
  id: string
  name: string
  title: string
  status: AgentDisplayStatus
  adapter_type: string
  last_heartbeat: string | null
}

interface PendingApproval {
  id: string
  title: string
  requested_by: string
  created_at: string
  issue_id: string | null
}

interface BudgetInfo {
  spent: number
  total: number
  label: string
}

interface HeartbeatRun {
  agent_id: string
  agent_name: string
  run_id: string
  status: RunDisplayStatus
  started_at: string
  duration_ms: number | null
}

interface ActivityEvent {
  id: string
  type: string
  summary: string
  agent_name: string | null
  timestamp: string
}

// Raw backend shapes (differ from the display interfaces above) + mappers.
interface RawAgentRow {
  id: string
  name: string
  last_heartbeat_at: string | null
  last_run_status: string | null
}
interface RawBudgetRow {
  agent_id: string
  budget_limit: string | number
  budget_spent: string | number
}
interface RawRunRow {
  id: string
  agent_id: string
  status: string
  started_at: string | null
  finished_at: string | null
}

function mapAgent(r: RawAgentRow): AgentStatus {
  return {
    id: r.id,
    name: r.name,
    title: '',
    status: runStatusToAgentStatus(r.last_run_status),
    adapter_type: '',
    last_heartbeat: r.last_heartbeat_at,
  }
}
function mapBudget(r: RawBudgetRow): BudgetInfo {
  return {
    spent: Number(r.budget_spent) || 0,
    total: Number(r.budget_limit) || 0,
    label: r.agent_id,
  }
}
function mapRun(r: RawRunRow): HeartbeatRun {
  const duration =
    r.started_at && r.finished_at
      ? new Date(r.finished_at).getTime() - new Date(r.started_at).getTime()
      : null
  return {
    agent_id: r.agent_id,
    agent_name: r.agent_id,
    run_id: r.id,
    status: runStatusToRunDisplayStatus(r.status),
    started_at: r.started_at ?? '',
    duration_ms: duration,
  }
}

const agents = ref<AgentStatus[]>([])
const pendingApprovals = ref<PendingApproval[]>([])
const budgets = ref<BudgetInfo[]>([])
const heartbeatRuns = ref<HeartbeatRun[]>([])
const activityFeed = ref<ActivityEvent[]>([])
const isLoading = ref(false)
const error = ref<string | null>(null)

const wsUrl = computed(
  () => `${getBackendUrl().replace(/^http/, 'ws')}/api/llc/ws/activity/${companyId.value}`
)

const { lastMessage, connect, disconnect } = useWebSocket(wsUrl, {
  autoConnect: false,
  autoReconnect: true,
})

function handleWsMessage(raw: string) {
  try {
    const event = JSON.parse(raw) as ActivityEvent
    activityFeed.value = [event, ...activityFeed.value].slice(0, 50)
  } catch (err) {
    logger.warn('WS parse error', err)
  }
}

const budgetPercent = (b: BudgetInfo) =>
  b.total > 0 ? Math.min(100, Math.round((b.spent / b.total) * 100)) : 0

const budgetBarColor = (b: BudgetInfo) => {
  const pct = budgetPercent(b)
  if (pct >= 90) return 'bg-red-500'
  if (pct >= 70) return 'bg-yellow-400'
  return 'bg-green-500'
}

async function fetchDashboardData() {
  if (!companyId.value) return
  isLoading.value = true
  error.value = null
  try {
    // GH#9851/#9861: canonical LLC routes. The api client returns parsed JSON
    // directly (no {data:{...}} envelope); these endpoints return arrays
    // (agents/approvals/budget/runs) or an ActivityLogResponse ({items}). The
    // backend field shapes differ from this view's display interfaces, so map
    // them explicitly (#9861 — was rendering NaN budgets / unstyled statuses).
    const cid = companyId.value
    const [agentsResp, approvalsResp, budgetsResp, runsResp, activityResp] = await Promise.all([
      api.get<RawAgentRow[]>(`/api/llc/agents?company_id=${cid}`),
      api.get<PendingApproval[]>(`/api/llc/approvals?company_id=${cid}`),
      api.get<RawBudgetRow[]>(`/api/llc/budget?company_id=${cid}`),
      api.get<RawRunRow[]>('/api/llc/heartbeat-runs?limit=20'),
      api.get<{ items: ActivityEvent[] }>(`/api/llc/companies/${cid}/activity?page_size=50`),
    ])
    agents.value = (agentsResp ?? []).map(mapAgent)
    pendingApprovals.value = approvalsResp ?? []
    budgets.value = (budgetsResp ?? []).map(mapBudget)
    heartbeatRuns.value = (runsResp ?? []).map(mapRun)
    activityFeed.value = activityResp?.items ?? []
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    logger.error('Failed to fetch dashboard data:', msg)
    error.value = msg
  } finally {
    isLoading.value = false
  }
}

async function quickApprove(approvalId: string) {
  try {
    await api.post(`/api/llc/approvals/${approvalId}/decide`, { decision: 'approved' })
    pendingApprovals.value = pendingApprovals.value.filter(a => a.id !== approvalId)
  } catch (err: unknown) {
    logger.error('Quick approve failed', err)
  }
}

function launchCeoChat() {
  router.push({ path: '/chat', query: { mode: 'ceo' } })
}

function formatDuration(ms: number | null): string {
  if (ms === null) return '—'
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function formatTime(ts: string): string {
  if (!ts) return '—'
  return new Date(ts).toLocaleTimeString()
}

onMounted(async () => {
  await resolveCompanyId().then((id) => { companyId.value = id })
  if (!companyId.value) return
  await fetchDashboardData()
  connect()
})

onUnmounted(() => {
  disconnect()
})

watch(lastMessage, (msg) => {
  if (msg) handleWsMessage(msg as string)
})
</script>

<template>
  <div class="p-4 space-y-6 max-w-7xl mx-auto">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-bold text-autobot-text-primary">{{ $t('llc.dashboard.title') }}</h1>
      <button
        class="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors text-sm font-medium"
        @click="launchCeoChat"
      >
        {{ $t('llc.dashboard.ceoChat') }}
      </button>
    </div>

    <div v-if="!companyId" class="text-center py-12 text-autobot-text-muted">
      {{ $t('llc.dashboard.selectCompany') }}
    </div>

    <template v-else>
      <div v-if="error" class="rounded-lg bg-red-50 border border-red-200 p-4 text-red-700 text-sm">
        {{ error }}
        <button class="ml-4 underline" @click="fetchDashboardData">{{ $t('llc.dashboard.retry') }}</button>
      </div>

      <div v-if="isLoading" class="text-center py-12 text-autobot-text-muted">{{ $t('llc.dashboard.loading') }}</div>

      <template v-else>
        <!-- Pending Approvals -->
        <section v-if="pendingApprovals.length > 0">
          <div class="flex items-center gap-2 mb-3">
            <h2 class="text-lg font-semibold text-autobot-text-primary">{{ $t('llc.dashboard.pendingApprovals') }}</h2>
            <span class="bg-amber-100 text-amber-800 text-xs font-semibold px-2 py-0.5 rounded-full">
              {{ pendingApprovals.length }}
            </span>
          </div>
          <div class="space-y-2">
            <div
              v-for="approval in pendingApprovals"
              :key="approval.id"
              class="flex items-center justify-between bg-autobot-bg-card rounded-lg border border-autobot-border p-3"
            >
              <div>
                <p class="text-sm font-medium text-autobot-text-primary">{{ approval.title }}</p>
                <p class="text-xs text-autobot-text-muted">{{ $t('llc.dashboard.requestedBy', { name: approval.requested_by }) }} · {{ formatTime(approval.created_at) }}</p>
              </div>
              <button
                class="px-3 py-1.5 bg-green-600 text-white text-xs rounded hover:bg-green-700 transition-colors"
                @click="quickApprove(approval.id)"
              >
                {{ $t('llc.dashboard.approve') }}
              </button>
            </div>
          </div>
        </section>

        <!-- Budget Gauges -->
        <section>
          <h2 class="text-lg font-semibold text-autobot-text-primary mb-3">{{ $t('llc.dashboard.budget') }}</h2>
          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <div
              v-for="budget in budgets"
              :key="budget.label"
              class="bg-autobot-bg-card rounded-lg border border-autobot-border p-4"
            >
              <div class="flex justify-between items-center mb-2">
                <span class="text-sm font-medium text-autobot-text-secondary">{{ budget.label }}</span>
                <span class="text-xs text-autobot-text-muted">{{ budgetPercent(budget) }}%</span>
              </div>
              <div class="w-full bg-autobot-bg-tertiary rounded-full h-2">
                <div
                  class="h-2 rounded-full transition-all"
                  :class="budgetBarColor(budget)"
                  :style="{ width: `${budgetPercent(budget)}%` }"
                />
              </div>
              <p class="text-xs text-autobot-text-muted mt-1">{{ budget.spent }} / {{ budget.total }}</p>
            </div>
          </div>
        </section>

        <!-- Agent Status Grid -->
        <section>
          <h2 class="text-lg font-semibold text-autobot-text-primary mb-3">
            {{ $t('llc.dashboard.agents') }}
            <span class="text-sm font-normal text-autobot-text-muted ml-1">({{ agents.length }})</span>
          </h2>
          <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            <div
              v-for="agent in agents"
              :key="agent.id"
              class="bg-autobot-bg-card rounded-lg border border-autobot-border p-3 flex flex-col gap-1"
            >
              <div class="flex items-center gap-2">
                <span class="w-2.5 h-2.5 rounded-full flex-shrink-0" :class="agentStatusColor(agent.status)" />
                <span class="text-sm font-medium text-autobot-text-primary truncate">{{ agent.name }}</span>
              </div>
              <span class="text-xs text-autobot-text-muted truncate">{{ agent.title }}</span>
              <span class="text-xs bg-autobot-bg-tertiary text-autobot-text-secondary rounded px-1.5 py-0.5 self-start">
                {{ agent.adapter_type }}
              </span>
            </div>
          </div>
        </section>

        <!-- Live Heartbeat Runs -->
        <section>
          <h2 class="text-lg font-semibold text-autobot-text-primary mb-3">{{ $t('llc.dashboard.recentRuns') }}</h2>
          <div class="overflow-x-auto rounded-lg border border-autobot-border">
            <table class="min-w-full divide-y divide-autobot-border text-sm">
              <thead class="bg-autobot-bg-surface">
                <tr>
                  <th class="px-4 py-2 text-left text-xs font-semibold text-autobot-text-secondary uppercase tracking-wider">{{ $t('llc.dashboard.colAgent') }}</th>
                  <th class="px-4 py-2 text-left text-xs font-semibold text-autobot-text-secondary uppercase tracking-wider">{{ $t('llc.dashboard.colStatus') }}</th>
                  <th class="px-4 py-2 text-left text-xs font-semibold text-autobot-text-secondary uppercase tracking-wider">{{ $t('llc.dashboard.colStarted') }}</th>
                  <th class="px-4 py-2 text-left text-xs font-semibold text-autobot-text-secondary uppercase tracking-wider">{{ $t('llc.dashboard.colDuration') }}</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-autobot-border bg-autobot-bg-card">
                <tr v-for="run in heartbeatRuns" :key="run.run_id">
                  <td class="px-4 py-2 text-autobot-text-primary font-medium">{{ run.agent_name }}</td>
                  <td class="px-4 py-2">
                    <span
                      class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium"
                      :class="{
                        'bg-green-100 text-green-800': run.status === 'done',
                        'bg-blue-100 text-blue-800': run.status === 'running',
                        'bg-red-100 text-red-800': run.status === 'failed',
                      }"
                    >
                      {{ run.status }}
                    </span>
                  </td>
                  <td class="px-4 py-2 text-autobot-text-muted">{{ formatTime(run.started_at) }}</td>
                  <td class="px-4 py-2 text-autobot-text-muted">{{ formatDuration(run.duration_ms) }}</td>
                </tr>
                <tr v-if="heartbeatRuns.length === 0">
                  <td colspan="4" class="px-4 py-4 text-center text-autobot-text-muted text-sm">{{ $t('llc.dashboard.noRuns') }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- Activity Feed -->
        <section>
          <h2 class="text-lg font-semibold text-autobot-text-primary mb-3">{{ $t('llc.dashboard.liveActivity') }}</h2>
          <div class="bg-autobot-bg-card rounded-lg border border-autobot-border divide-y divide-autobot-border max-h-72 overflow-y-auto">
            <div
              v-for="event in activityFeed"
              :key="event.id"
              class="px-4 py-2 flex items-start gap-3"
            >
              <span class="text-xs text-autobot-text-muted w-16 flex-shrink-0 pt-0.5">{{ formatTime(event.timestamp) }}</span>
              <div class="flex-1 min-w-0">
                <span class="text-xs text-indigo-600 dark:text-indigo-400 font-medium mr-1">{{ event.agent_name ?? $t('llc.dashboard.system') }}</span>
                <span class="text-sm text-autobot-text-secondary">{{ event.summary }}</span>
              </div>
            </div>
            <div v-if="activityFeed.length === 0" class="px-4 py-4 text-center text-autobot-text-muted text-sm">
              {{ $t('llc.dashboard.waitingActivity') }}
            </div>
          </div>
        </section>
      </template>
    </template>
  </div>
</template>
