<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0
  AutoBot - AI-Powered Automation Platform
  Author: mrveiss

  TeamsView -- Company OS > Organization > Teams (#18245, mockup Teams).

  Company-scoped child of LlcCompanyLayout (/llc/companies/:companyId/teams). Lists the company's
  teams and who is on each (GET /api/llc/companies/{id}/teams). Read-only: creating, deleting and
  changing the members of a team land with the company-scoped write routes (#14106). Reading says
  "couldn't read" apart from "no teams" and "not available". Teams hold users only (the backend has no team column for agents or
  contacts), so the mockup's team lead, projects and managers have no data behind them and are not
  drawn.
-->
<template>
  <div class="flex flex-col gap-4 p-4" data-testid="company-teams">
    <PageHeader :title="t('llcTeams.title')" :subtitle="t('llcTeams.subtitle')" />

    <p v-if="!companyId" class="m-0 text-autobot-text-secondary" data-testid="teams-no-company">{{ t('llcTeams.noCompany') }}</p>

    <template v-else>
      <div v-if="state === 'loading'" class="flex items-center gap-2 text-autobot-text-secondary" role="status" data-testid="teams-loading">
        <BaseSpinner size="sm" />
        <span>{{ t('llcTeams.loading') }}</span>
      </div>

      <BaseAlert v-else-if="state === 'failed'" variant="error" :message="t('llcTeams.loadError')" data-testid="teams-failed">
        <template #actions>
          <BaseButton variant="secondary" size="sm" data-testid="teams-retry" @click="load()">{{ t('llcTeams.retry') }}</BaseButton>
        </template>
      </BaseAlert>

      <EmptyState v-else-if="state === 'unavailable'" :title="t('llcTeams.unavailable')" data-testid="teams-unavailable" />

      <template v-else>
        <p class="m-0 text-sm text-autobot-text-secondary">{{ t('llcTeams.peopleOnly') }}</p>

        <EmptyState v-if="!hasTeams" :title="t('llcTeams.empty')" data-testid="teams-empty" />

        <BaseTable v-else :columns="teamColumns" :rows="teamRows" row-key="id" :aria-label="t('llcTeams.title')" :actions-label="t('llcTeams.colActions')" data-testid="teams-table">
          <template #actions="{ row }">
            <BaseButton variant="secondary" size="sm" :aria-pressed="selectedId === row.id" @click="selectedId = String(row.id)">
              {{ t('llcTeams.viewMembers') }}
            </BaseButton>
          </template>
        </BaseTable>

        <BaseCard v-if="hasTeams" data-testid="team-detail">
          <p v-if="!selected" class="m-0 text-autobot-text-secondary">{{ t('llcTeams.selectTeam') }}</p>
          <div v-else class="flex flex-col gap-3">
            <h2 class="m-0 text-base text-autobot-text-primary">{{ t('llcTeams.membersOf', { name: selected.name }) }}</h2>
            <BaseAlert v-if="membersFailed" variant="warning" :message="t('llcTeams.namesError')" data-testid="teams-names-error" />

            <p v-if="memberRows.length === 0" class="m-0 text-autobot-text-secondary" data-testid="team-no-members">{{ t('llcTeams.noMembers') }}</p>
            <BaseTable v-else :columns="memberColumns" :rows="memberRows" row-key="id" size="compact" :aria-label="t('llcTeams.membersOf', { name: selected.name })" data-testid="team-members">
              <template #cell-name="{ row }">
                <span>{{ row.name }}</span>
                <BaseBadge v-if="row.inactive" size="sm" variant="warning" class="ms-2">{{ t('llcTeams.inactive') }}</BaseBadge>
              </template>
            </BaseTable>
          </div>
        </BaseCard>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  BaseAlert, BaseBadge, BaseButton, BaseCard, BaseSpinner, BaseTable, EmptyState, PageHeader,
  type BaseTableColumn,
} from '@autobot/ui'
import { useApiClient } from '@/plugins/api'
import { useCompanyTeams, type CompanyTeam } from '@/composables/llc/useCompanyTeams'

const props = defineProps<{ companyId?: string }>()
const route = useRoute()
const { t } = useI18n()
const companyId = computed(() => (route.params.companyId as string) ?? props.companyId ?? '')

const { teams, members, state, membersFailed, hasTeams, nameOf, isInactive, load } =
  useCompanyTeams(useApiClient(), () => companyId.value)

const selectedId = ref('')
const selected = computed<CompanyTeam | undefined>(() => teams.value.find((x) => x.id === selectedId.value))
// A team gone after a reload is no longer selected.
watch(teams, () => {
  if (selectedId.value && !selected.value) selectedId.value = ''
})
watch(companyId, () => { selectedId.value = '' })

const teamColumns = computed<BaseTableColumn[]>(() => [
  { key: 'name', label: t('llcTeams.colTeam') },
  { key: 'count', label: t('llcTeams.colMembers'), numeric: true },
])
const teamRows = computed(() => teams.value.map((x) => ({ id: x.id, name: x.name, count: x.member_user_ids.length })))

const memberColumns = computed<BaseTableColumn[]>(() => [
  { key: 'name', label: t('llcTeams.colName') },
  { key: 'role', label: t('llcTeams.colRole') },
])
const memberRows = computed(() =>
  (selected.value?.member_user_ids ?? []).map((userId) => ({
    id: userId,
    name: nameOf(userId),
    role: members.value.find((m) => m.user_id === userId)?.role ?? '',
    inactive: isInactive(userId),
  })),
)

onMounted(() => load())
</script>
