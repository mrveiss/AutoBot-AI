<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="repos-tab">
    <div class="flex justify-end mb-4">
      <button
        class="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded text-sm
               text-white transition-colors"
        @click="showAddModal = true"
      >
        {{ $t('skills.reposTab.addRepo') }}
      </button>
    </div>

    <BaseTable
      :columns="columns"
      :rows="rows"
      :aria-label="$t('skills.reposTab.tableLabel')"
      :empty-title="$t('skills.reposTab.noRepositoriesRegisteredAdd')"
      :actions-label="$t('skills.reposTab.sync')"
    >
      <template #cell-repo_type="{ value }">
        <BaseBadge size="sm" :variant="repoBadgeVariant(String(value))">{{ value }}</BaseBadge>
      </template>
      <template #actions="{ row }">
        <button
          class="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs
                 text-gray-300 transition-colors"
          @click="$emit('sync', String(row.id))"
        >
          {{ $t('skills.reposTab.sync') }}
        </button>
      </template>
    </BaseTable>

    <!-- Add Repo Modal -->
    <BaseModal
      v-model="showAddModal"
      :title="$t('skills.reposTab.addSkillRepository')"
      size="sm"
      :close-label="$t('ui.modal.closeDialog')"
    >
      <div class="space-y-3">
        <label class="block">
          <span class="text-sm text-gray-400">{{ $t('skills.reposTab.name') }}</span>
          <input
            v-model="newRepo.name"
            type="text"
            :placeholder="$t('skills.reposTab.mySkills')"
            class="mt-1 w-full bg-gray-900 border border-gray-700 rounded px-3 py-2
                   text-white text-sm focus:outline-hidden focus:border-blue-500"
          />
        </label>
        <label class="block">
          <span class="text-sm text-gray-400">{{ $t('skills.reposTab.uRL') }}</span>
          <input
            v-model="newRepo.url"
            type="text"
            :placeholder="$t('skills.reposTab.httpsOrPathToDir')"
            class="mt-1 w-full bg-gray-900 border border-gray-700 rounded px-3 py-2
                   text-white text-sm focus:outline-hidden focus:border-blue-500"
          />
        </label>
        <label class="block">
          <span class="text-sm text-gray-400">{{ $t('skills.reposTab.type') }}</span>
          <select
            v-model="newRepo.repo_type"
            class="mt-1 w-full bg-gray-900 border border-gray-700 rounded px-3 py-2
                   text-white text-sm focus:outline-hidden focus:border-blue-500"
          >
            <option value="git">{{ $t('skills.reposTab.git') }}</option>
            <option value="local">{{ $t('skills.reposTab.local') }}</option>
            <option value="http">{{ $t('skills.reposTab.hTTP') }}</option>
            <option value="mcp">{{ $t('skills.reposTab.mCP') }}</option>
          </select>
        </label>
      </div>
      <template #actions>
        <button
          class="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded text-sm
                 text-white transition-colors"
          @click="submitAdd"
        >
          {{ $t('skills.reposTab.add') }}
        </button>
        <button
          class="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm
                 text-gray-300 transition-colors"
          @click="showAddModal = false"
        >
          {{ $t('skills.reposTab.cancel') }}
        </button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { SkillRepo } from '@/composables/useSkills'
import { formatDateTime } from '@/composables/useTimezone'
import { BaseBadge, BaseModal, BaseTable, type BadgeVariant, type BaseTableColumn } from '@autobot/ui'

const props = defineProps<{ repos: readonly SkillRepo[] }>()
const { t } = useI18n()
const emit = defineEmits<{
  sync: [id: string]
  add: [payload: Omit<SkillRepo, 'id' | 'skill_count' | 'status' | 'last_synced'>]
}>()

const showAddModal = ref(false)
const newRepo = ref<Omit<SkillRepo, 'id' | 'skill_count' | 'status' | 'last_synced'>>({
  name: '',
  url: '',
  repo_type: 'git',
})

const BADGE_VARIANT: Record<string, BadgeVariant> = { git: 'primary', http: 'info', mcp: 'info' }
const repoBadgeVariant = (repoType: string): BadgeVariant => BADGE_VARIANT[repoType] ?? 'neutral'

// BaseTable rows are plain records; SkillRepo carries no index signature.
const rows = computed(() => props.repos.map((repo) => ({ ...repo })))
const columns = computed<BaseTableColumn[]>(() => [
  { key: 'name', label: t('skills.reposTab.name') },
  { key: 'repo_type', label: t('skills.reposTab.type') },
  { key: 'url', label: t('skills.reposTab.uRL') },
  { key: 'skill_count', label: t('skills.reposTab.skills'), numeric: true },
  { key: 'last_synced', label: t('skills.reposTab.lastSync'), formatter: (v) => formatDateTime(v as string) },
])

function submitAdd(): void {
  emit('add', { ...newRepo.value })
  showAddModal.value = false
  newRepo.value = { name: '', url: '', repo_type: 'git' }
}
</script>
