<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ChatFilePanelToolbar -- the Chat files panel's count line, search field, sort group and bulk-selection
  bar (#22349). Presentational: the state lives in `useConversationFiles`; this renders it and emits intents.
  The sort group is a `role="group"` of kit buttons that carry `aria-pressed`; the active one shows its direction.
-->
<template>
  <div class="px-3 py-2 border-b border-autobot-border shrink-0 space-y-2">
    <div v-if="totalFiles > 0" class="flex justify-between text-xs text-autobot-text-secondary" data-testid="file-count">
      <span>{{ $t('chat.filePanel.fileCount', { count: totalFiles }, totalFiles) }}</span>
      <span>{{ totalSizeLabel }}</span>
    </div>
    <BaseInput
      :model-value="search"
      type="search"
      size="sm"
      :placeholder="$t('chat.filePanel.searchFiles')"
      :aria-label="$t('chat.filePanel.searchLabel')"
      @update:model-value="emit('update:search', $event)"
    >
      <template #prefix><Icon name="search" /></template>
    </BaseInput>
    <div class="flex flex-wrap items-center gap-1 text-xs" role="group" :aria-label="$t('chat.filePanel.sortGroupLabel')">
      <span class="text-autobot-text-secondary">{{ $t('chat.filePanel.sort') }}:</span>
      <BaseButton
        v-for="opt in sortOptions"
        :key="opt.field"
        variant="ghost"
        size="xs"
        :aria-pressed="sortField === opt.field"
        data-testid="sort-button"
        @click="emit('sort', opt.field)"
      >
        {{ opt.label }}
        <Icon v-if="sortField === opt.field" :name="sortDirection === 'asc' ? 'arrow-up' : 'arrow-down'" />
      </BaseButton>
    </div>
    <div
      v-if="selectedCount > 0"
      class="flex items-center justify-between rounded-md px-2 py-1 bg-autobot-bg-tertiary"
      data-testid="selection-bar"
    >
      <span class="text-xs text-autobot-text-secondary">{{ $t('chat.filePanel.nSelected', { count: selectedCount }) }}</span>
      <div class="flex gap-1">
        <BaseButton variant="link" size="xs" class="text-autobot-error" data-testid="bulk-delete" @click="emit('bulk-delete')">
          {{ $t('common.delete') }}
        </BaseButton>
        <BaseButton variant="link" size="xs" data-testid="select-all" @click="emit('select-all')">
          {{ allSelected ? $t('chat.filePanel.deselect') : $t('chat.filePanel.selectAll') }}
        </BaseButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton, BaseInput } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import type { SortDirection, SortField } from '@/composables/useConversationFiles'

defineProps<{
  totalFiles: number
  totalSizeLabel: string
  search: string
  sortField: SortField
  sortDirection: SortDirection
  selectedCount: number
  allSelected: boolean
}>()
const emit = defineEmits<{
  'update:search': [value: string]
  sort: [field: SortField]
  'bulk-delete': []
  'select-all': []
}>()

const { t } = useI18n()
const sortOptions = computed(() => [
  { field: 'name' as SortField, label: t('chat.filePanel.sortName') },
  { field: 'date' as SortField, label: t('chat.filePanel.sortDate') },
  { field: 'size' as SortField, label: t('chat.filePanel.sortSize') },
  { field: 'type' as SortField, label: t('chat.filePanel.sortType') },
])
</script>
