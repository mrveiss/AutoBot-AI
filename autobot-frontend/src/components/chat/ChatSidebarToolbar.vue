<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ChatSidebarToolbar -- the top of the chat sidebar (#18243): the primary New chat button, the
  Select chats toggle and the title search, all on the kit. In selection mode the toggle becomes
  a Cancel button and the selected count is shown. Emits intents only; state lives in the parent.
-->
<template>
  <div class="mb-2 flex shrink-0 flex-col gap-2">
    <div class="flex gap-2">
      <BaseTooltip :text="$t('chat.newChat')" placement="bottom" class="grow">
        <template #default="{ describedby }">
          <BaseButton block variant="primary" size="sm" :aria-describedby="describedby" @click="emit('new-chat')">
            <template #icon-left><Icon name="plus" /></template>
            {{ $t('chat.newChat') }}
          </BaseButton>
        </template>
      </BaseTooltip>
      <BaseTooltip :text="selectionMode ? $t('common.cancel') : $t('chat.sidebar.selectChats')" placement="bottom">
        <template #default="{ describedby }">
          <BaseButton
            variant="outline"
            size="sm"
            :aria-label="selectionMode ? $t('common.cancel') : $t('chat.sidebar.selectChats')"
            :aria-describedby="describedby"
            @click="emit('toggle-selection')"
          >
            <Icon :name="selectionMode ? 'times' : 'check-square'" />
          </BaseButton>
        </template>
      </BaseTooltip>
      <!-- Reset, Delete and Refresh: kept from the old bottom block, advanced-only (D2) -->
      <BaseDropdownMenu v-if="!selectionMode" class="adv" :items="moreItems" size="sm" align="end" @select="onMore">
        <template #trigger>
          <BaseButton variant="outline" size="sm" class="adv" :aria-label="$t('chat.sidebar.moreActions')">
            <Icon name="ellipsis-h" />
          </BaseButton>
        </template>
      </BaseDropdownMenu>
    </div>
    <p v-if="selectionMode" class="m-0 text-xs text-[var(--aui-color-text-muted)]" role="status">
      {{ $t('chat.sidebar.nSelected', { count: selectedCount }) }}
    </p>
    <BaseButton
      v-if="selectionMode"
      variant="error"
      size="sm"
      block
      :disabled="selectedCount === 0"
      :aria-label="$t('chat.sidebar.deleteSelected')"
      @click="emit('delete-selected')"
    >
      <template #icon-left><Icon name="trash" /></template>
      {{ $t('chat.sidebar.deleteNSelected', { count: selectedCount }) }}
    </BaseButton>
    <BaseInput
      :model-value="search"
      type="search"
      size="sm"
      clearable
      :clear-label="$t('common.clear')"
      :placeholder="$t('chat.sidebar.searchChats')"
      :aria-label="$t('chat.sidebar.searchChats')"
      @update:model-value="emit('update:search', $event)"
    >
      <template #prefix><Icon name="search" /></template>
    </BaseInput>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton, BaseDropdownMenu, BaseInput, BaseTooltip } from '@autobot/ui'
import type { MenuItem } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'

const props = defineProps<{ search: string; selectionMode: boolean; selectedCount: number; hasCurrentSession: boolean }>()
const emit = defineEmits<{
  'new-chat': []
  'toggle-selection': []
  'delete-selected': []
  'reset-chat': []
  'delete-chat': []
  'refresh': []
  'update:search': [value: string]
}>()

const { t } = useI18n()

const moreItems = computed<MenuItem[]>(() => [
  { key: 'reset', label: t('chat.sidebar.resetChat'), disabled: !props.hasCurrentSession },
  { key: 'delete', label: t('chat.sidebar.deleteChat'), disabled: !props.hasCurrentSession, variant: 'danger', separatorBefore: true },
  { key: 'refresh', label: t('chat.sidebar.refreshList'), separatorBefore: true },
])

function onMore(key: string): void {
  if (key === 'reset') emit('reset-chat')
  else if (key === 'delete') emit('delete-chat')
  else if (key === 'refresh') emit('refresh')
}
</script>
