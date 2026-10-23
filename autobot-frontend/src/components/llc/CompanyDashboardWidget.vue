<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0
-->
<script setup lang="ts">
/**
 * One Company OS dashboard widget, chosen by `type` (#18242). The grid frame around it
 * (DashboardGrid) fixes the height, so the heading stays put and the body scrolls.
 * Colours come from the design tokens and kit variants, never the raw palette (#14580).
 */
import { BaseBadge, BaseButton, type BadgeVariant } from '@autobot/ui'
import { agentStatusColor, type RunDisplayStatus } from '@/composables/llc/llcStatus'
import type { CompanyWidgetType } from '@/composables/dashboard/companyOsDashboard'
import type { BudgetInfo, CompanyDashboardData } from '@/views/llc/companyDashboardTypes'

defineProps<{ type: CompanyWidgetType; data: CompanyDashboardData }>()
const emit = defineEmits<{ approve: [approvalId: string] }>()

const RUN_VARIANT: Record<RunDisplayStatus, BadgeVariant> = { done: 'success', running: 'info', failed: 'error' }
const RUN_LABEL_KEY: Record<RunDisplayStatus, string> = {
  done: 'llc.dashboard.runStatus.done',
  running: 'llc.dashboard.runStatus.running',
  failed: 'llc.dashboard.runStatus.failed',
}

const budgetPercent = (b: BudgetInfo) =>
  b.total > 0 ? Math.min(100, Math.round((b.spent / b.total) * 100)) : 0

