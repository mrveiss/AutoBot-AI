<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  PlannerConversionSummary (#19938): what a conversion would create (preview) or did create
  (committed). Only the contract's PlanConversion is read here, so a change to the conversion
  response touches this one file. Errors and warnings are the server's strings, shown as sent.
-->
<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { BaseAlert, BaseButton } from '@autobot/ui'
import { laneName } from '@/composables/llc/workflowPlanTypes'
import type { Plan, PlanConversion } from '@/composables/llc/workflowPlanTypes'

const props = defineProps<{ plan: Plan; conversion: PlanConversion }>()
const { t } = useI18n()
const route = useRoute() as ReturnType<typeof useRoute> | undefined
const router = useRouter() as ReturnType<typeof useRouter> | undefined

const committed = computed(() => props.conversion.status === 'committed')
const errors = computed(() => [...(props.conversion.contract_errors ?? []), ...(props.conversion.preview_errors ?? [])])
const warnings = computed(() => props.conversion.preview_warnings ?? [])
const workflows = computed(() => props.conversion.workflows ?? [])
const processes = computed(() => props.conversion.processes ?? [])
const documented = computed(() => props.conversion.documentation_only ?? [])
const failedLines = computed(() => (props.conversion.ai_line_proposals ?? []).filter((p) => p.outcome === 'failed'))
const workflowsPath = computed(() => {
  const id = route?.params?.companyId
  const companyId = Array.isArray(id) ? id[0] : id
  return companyId ? `/llc/companies/${companyId}/automation` : ''
})

function openWorkflows(): void {
  void router?.push(workflowsPath.value)
}
</script>

<template>
  <section data-testid="conversion-summary" :data-status="conversion.status">
    <h4 class="text-sm font-semibold text-autobot-text-primary">
      {{ t(committed ? 'llc.workflowPlanner.convert.createdTitle' : 'llc.workflowPlanner.convert.previewTitle') }}
    </h4>
    <p class="text-sm text-autobot-text-secondary" data-testid="conversion-counts">
      {{ t('llc.workflowPlanner.convert.counts', { workflows: workflows.length, processes: processes.length }) }}
    </p>

    <ul class="my-2 space-y-1 text-sm text-autobot-text-primary" data-testid="conversion-workflows">
      <li v-for="w in workflows" :key="w.workflow_id">
        {{ w.name }}
        <span class="text-autobot-text-muted">({{ t('llc.workflowPlanner.convert.ownerLane', { lane: laneName(plan, w.owner_lane_key) }) }})</span>
      </li>
    </ul>

    <BaseAlert v-if="errors.length" variant="error" :title="t('llc.workflowPlanner.convert.errors')" data-testid="conversion-errors">
      <ul class="list-disc ps-5"><li v-for="e in errors" :key="e">{{ e }}</li></ul>
    </BaseAlert>
    <BaseAlert v-if="warnings.length" variant="warning" :title="t('llc.workflowPlanner.convert.warnings')" data-testid="conversion-warnings">
      <ul class="list-disc ps-5"><li v-for="w in warnings" :key="w">{{ w }}</li></ul>
    </BaseAlert>

    <div v-if="documented.length" class="my-2 text-sm text-autobot-text-secondary" data-testid="conversion-documented">
      {{ t('llc.workflowPlanner.convert.documented') }}
      <ul class="list-disc ps-5"><li v-for="d in documented" :key="d.sub_step_key">{{ d.sub_step_key }}: {{ d.reason }}</li></ul>
    </div>

    <BaseAlert v-if="failedLines.length" variant="warning" :message="t('llc.workflowPlanner.convert.failedProposals', { count: failedLines.length })" data-testid="conversion-failed-proposals" />
    <p class="my-2 text-sm text-autobot-text-muted" data-testid="turn-on-not-available">{{ t('llc.workflowPlanner.convert.turnOnNotAvailable') }}</p>

    <BaseButton v-if="committed && workflowsPath" size="sm" variant="outline" data-testid="open-workflows" @click="openWorkflows">
      {{ t('llc.workflowPlanner.convert.openWorkflows') }}
    </BaseButton>
  </section>
</template>
