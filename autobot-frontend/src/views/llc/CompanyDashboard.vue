<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseButton } from '@autobot/ui'
import { useApiClient } from '@/plugins/api'
import { useLiveEvents } from '@/composables/useLiveEvents'
import { createLogger } from '@/utils/debugUtils'
import { useRouter } from 'vue-router'
import { useLlcCompanyContext } from '@/composables/llc/useLlcCompanyContext'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import DashboardGrid from '@/components/dashboard/DashboardGrid.vue'
import CompanyDashboardWidget from '@/components/llc/CompanyDashboardWidget.vue'
import { useDashboardLayout } from '@/composables/dashboard/useDashboardLayout'
import { displayText, type DashboardWidget } from '@/composables/dashboard/dashboardLayoutModel'
import {
  companyWidgetsOf,
  defaultCompanyOsLayout,
  withCompanyWidgets,
  type CompanyWidget,
} from '@/composables/dashboard/companyOsDashboard'
import {
  mapActivityRow,
  mapAgent,
  mapBudget,
  mapRun,
  type CompanyDashboardData,
  type PendingApproval,
  type RawAgentRow,
  type RawBudgetRow,
  type RawRunRow,
} from './companyDashboardTypes'

const logger = createLogger('CompanyDashboard')
const api = useApiClient()
const router = useRouter()
const live = useLiveEvents()
const { t } = useI18n()
const { confirm } = useConfirmDialog()
const { resolveCompanyId } = useLlcCompanyContext()

// Resolved at mount: the top-level /llc/dashboard nav entry carries no
// :companyId, so fall back to ?company= or the first company (#9861).
const companyId = ref<string>('')

const data = ref<CompanyDashboardData>({ agents: [], approvals: [], budgets: [], runs: [], activity: [] })
const isLoading = ref(false)
const error = ref<string | null>(null)

// Layout: per user, shared by every company (#18242). The grid edits `widgets`; Save writes it.
const { layout, loaded, loadError, saveError, load, save, reset } = useDashboardLayout('company-os', defaultCompanyOsLayout)
const widgets = ref<CompanyWidget[]>(companyWidgetsOf(layout.value))
const editing = ref(false)
const dirty = ref(false)
const resetError = ref(false)
const labelOf = (w: DashboardWidget) => displayText(w.title, t)

// Live activity via the canonical /ws/live event bus (channel company:{id}).
function pushActivity(p: Record<string, unknown>) {
  data.value.activity = [mapActivityRow(p), ...data.value.activity].slice(0, 50)
}

async function fetchDashboardData() {
  if (!companyId.value) return
  isLoading.value = true
  error.value = null
  try {
    // GH#9851/#9861: canonical LLC routes. The api client returns parsed JSON
    // directly (no {data:{...}} envelope); these endpoints return arrays
    // (agents/approvals/budget/runs) or an ActivityLogResponse ({items}). The
    // backend field shapes differ from the display interfaces, so map them
    // explicitly (#9861 — was rendering NaN budgets / unstyled statuses).
    const cid = companyId.value
    const [agentsResp, approvalsResp, budgetsResp, runsResp, activityResp] = await Promise.all([
      api.get<RawAgentRow[]>(`/api/llc/agents?company_id=${cid}`),
      api.get<PendingApproval[]>(`/api/llc/approvals?company_id=${cid}`),
      api.get<RawBudgetRow[]>(`/api/llc/budget?company_id=${cid}`),
      api.get<RawRunRow[]>('/api/llc/heartbeat-runs?limit=20'),
      api.get<{ items: Array<Record<string, unknown>> }>(`/api/llc/companies/${cid}/activity?page_size=50`),
    ])
    data.value = {
      agents: (agentsResp ?? []).map(mapAgent),
      approvals: approvalsResp ?? [],
      budgets: (budgetsResp ?? []).map(mapBudget),
      runs: (runsResp ?? []).map(mapRun),
      // Backend returns ActivityLogEntry rows, not the display shape — map them
      // through the same mapper as live events so fields aren't blank (#11395).
      activity: (activityResp?.items ?? []).map(mapActivityRow).slice(0, 50),
    }
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
    data.value.approvals = data.value.approvals.filter(a => a.id !== approvalId)
  } catch (err: unknown) {
    logger.error('Quick approve failed', err)
  }
}

function launchCeoChat() {
  // #11552 follow-up: the CEO Chat button must open THIS company's CEO chat, not
  // the global assistant. Route to the company-scoped ceo-chat view (mirrors
  // LlcSidebar's nav target) so the company context (and its LLC tools) apply.
  if (!companyId.value) return
  router.push({ path: `/llc/companies/${companyId.value}/ceo-chat` })
}

