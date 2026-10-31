<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  PlanFirstProcessCard (#19938, entry point E2): shown on the company landing page right after
  the creation wizard. "Plan my first process" opens the Org Chart in Workflow Planner mode and
  records `wizard_exit` as the entry point; "Later" only drops the flag from the URL. The wizard
  itself keeps its three steps.
-->
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { BaseAlert, BaseButton } from '@autobot/ui'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

function companyPath(): string {
  const id = route.params.companyId
  return `/llc/companies/${Array.isArray(id) ? id[0] : id}`
}

function planNow(): void {
  void router.push({ path: `${companyPath()}/org-chart`, query: { view: 'planner', entry_point: 'wizard_exit' } })
}

function later(): void {
  void router.replace({ path: route.path, query: { ...route.query, welcome: undefined } })
}
</script>

<template>
  <BaseAlert variant="success" :title="t('llc.workflowPlanner.firstProcess.title')" :message="t('llc.workflowPlanner.firstProcess.body')" data-testid="plan-first-process">
    <template #actions>
      <BaseButton size="sm" data-testid="plan-first-process-now" @click="planNow">{{ t('llc.workflowPlanner.firstProcess.plan') }}</BaseButton>
      <BaseButton size="sm" variant="ghost" data-testid="plan-first-process-later" @click="later">{{ t('llc.workflowPlanner.firstProcess.later') }}</BaseButton>
    </template>
  </BaseAlert>
</template>