function budgetBarColor(b: BudgetInfo): string {
  const pct = budgetPercent(b)
  if (pct >= 90) return 'bg-autobot-error'
  if (pct >= 70) return 'bg-autobot-warning'
  return 'bg-autobot-success'
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
</script>

<template>
  <div class="flex h-full flex-col gap-3 p-3">
    <template v-if="type === 'company-approvals'">
      <div class="flex items-center gap-2">
        <h2 class="text-lg font-semibold text-autobot-text-primary">{{ $t('llc.dashboard.pendingApprovals') }}</h2>
        <BaseBadge size="sm" variant="warning">{{ data.approvals.length }}</BaseBadge>
      </div>
      <div class="min-h-0 flex-1 space-y-2 overflow-y-auto">
        <div
          v-for="approval in data.approvals"
          :key="approval.id"
          class="flex items-center justify-between rounded-lg border border-autobot-border bg-autobot-bg-card p-3"
        >
          <div>
            <p class="text-sm font-medium text-autobot-text-primary">{{ approval.title }}</p>
            <p class="text-xs text-autobot-text-muted">{{ $t('llc.dashboard.requestedBy', { name: approval.requested_by }) }} · {{ formatTime(approval.created_at) }}</p>
          </div>
          <BaseButton size="sm" variant="primary" @click="emit('approve', approval.id)">
            {{ $t('llc.dashboard.approve') }}
          </BaseButton>
        </div>
        <p v-if="data.approvals.length === 0" class="py-4 text-center text-sm text-autobot-text-muted">
          {{ $t('llc.dashboard.noApprovals') }}
        </p>
      </div>
    </template>

    <template v-else-if="type === 'company-budget'">
      <h2 class="text-lg font-semibold text-autobot-text-primary">{{ $t('llc.dashboard.budget') }}</h2>
      <div class="grid min-h-0 flex-1 auto-rows-min grid-cols-1 gap-4 overflow-y-auto sm:grid-cols-2 lg:grid-cols-3">
        <div v-for="budget in data.budgets" :key="budget.label" class="rounded-lg border border-autobot-border bg-autobot-bg-card p-4">
          <div class="mb-2 flex items-center justify-between">
            <span class="text-sm font-medium text-autobot-text-secondary">{{ budget.label }}</span>
            <span class="text-xs text-autobot-text-muted">{{ budgetPercent(budget) }}%</span>
          </div>
          <div class="h-2 w-full rounded-full bg-autobot-bg-tertiary">
            <div class="h-2 rounded-full transition-all" :class="budgetBarColor(budget)" :style="{ width: `${budgetPercent(budget)}%` }" />
          </div>
          <p class="mt-1 text-xs text-autobot-text-muted">{{ budget.spent }} / {{ budget.total }}</p>
        </div>
      </div>
    </template>

    <template v-else-if="type === 'company-agents'">
      <h2 class="text-lg font-semibold text-autobot-text-primary">
        {{ $t('llc.dashboard.agents') }}
        <span class="ml-1 text-sm font-normal text-autobot-text-muted">({{ data.agents.length }})</span>
      </h2>
      <div class="grid min-h-0 flex-1 auto-rows-min grid-cols-2 gap-3 overflow-y-auto sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        <div v-for="agent in data.agents" :key="agent.id" class="flex flex-col gap-1 rounded-lg border border-autobot-border bg-autobot-bg-card p-3">
          <div class="flex items-center gap-2">
            <span class="h-2.5 w-2.5 flex-shrink-0 rounded-full" :class="agentStatusColor(agent.status)" />
            <span class="truncate text-sm font-medium text-autobot-text-primary">{{ agent.name }}</span>
          </div>
          <span class="truncate text-xs text-autobot-text-muted">{{ agent.title }}</span>
          <span class="self-start rounded bg-autobot-bg-tertiary px-1.5 py-0.5 text-xs text-autobot-text-secondary">{{ agent.adapter_type }}</span>
        </div>
      </div>
    </template>

    <template v-else-if="type === 'company-runs'">
      <h2 class="text-lg font-semibold text-autobot-text-primary">{{ $t('llc.dashboard.recentRuns') }}</h2>
      <div class="min-h-0 flex-1 overflow-auto rounded-lg border border-autobot-border">
        <table class="min-w-full divide-y divide-autobot-border text-sm">
          <thead class="bg-autobot-bg-surface">
            <tr>
              <th class="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wider text-autobot-text-secondary">{{ $t('llc.dashboard.colAgent') }}</th>
              <th class="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wider text-autobot-text-secondary">{{ $t('llc.dashboard.colStatus') }}</th>
              <th class="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wider text-autobot-text-secondary">{{ $t('llc.dashboard.colStarted') }}</th>
              <th class="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wider text-autobot-text-secondary">{{ $t('llc.dashboard.colDuration') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-autobot-border bg-autobot-bg-card">
            <tr v-for="run in data.runs" :key="run.run_id">
              <td class="px-4 py-2 font-medium text-autobot-text-primary">{{ run.agent_name }}</td>
              <td class="px-4 py-2"><BaseBadge size="sm" :rounded="false" :variant="RUN_VARIANT[run.status]">{{ $t(RUN_LABEL_KEY[run.status]) }}</BaseBadge></td>
              <td class="px-4 py-2 text-autobot-text-muted">{{ formatTime(run.started_at) }}</td>
              <td class="px-4 py-2 text-autobot-text-muted">{{ formatDuration(run.duration_ms) }}</td>
            </tr>
            <tr v-if="data.runs.length === 0">
              <td colspan="4" class="px-4 py-4 text-center text-sm text-autobot-text-muted">{{ $t('llc.dashboard.noRuns') }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <template v-else-if="type === 'company-activity'">
      <h2 class="text-lg font-semibold text-autobot-text-primary">{{ $t('llc.dashboard.liveActivity') }}</h2>
      <div class="min-h-0 flex-1 divide-y divide-autobot-border overflow-y-auto rounded-lg border border-autobot-border bg-autobot-bg-card">
        <div v-for="event in data.activity" :key="event.id" class="flex items-start gap-3 px-4 py-2">
          <span class="w-16 flex-shrink-0 pt-0.5 text-xs text-autobot-text-muted">{{ formatTime(event.timestamp) }}</span>
          <div class="min-w-0 flex-1">
            <span class="mr-1 text-xs font-medium text-autobot-primary">{{ event.agent_name ?? $t('llc.dashboard.system') }}</span>
            <span class="text-sm text-autobot-text-secondary">{{ event.summary }}</span>
          </div>
        </div>
        <div v-if="data.activity.length === 0" class="px-4 py-4 text-center text-sm text-autobot-text-muted">
          {{ $t('llc.dashboard.waitingActivity') }}
        </div>
      </div>
    </template>
  </div>
</template>
