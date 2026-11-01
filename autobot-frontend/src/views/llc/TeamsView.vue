<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0
  AutoBot - AI-Powered Automation Platform
  Author: mrveiss

  TeamsView -- Company OS > Organization > Teams (#18245, mockup Teams).

  Company-scoped child of LlcCompanyLayout (/llc/companies/:companyId/teams). Lists the company's
  teams and who is on each (GET /api/llc/companies/{id}/teams), creates and deletes a team, and adds
  or removes a member (the user-management team routes, which the server limits to platform
  administrators: a refusal is shown, not hidden). Reading says "couldn't read" apart from "no
  teams" and "not available". Teams hold users only (the backend has no team column for agents or
  contacts), so the mockup's team lead, projects and managers have no data behind them and are not
  drawn. See useCompanyTeams for how a write is scoped to the company shown.
-->
<template>
  <div class="flex flex-col gap-4 p-4" data-testid="company-teams">
    <PageHeader :title="t('llcTeams.title')" :subtitle="t('llcTeams.subtitle')">
      <template #actions>
        <BaseButton v-if="companyId && state === 'ready'" variant="primary" data-testid="teams-create" @click="openCreate">
          {{ t('llcTeams.createTeam') }}
        </BaseButton>
      </template>
    </PageHeader>

    <p v-if="!companyId" class="m-0 text-autobot-text-secondary" data-testid="teams-no-company">{{ t('llcTeams.noCompany') }}</p>

    <template v-else>
      <BaseAlert v-if="errorMessage && !showCreate && !showDelete" variant="error" :message="errorMessage" dismissible :dismiss-label="t('common.dismiss')" data-testid="teams-error" />

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

        <EmptyState v-if="!hasTeams" :title="t('llcTeams.empty')" :description="t('llcTeams.emptyHint')" data-testid="teams-empty" />

        <BaseTable v-else :columns="teamColumns" :rows="teamRows" row-key="id" :aria-label="t('llcTeams.title')" :actions-label="t('llcTeams.colActions')" data-testid="teams-table">
          <template #actions="{ row }">
            <div class="flex gap-2">
              <BaseButton variant="secondary" size="sm" :aria-pressed="selectedId === row.id" @click="selectedId = String(row.id)">
                {{ t('llcTeams.manage') }}
              </BaseButton>
              <BaseButton variant="error" size="sm" :disabled="pending" @click="askDelete(String(row.id))">
                {{ t('llcTeams.deleteTeam') }}
              </BaseButton>
            </div>
          </template>
        </BaseTable>

        <BaseCard v-if="hasTeams" data-testid="team-detail">
          <p v-if="!selected" class="m-0 text-autobot-text-secondary">{{ t('llcTeams.selectTeam') }}</p>
          <div v-else class="flex flex-col gap-3">
            <h2 class="m-0 text-base text-autobot-text-primary">{{ t('llcTeams.membersOf', { name: selected.name }) }}</h2>
            <BaseAlert v-if="membersFailed" variant="warning" :message="t('llcTeams.namesError')" data-testid="teams-names-error" />

            <p v-if="memberRows.length === 0" class="m-0 text-autobot-text-secondary" data-testid="team-no-members">{{ t('llcTeams.noMembers') }}</p>
            <BaseTable v-else :columns="memberColumns" :rows="memberRows" row-key="id" size="compact" :aria-label="t('llcTeams.membersOf', { name: selected.name })" :actions-label="t('llcTeams.colActions')" data-testid="team-members">
              <template #cell-name="{ row }">
                <span>{{ row.name }}</span>
                <BaseBadge v-if="row.inactive" size="sm" variant="warning" class="ms-2">{{ t('llcTeams.inactive') }}</BaseBadge>
              </template>
              <template #actions="{ row }">
                <BaseButton variant="error" size="sm" :disabled="pending" :aria-label="t('llcTeams.removeMemberAria', { name: String(row.name), team: selected.name })" data-testid="team-remove-member" @click="onRemove(String(row.id))">
                  {{ t('llcTeams.removeMember') }}
                </BaseButton>
              </template>
            </BaseTable>

            <div class="flex flex-wrap items-end gap-2" data-testid="team-add">
              <p v-if="candidates.length === 0" class="m-0 text-autobot-text-secondary" data-testid="team-no-candidates">{{ t('llcTeams.noCandidates') }}</p>
              <template v-else>
                <BaseSelectMenu v-model="candidateId" :options="candidateOptions" :label="t('llcTeams.addMemberLabel')" :placeholder="t('llcTeams.addMemberPlaceholder')" :disabled="pending" />
                <BaseButton variant="primary" :disabled="!candidateId || pending" :loading="pending" data-testid="team-add-member" @click="onAdd">
                  {{ t('llcTeams.addMemberAction') }}
                </BaseButton>
              </template>
            </div>
          </div>
        </BaseCard>
      </template>
    </template>

    <BaseModal v-model="showCreate" :title="t('llcTeams.createTitle')" size="sm" :close-label="t('ui.modal.closeDialog')">
      <BaseAlert v-if="errorMessage" variant="error" :message="errorMessage" data-testid="teams-create-error" />
      <BaseInput v-model="newName" :label="t('llcTeams.nameLabel')" :helper-text="t('llcTeams.nameHint')" :error="nameError" required data-testid="teams-name" @keydown.enter.prevent="submitCreate" />
      <template #actions>
        <BaseButton variant="secondary" :disabled="pending" @click="showCreate = false">{{ t('llcTeams.cancel') }}</BaseButton>
        <BaseButton variant="primary" :loading="pending" :disabled="pending" data-testid="teams-create-confirm" @click="submitCreate">{{ t('llcTeams.create') }}</BaseButton>
      </template>
    </BaseModal>

    <BaseModal v-model="showDelete" :title="t('llcTeams.deleteTitle')" size="sm" :close-label="t('ui.modal.closeDialog')">
      <BaseAlert v-if="errorMessage" variant="error" :message="errorMessage" data-testid="teams-delete-error" />
      <p class="m-0 text-autobot-text-primary">{{ t('llcTeams.deleteConfirm', { name: toDelete?.name ?? '' }) }}</p>
      <template #actions>
        <BaseButton variant="secondary" :disabled="pending" @click="showDelete = false">{{ t('llcTeams.cancel') }}</BaseButton>
        <BaseButton variant="error" :loading="pending" :disabled="pending" data-testid="teams-delete-confirm" @click="confirmDelete">{{ t('llcTeams.confirmDelete') }}</BaseButton>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  BaseAlert, BaseBadge, BaseButton, BaseCard, BaseInput, BaseModal, BaseSelectMenu, BaseSpinner, BaseTable, EmptyState, PageHeader,
  type BaseTableColumn,
} from '@autobot/ui'
import { useApiClient } from '@/plugins/api'
import { candidatesFor, useCompanyTeams, type CompanyTeam } from '@/composables/llc/useCompanyTeams'

