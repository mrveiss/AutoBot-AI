<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ChatSessionRow -- one chat in the sidebar history (#18243): a status dot (accent for the open
  chat), the title, the message count, and the row actions in a kit menu (move to folder, share,
  rename, delete). In selection mode it shows a checkbox and no actions. The row is a roving-tabindex
  `role="button"` that ChatSessionList drives; it only reports intents.
-->
<template>
  <div
    class="chat-session-row"
    :class="{ 'chat-session-row--current': current, 'chat-session-row--selected': selected }"
    :tabindex="focused ? 0 : -1"
    :aria-selected="focused"
    :aria-current="current ? 'page' : undefined"
    role="button"
    @click="emit('open')"
    @keydown="emit('keydown', $event)"
    @focus="emit('focus')"
  >
    <input
      v-if="selectionMode"
      type="checkbox"
      class="chat-session-row__check"
      :checked="selected"
      :aria-label="title"
      @click.stop="emit('toggle-select')"
    />
    <span class="chat-session-row__dot" aria-hidden="true" />
    <span class="chat-session-row__title">{{ title }}</span>
    <span class="chat-session-row__meta">{{ $t('chat.sidebar.nMsgs', { count: messageCount }) }}</span>
    <BaseDropdownMenu v-if="!selectionMode" :items="menuItems" size="sm" align="end" @select="onMenuSelect">
      <template #trigger>
        <BaseButton
          class="chat-session-row__actions"
          variant="ghost"
          size="xs"
          :aria-label="$t('chat.sidebar.sessionActions')"
          tabindex="-1"
          @click.stop
        >
          <Icon name="ellipsis-h" />
        </BaseButton>
      </template>
    </BaseDropdownMenu>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseButton, BaseDropdownMenu } from '@autobot/ui'
import type { MenuItem } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'

const FOLDER_PREFIX = 'folder:'
const NO_FOLDER = `${FOLDER_PREFIX}none`

const props = defineProps<{
  title: string
  messageCount: number
  current: boolean
  selected: boolean
  selectionMode: boolean
  focused: boolean
  folders: { id: string; name: string }[]
}>()

const emit = defineEmits<{
  open: []
  'toggle-select': []
  focus: []
  keydown: [event: KeyboardEvent]
  share: []
  rename: []
  delete: []
  'assign-folder': [folderId: string | null]
}>()

const { t } = useI18n()

const menuItems = computed<MenuItem[]>(() => [
  { key: 'share', label: t('common.share') },
  { key: 'rename', label: t('chat.editName') },
  { key: NO_FOLDER, label: t('chat.folders.removeFromFolder'), separatorBefore: true },
  ...props.folders.map((f) => ({ key: `${FOLDER_PREFIX}${f.id}`, label: t('chat.sidebar.moveToFolder', { name: f.name }) })),
  { key: 'delete', label: t('common.delete'), variant: 'danger' as const, separatorBefore: true },
])

function onMenuSelect(key: string): void {
  if (key === 'share') emit('share')
  else if (key === 'rename') emit('rename')
  else if (key === 'delete') emit('delete')
  else if (key.startsWith(FOLDER_PREFIX)) emit('assign-folder', key === NO_FOLDER ? null : key.slice(FOLDER_PREFIX.length))
}
</script>

<style scoped>
.chat-session-row {
  display: flex;
  align-items: center;
  gap: var(--aui-space-2);
  padding: var(--aui-space-2) var(--aui-space-3);
  border: 1px solid transparent;
  border-radius: var(--aui-radius-md);
  font-size: var(--aui-text-sm);
  color: var(--aui-color-text);
  cursor: pointer;
}

.chat-session-row:hover {
  background: var(--surface2);
}

.chat-session-row--current {
  background: var(--surface2);
  border-color: var(--aui-color-border);
  font-weight: var(--aui-font-weight-medium);
}

.chat-session-row--selected {
  border-color: var(--aui-color-primary);
}

.chat-session-row:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: 2px;
}

.chat-session-row__dot {
  flex-shrink: 0;
  inline-size: 0.5rem;
  block-size: 0.5rem;
  border-radius: var(--aui-radius-full);
  background: var(--aui-color-border-strong);
}

.chat-session-row--current .chat-session-row__dot {
  background: var(--aui-color-primary);
}

.chat-session-row__title {
  flex-grow: 1;
  min-inline-size: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-session-row__meta {
  flex-shrink: 0;
  font-size: var(--aui-text-xs);
  font-weight: 400;
  color: var(--aui-color-text-muted);
}

/* Shown on hover and keyboard focus within the row; always reachable by the menu key. */
.chat-session-row__actions {
  opacity: 0;
}

.chat-session-row:hover .chat-session-row__actions,
.chat-session-row:focus-within .chat-session-row__actions,
.chat-session-row__actions[aria-expanded='true'] {
  opacity: 1;
}
</style>
