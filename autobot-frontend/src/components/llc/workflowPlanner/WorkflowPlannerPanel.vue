<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  WorkflowPlannerPanel (#19938): the Workflow Planner view mode of the Org Chart. Lists the
  company's plans with their status, creates a plan, and opens one. While the planner switch is
  off the routes answer 404; that is shown as "not available", not as an error and not as an
  empty list. Entry points (wizard exit, the Workflow Automation quick action) arrive as
  `entryPoint` and are recorded on the plan they create.
-->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { BaseAlert, BaseButton, BaseInput, BaseTable, EmptyState, useToast, type BaseTableColumn } from '@autobot/ui'
import WorkflowPlanDetail from './WorkflowPlanDetail.vue'
import { describeApiError } from '@/composables/llc/apiErrorMessage'
import { useWorkflowPlans } from '@/composables/llc/useWorkflowPlans'
import { plannerEntryPoint } from '@/composables/llc/workflowPlanTypes'

// Deep links name the entry point (wizard exit, the Workflow Automation quick action).
const route = useRoute() as ReturnType<typeof useRoute> | undefined
const entryPoint = computed(() => plannerEntryPoint(route?.query?.entry_point))
const { t } = useI18n()
const { showToast } = useToast()
const api = useWorkflowPlans()

const openKey = ref('')
const showForm = ref(false)
const creating = ref(false)
const form = ref({ name: '', startsAt: '', endsAt: '' })

const columns = computed<BaseTableColumn[]>(() => [
  { key: 'name', label: t('llc.workflowPlanner.col.name') },
  { key: 'revision', label: t('llc.workflowPlanner.col.revision'), numeric: true },
  { key: 'status', label: t('llc.workflowPlanner.col.status'), formatter: (v) => t(`llc.workflowPlanner.status.${String(v)}`) },
])
const formValid = computed(() => !!(form.value.name.trim() && form.value.startsAt.trim() && form.value.endsAt.trim()))

function keyOf(name: string): string {
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40)
  return `${slug || 'plan'}-${Date.now().toString(36)}`
}

async function create() {
  if (creating.value || !formValid.value) return
  creating.value = true
  try {
    const plan = await api.create({
      key: keyOf(form.value.name),
      name: form.value.name.trim(),
      entry_point: entryPoint.value,
      starts_at: form.value.startsAt.trim(),
      ends_at: form.value.endsAt.trim(),
    })
    form.value = { name: '', startsAt: '', endsAt: '' }
    showForm.value = false
    openKey.value = plan.key
  } catch (err: unknown) {
    showToast(describeApiError(err, t('llc.workflowPlanner.createFailed')), 'error')
  } finally {
    creating.value = false
  }
}

function closeDetail() {
  openKey.value = ''
  void reload()
}

const reload = () => api.load(t('llc.workflowPlanner.loadFailed'))
onMounted(reload)
</script>

<template>
  <div data-testid="workflow-planner">
    <WorkflowPlanDetail v-if="openKey" :plan-key="openKey" :api="api" @back="closeDetail" />

    <p v-else-if="api.state.value === 'loading'" role="status" class="py-8 text-center text-autobot-text-muted" data-testid="planner-loading">
      {{ t('llc.workflowPlanner.loading') }}
    </p>

    <EmptyState v-else-if="api.state.value === 'unavailable'" :title="t('llc.workflowPlanner.unavailableTitle')" :description="t('llc.workflowPlanner.unavailableHint')" data-testid="planner-unavailable" />

    <div v-else-if="api.state.value === 'error'" data-testid="planner-error">
      <BaseAlert variant="error" :message="api.errorMessage.value" />
      <BaseButton class="mt-3" variant="secondary" size="sm" data-testid="planner-retry" @click="reload">{{ t('llc.workflowPlanner.retry') }}</BaseButton>
    </div>

    <template v-else>
      <div class="mb-3 flex items-center justify-between">
        <h3 class="text-lg font-semibold text-autobot-text-primary">{{ t('llc.workflowPlanner.plans') }}</h3>
        <BaseButton size="sm" data-testid="new-plan" @click="showForm = !showForm">{{ t('llc.workflowPlanner.newPlan') }}</BaseButton>
      </div>

      <form v-if="showForm" class="mb-4 flex flex-wrap items-end gap-3" data-testid="plan-form" @submit.prevent="create">
        <BaseInput v-model="form.name" size="sm" :label="t('llc.workflowPlanner.form.name')" />
        <BaseInput v-model="form.startsAt" size="sm" :label="t('llc.workflowPlanner.form.startsAt')" />
        <BaseInput v-model="form.endsAt" size="sm" :label="t('llc.workflowPlanner.form.endsAt')" />
        <BaseButton type="submit" size="sm" :loading="creating" :disabled="!formValid" data-testid="plan-create">{{ t('llc.workflowPlanner.form.create') }}</BaseButton>
      </form>

      <BaseTable
        :columns="columns"
        :rows="api.plans.value"
        row-key="plan_key"
        :aria-label="t('llc.workflowPlanner.plans')"
        :empty-title="t('llc.workflowPlanner.emptyTitle')"
        :empty-description="t('llc.workflowPlanner.emptyHint')"
        :actions-label="t('llc.workflowPlanner.col.actions')"
      >
        <template #actions="{ row }">
          <BaseButton size="xs" variant="outline" :data-testid="`open-${row.plan_key}`" @click="openKey = String(row.plan_key)">{{ t('llc.workflowPlanner.open') }}</BaseButton>
        </template>
      </BaseTable>
    </template>
  </div>
</template>
