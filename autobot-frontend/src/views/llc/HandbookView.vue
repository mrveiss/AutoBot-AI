<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  HandbookView -- Company OS > Organization > Handbook (#18431, mockup Handbook). A reference
  page for every role, workflow, process and meta skill, generated from the company model on
  every load, plus a coverage list of pages whose model records no description.

  What has no backend yet (company chapters, owner-written explanations and their approval,
  onboarding paths and read confirmations, need-to-know scoping, Knowledge/chat search, who a
  role works with) is listed as not available. Nothing here stands in for it.
-->
<template>
  <div class="flex flex-col gap-4 p-4" data-testid="handbook">
    <PageHeader :title="t('llc.handbook.title')" :subtitle="t('llc.handbook.subtitle')" />

    <p v-if="!companyId" class="m-0 text-autobot-text-secondary" data-testid="handbook-no-company">{{ t('llc.handbook.noCompany') }}</p>
    <template v-else>
      <BaseAlert v-for="(message, i) in handbook.errors.value" :key="i" variant="error" data-testid="handbook-error" :message="t('llc.handbook.sourceFailed', { reason: message })" />

      <p v-if="loading" class="m-0 text-autobot-text-secondary" role="status" data-testid="handbook-loading">{{ t('llc.handbook.loading') }}</p>
      <EmptyState v-else-if="handbook.pages.value.length === 0 && handbook.errors.value.length === 0" :title="t('llc.handbook.emptyTitle')" :description="t('llc.handbook.emptyBody')" data-testid="handbook-empty" />

      <template v-else>
        <BaseCard data-testid="handbook-coverage">
          <h2 class="m-0 mb-2 text-base text-autobot-text-primary">{{ t('llc.handbook.coverage.title') }}</h2>
          <p class="m-0 text-autobot-text-secondary">{{ t('llc.handbook.coverage.body') }}</p>
          <ul class="m-0 ps-4">
            <li v-for="k in kinds" :key="k" data-testid="handbook-coverage-count">{{ t(`llc.handbook.kindPlural.${k}`) }}: {{ countOf(k) }}</li>
          </ul>
          <h3 class="mt-3 mb-1 text-sm text-autobot-text-primary">{{ t('llc.handbook.coverage.missing', { n: missing.length }) }}</h3>
          <ul class="m-0 ps-4" data-testid="handbook-coverage-missing">
            <li v-for="p in missing" :key="`${p.kind}:${p.id}`">
              <button type="button" class="text-autobot-primary" @click="select(p)">{{ p.title }}</button>
              <span class="text-autobot-text-secondary"> ({{ t(`llc.handbook.kind.${p.kind}`) }})</span>
            </li>
          </ul>
        </BaseCard>

        <div class="flex flex-wrap gap-4">
          <BaseCard class="min-w-64 flex-1">
            <BaseInput v-model="query" :label="t('llc.handbook.search')" :placeholder="t('llc.handbook.searchPlaceholder')" data-testid="handbook-search" />
            <BaseTabs v-model="filter" :items="filterItems" :label="t('llc.handbook.filterAria')" />
            <p v-if="shown.length === 0" class="m-0 mt-2 text-autobot-text-secondary" data-testid="handbook-no-match">{{ t('llc.handbook.noMatch') }}</p>
            <ul class="m-0 mt-2 ps-0 list-none" data-testid="handbook-pages">
              <li v-for="p in shown" :key="`${p.kind}:${p.id}`">
                <button type="button" class="w-full text-start px-2 py-1 rounded text-autobot-text-primary"
                  :aria-current="isSelected(p) ? 'page' : undefined" data-testid="handbook-page-link" @click="select(p)">
                  {{ p.title }} <span class="text-autobot-text-secondary">({{ t(`llc.handbook.kind.${p.kind}`) }})</span>
                </button>
              </li>
            </ul>
          </BaseCard>

          <BaseCard class="min-w-64 flex-[2]">
            <HandbookPageDetail v-if="selected" :page="selected" :detail="handbook.detail.value" :pages="handbook.pages.value"
              :workflows="handbook.workflows.value" :processes="handbook.processes.value" :names="names" />
            <p v-else class="m-0 text-autobot-text-secondary" data-testid="handbook-pick">{{ t('llc.handbook.pickPage') }}</p>
          </BaseCard>
        </div>
      </template>

      <BaseCard data-testid="handbook-unavailable">
        <h2 class="m-0 mb-2 text-base text-autobot-text-primary">{{ t('llc.handbook.unavailable.title') }}</h2>
        <p class="m-0 text-autobot-text-secondary">{{ t('llc.handbook.unavailable.body') }}</p>
        <ul class="m-0 ps-4">
          <li v-for="k in unavailable" :key="k" data-testid="handbook-unavailable-item">{{ t(`llc.handbook.unavailable.${k}`) }}</li>
        </ul>
      </BaseCard>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseCard, BaseInput, BaseTabs, EmptyState, PageHeader } from '@autobot/ui'
import HandbookPageDetail from '@/components/llc/handbook/HandbookPageDetail.vue'
import { useHandbook, type HandbookPage, type PageKind } from '@/composables/llc/useHandbook'

const kinds: PageKind[] = ['role', 'workflow', 'process', 'metaSkill']
const unavailable = ['chapters', 'explanations', 'onboarding', 'scoping', 'search', 'handoffs']

const { t } = useI18n()
const route = useRoute()
const companyId = computed(() => (route.params.companyId as string) || '')
const handbook = useHandbook(() => companyId.value)

const query = ref('')
const filter = ref('all')
const selected = ref<HandbookPage | null>(null)

const loading = computed(() => Object.values(handbook.sources.value).some((s) => s === 'loading'))
const names = {
  process: handbook.processName,
  workflow: handbook.workflowName,
  role: handbook.roleName,
}
const filterItems = computed(() => [
  { value: 'all', label: t('llc.handbook.filterAll') },
  ...kinds.map((k) => ({ value: k, label: t(`llc.handbook.kindPlural.${k}`) })),
])
const shown = computed(() => {
  const needle = query.value.trim().toLowerCase()
  return handbook.pages.value.filter(
    (p) => (filter.value === 'all' || p.kind === filter.value) && (!needle || p.title.toLowerCase().includes(needle)),
  )
})
/** Only roles and processes can carry a description in the model; the other kinds have no such field. */
const missing = computed(() => handbook.pages.value.filter((p) => (p.kind === 'role' || p.kind === 'process') && !p.description))
const countOf = (k: PageKind): number => handbook.pages.value.filter((p) => p.kind === k).length
const isSelected = (p: HandbookPage): boolean => selected.value?.kind === p.kind && selected.value?.id === p.id

function select(page: HandbookPage): void {
  selected.value = page
  void handbook.open(page)
}

onMounted(() => void handbook.load())
watch(companyId, () => {
  selected.value = null
  void handbook.load()
})
</script>