const props = defineProps<{ companyId?: string }>()
const route = useRoute()
const { t } = useI18n()
const companyId = computed(() => (route.params.companyId as string) ?? props.companyId ?? '')

const { teams, members, state, membersFailed, errorMessage, pending, hasTeams, nameOf, isInactive, load, createTeam, deleteTeam, addMember, removeMember } =
  useCompanyTeams(useApiClient(), () => companyId.value)

const selectedId = ref('')
const selected = computed<CompanyTeam | undefined>(() => teams.value.find((x) => x.id === selectedId.value))
// A team deleted (or gone after a reload) is no longer selected.
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

const candidates = computed(() => (selected.value ? candidatesFor(selected.value, members.value) : []))
const candidateOptions = computed(() => candidates.value.map((m) => ({ value: m.user_id, label: m.display_name })))
const candidateId = ref('')
watch([selectedId, candidates], () => {
  if (!candidates.value.some((m) => m.user_id === candidateId.value)) candidateId.value = ''
})

async function onAdd(): Promise<void> {
  if (!selected.value || !candidateId.value) return
  if (await addMember(selected.value, candidateId.value)) candidateId.value = ''
}
const onRemove = (userId: string) => (selected.value ? removeMember(selected.value, userId) : Promise.resolve(false))

const showCreate = ref(false)
const newName = ref('')
const nameError = ref('')
function openCreate(): void {
  newName.value = ''
  nameError.value = ''
  showCreate.value = true
}
async function submitCreate(): Promise<void> {
  if (!newName.value.trim()) {
    nameError.value = t('llcTeams.nameRequired')
    return
  }
  nameError.value = ''
  if (await createTeam(newName.value)) showCreate.value = false
}

const showDelete = ref(false)
const toDelete = ref<CompanyTeam | undefined>()
function askDelete(id: string): void {
  toDelete.value = teams.value.find((x) => x.id === id)
  showDelete.value = !!toDelete.value
}
async function confirmDelete(): Promise<void> {
  if (toDelete.value && (await deleteTeam(toDelete.value))) showDelete.value = false
}

onMounted(() => load())
</script>
