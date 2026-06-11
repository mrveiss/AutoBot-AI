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
      <h1 class="text-2xl font-bold text-gray-900 dark:text-gray-100">Company Dashboard</h1>
      <button
        class="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors text-sm font-medium"
        @click="launchCeoChat"
      >
        CEO Chat
      </button>
    </div>

    <div v-if="!companyId" class="text-center py-12 text-gray-500">
      Select a company to view its dashboard.
    </div>

    <template v-else>
      <div v-if="error" class="rounded-lg bg-red-50 border border-red-200 p-4 text-red-700 text-sm">
        {{ error }}
        <button class="ml-4 underline" @click="fetchDashboardData">Retry</button>
      </div>

      <div v-if="isLoading" class="text-center py-12 text-gray-500">Loading…</div>

      <template v-else>
        <!-- Pending Approvals -->
        <section v-if="pendingApprovals.length > 0">
          <div class="flex items-center gap-2 mb-3">
            <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-200">Pending Approvals</h2>
            <span class="bg-amber-100 text-amber-800 text-xs font-semibold px-2 py-0.5 rounded-full">
              {{ pendingApprovals.length }}
            </span>
          </div>
          <div class="space-y-2">
            <div
              v-for="approval in pendingApprovals"
              :key="approval.id"
              class="flex items-center justify-between bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3"
            >
              <div>
                <p class="text-sm font-medium text-gray-900 dark:text-gray-100">{{ approval.title }}</p>
                <p class="text-xs text-gray-500">Requested by {{ approval.requested_by }} · {{ formatTime(approval.created_at) }}</p>
              </div>
              <button
                class="px-3 py-1.5 bg-green-600 text-white text-xs rounded hover:bg-green-700 transition-colors"
                @click="quickApprove(approval.id)"
              >
                Approve
              </button>
            </div>
          </div>
        </section>

        <!-- Budget Gauges -->
        <section>
          <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">Budget</h2>
          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <div
              v-for="budget in budgets"
              :key="budget.label"
              class="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4"
            >
              <div class="flex justify-between items-center mb-2">
                <span class="text-sm font-medium text-gray-700 dark:text-gray-300">{{ budget.label }}</span>
                <span class="text-xs text-gray-500">{{ budgetPercent(budget) }}%</span>
              </div>
              <div class="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                <div
                  class="h-2 rounded-full transition-all"
                  :class="budgetBarColor(budget)"
                  :style="{ width: `${budgetPercent(budget)}%` }"
                />
              </div>
              <p class="text-xs text-gray-500 mt-1">{{ budget.spent }} / {{ budget.total }}</p>
            </div>
          </div>
        </section>

        <!-- Agent Status Grid -->
        <section>
          <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">
            Agents
            <span class="text-sm font-normal text-gray-500 ml-1">({{ agents.length }})</span>
          </h2>
          <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            <div
              v-for="agent in agents"
              :key="agent.id"
              class="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3 flex flex-col gap-1"
            >
              <div class="flex items-center gap-2">
                <span class="w-2.5 h-2.5 rounded-full flex-shrink-0" :class="agentStatusColor(agent.status)" />
                <span class="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{{ agent.name }}</span>
              </div>
              <span class="text-xs text-gray-500 truncate">{{ agent.title }}</span>
              <span class="text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded px-1.5 py-0.5 self-start">
                {{ agent.adapter_type }}
              </span>
            </div>
          </div>
        </section>

        <!-- Live Heartbeat Runs -->
        <section>
          <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">Recent Heartbeat Runs</h2>
          <div class="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
            <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700 text-sm">
              <thead class="bg-gray-50 dark:bg-gray-900">
                <tr>
                  <th class="px-4 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">Agent</th>
                  <th class="px-4 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">Status</th>
                  <th class="px-4 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">Started</th>
                  <th class="px-4 py-2 text-left text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wider">Duration</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100 dark:divide-gray-800 bg-white dark:bg-gray-800">
                <tr v-for="run in heartbeatRuns" :key="run.run_id">
                  <td class="px-4 py-2 text-gray-900 dark:text-gray-100 font-medium">{{ run.agent_name }}</td>
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
                  <td class="px-4 py-2 text-gray-500">{{ formatTime(run.started_at) }}</td>
                  <td class="px-4 py-2 text-gray-500">{{ formatDuration(run.duration_ms) }}</td>
                </tr>
                <tr v-if="heartbeatRuns.length === 0">
                  <td colspan="4" class="px-4 py-4 text-center text-gray-400 text-sm">No runs yet</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- Activity Feed -->
        <section>
          <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-3">Live Activity</h2>
          <div class="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 divide-y divide-gray-100 dark:divide-gray-700 max-h-72 overflow-y-auto">
            <div
              v-for="event in activityFeed"
              :key="event.id"
              class="px-4 py-2 flex items-start gap-3"
            >
              <span class="text-xs text-gray-400 w-16 flex-shrink-0 pt-0.5">{{ formatTime(event.timestamp) }}</span>
              <div class="flex-1 min-w-0">
                <span class="text-xs text-indigo-600 dark:text-indigo-400 font-medium mr-1">{{ event.agent_name ?? 'system' }}</span>
                <span class="text-sm text-gray-700 dark:text-gray-300">{{ event.summary }}</span>
              </div>
            </div>
            <div v-if="activityFeed.length === 0" class="px-4 py-4 text-center text-gray-400 text-sm">
              Waiting for activity…
            </div>
          </div>
        </section>
      </template>
    </template>
  </div>
</template>
