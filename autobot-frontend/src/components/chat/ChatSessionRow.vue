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
    class="chat-session-row group flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm text-[var(--aui-color-text)] hover:bg-[var(--surface2)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--aui-color-focus-ring)]"
    :class="[
      current ? 'border-[var(--aui-color-border)] bg-[var(--surface2)] font-medium' : 'border-transparent',
      selected && 'border-[var(--aui-color-primary)]',
    ]"
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
      :checked="selected"
      :aria-label="title"
      @click.stop="emit('toggle-select')"
    />
    <span
      class="size-2 shrink-0 rounded-full"
      :class="current ? 'bg-[var(--aui-color-primary)]' : 'bg-[var(--aui-color-border-strong)]'"
      aria-hidden="true"
    />
    <span class="chat-session-row__title min-w-0 grow truncate">{{ title }}</span>
    <span class="shrink-0 text-xs font-normal text-[var(--aui-color-text-muted)]">{{ $t('chat.sidebar.nMsgs', { count: messageCount }) }}</span>
    <BaseDropdownMenu v-if="!selectionMode" :items="menuItems" size="sm" align="end" @select="onMenuSelect">
      <template #trigger>
        <BaseButton
          class="opacity-0 group-focus-within:opacity-100 group-hover:opacity-100 aria-expanded:opacity-100"
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
