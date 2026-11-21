<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ChatSidebarToolbar -- the top of the chat sidebar (#18243): the primary New chat button, the
  Select chats toggle and the title search, all on the kit. In selection mode the toggle becomes
  a Cancel button and the selected count is shown. Emits intents only; state lives in the parent.
-->
<template>
  <div class="chat-sidebar-toolbar">
    <div class="chat-sidebar-toolbar__row">
      <BaseButton class="chat-sidebar-toolbar__new" variant="primary" size="sm" @click="emit('new-chat')">
        <template #icon-left><Icon name="plus" /></template>
        {{ $t('chat.newChat') }}
      </BaseButton>
      <BaseTooltip :text="selectionMode ? $t('common.cancel') : $t('chat.sidebar.selectChats')" placement="bottom">
        <template #default="{ describedby }">
          <BaseButton
            variant="outline"
            size="sm"
            :aria-label="selectionMode ? $t('common.cancel') : $t('chat.sidebar.selectChats')"
            :aria-describedby="describedby"
            :aria-pressed="selectionMode"
            @click="emit('toggle-selection')"
          >
            <Icon :name="selectionMode ? 'times' : 'check-square'" />
          </BaseButton>
        </template>
      </BaseTooltip>
    </div>
    <p v-if="selectionMode" class="chat-sidebar-toolbar__count" role="status">
      {{ $t('chat.sidebar.nSelected', { count: selectedCount }) }}
    </p>
    <BaseInput
      :model-value="search"
      type="search"
      size="sm"
      clearable
      :clear-label="$t('common.clear')"
      :placeholder="$t('chat.sidebar.searchChats')"
      :aria-label="$t('chat.sidebar.searchChats')"
      @update:model-value="emit('update:search', $event)"
    />
  </div>
</template>

<script setup lang="ts">
import { BaseButton, BaseInput, BaseTooltip } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'

defineProps<{ search: string; selectionMode: boolean; selectedCount: number }>()
const emit = defineEmits<{
  'new-chat': []
  'toggle-selection': []
  'update:search': [value: string]
}>()
</script>

<style scoped>
.chat-sidebar-toolbar {
  display: flex;
  flex-direction: column;
  gap: var(--aui-space-2);
  flex-shrink: 0;
}

.chat-sidebar-toolbar__row {
  display: flex;
  gap: var(--aui-space-2);
}

.chat-sidebar-toolbar__new {
  flex-grow: 1;
}

.chat-sidebar-toolbar__count {
  margin: 0;
  font-size: var(--aui-text-xs);
  color: var(--aui-color-text-muted);
}
</style>