async function loadLayout() {
  await load()
  widgets.value = companyWidgetsOf(layout.value)
  dirty.value = false
}

function onWidgetsChange(next: CompanyWidget[]) {
  widgets.value = next
  dirty.value = true
}

async function saveLayout() {
  const saved = widgets.value
  // An edit made while the PUT was in flight replaced `widgets` (onWidgetsChange assigns a new array): keep it dirty.
  if ((await save(withCompanyWidgets(layout.value, saved))) && widgets.value === saved) {
    dirty.value = false
    editing.value = false
  }
}

async function resetLayout() {
  const ok = await confirm({ title: t('views.customDashboard.resetLayout'), message: t('views.customDashboard.resetLayoutConfirm') })
  if (!ok) return
  try {
    await reset()
    resetError.value = false
  } catch (err: unknown) {
    logger.error('Resetting the dashboard layout failed', err)
    resetError.value = true
    return
  }
  widgets.value = companyWidgetsOf(layout.value)
  dirty.value = false
}

onMounted(async () => {
  void loadLayout()
  await resolveCompanyId().then((id) => { companyId.value = id })
  if (!companyId.value) return
  await fetchDashboardData()
  // useLiveEvents auto-unsubscribes on unmount.
  live.subscribe(`company:${companyId.value}`, (ev) => {
    if (ev.event_type === 'llc:activity_created') pushActivity(ev.payload)
  })
})
</script>

<template>
  <!--
    Full-height scroll container: the shell gives dashboards a full-height content
    region (#10897). The sections are DashboardGrid widgets the user can move and
    resize; the layout is saved per user (#18242).
  -->
  <div class="h-full overflow-y-auto">
    <div class="mx-auto flex min-h-full max-w-7xl flex-col gap-6 p-4">
      <!-- Header -->
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h1 class="text-2xl font-bold text-autobot-text-primary">{{ $t('llc.dashboard.title') }}</h1>
        <div class="flex flex-wrap items-center gap-2">
          <template v-if="companyId">
            <BaseButton v-if="loadError" variant="secondary" @click="loadLayout">
              {{ $t('views.customDashboard.retryLoad') }}
            </BaseButton>
            <BaseButton v-else variant="secondary" :disabled="!loaded" :aria-pressed="editing" @click="editing = !editing">
              {{ editing ? $t('views.customDashboard.done') : $t('views.customDashboard.editLayout') }}
            </BaseButton>
            <BaseButton v-if="editing" variant="ghost" @click="resetLayout">
              {{ $t('views.customDashboard.resetLayout') }}
            </BaseButton>
            <BaseButton v-if="dirty" variant="secondary" :disabled="!loaded" @click="saveLayout">
              {{ $t('views.customDashboard.save') }}
            </BaseButton>
          </template>
          <BaseButton variant="primary" @click="launchCeoChat">
            {{ $t('llc.dashboard.ceoChat') }}
          </BaseButton>
        </div>
      </div>

      <!-- The layout is per user, not per company: its errors show whether or not a company resolved. -->
      <BaseAlert v-if="loadError" variant="warning" :message="$t('views.customDashboard.loadFailed')" />
      <BaseAlert v-if="saveError" variant="error" :message="$t('views.customDashboard.saveFailed')" />
      <BaseAlert v-if="resetError" variant="error" :message="$t('views.customDashboard.resetFailed')" />

      <div v-if="!companyId" class="py-12 text-center text-autobot-text-muted">
        {{ $t('llc.dashboard.selectCompany') }}
      </div>

      <template v-else>
        <BaseAlert v-if="error" variant="error" :message="error">
          <template #actions>
            <BaseButton size="sm" variant="ghost" @click="fetchDashboardData">{{ $t('llc.dashboard.retry') }}</BaseButton>
          </template>
        </BaseAlert>

        <!-- A refetch keeps the grid mounted, so an edit session in progress survives it. -->
        <p v-if="isLoading" role="status" class="text-sm text-autobot-text-muted">{{ $t('llc.dashboard.loading') }}</p>

        <DashboardGrid :widgets="widgets" :editing="editing" :label-of="labelOf" @update:widgets="onWidgetsChange">
          <template #widget="{ widget }">
            <CompanyDashboardWidget :type="widget.type" :data="data" @approve="quickApprove" />
          </template>
        </DashboardGrid>
      </template>
    </div>
  </div>
</template>
