<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  PlanBeforeBuildingAction (#19938): the first Workflow Automation quick action. It opens the
  company's Org Chart in Workflow Planner mode and records `workflow_area` as the entry point.
  Only a company-scoped builder (/llc/companies/:id/automation) can reach the Org Chart, so
  anywhere else the action renders nothing.
-->
<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import Icon from '@/components/ui/Icon.vue'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const plannerPath = computed(() => {
  const id = route.params.companyId
  const companyId = Array.isArray(id) ? id[0] : id
  return companyId ? `/llc/companies/${companyId}/org-chart` : ''
})

function open(): void {
  void router.push({ path: plannerPath.value, query: { view: 'planner', entry_point: 'workflow_area' } })
}
</script>

<template>
  <button v-if="plannerPath" type="button" class="quick-action" data-testid="plan-before-building" @click="open">
    <Icon name="chess" />
    <span>{{ t('workflow.views.planBeforeBuilding') }}</span>
  </button>
</template>
