<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ChatSessionList -- the scrollable chat history of the sidebar (#18243): one ChatSessionRow per
  session with roving-tabindex keyboard navigation (Arrow, Home, End, Enter, Space), and the two
  empty states. Opening, selecting and the row actions are reported to the parent.
-->
<template>
  <div class="chat-session-list">
    <ChatSessionRow
      v-for="(session, index) in sessions"
      :key="session.id"
      :ref="(row) => setRowRef(row, index)"
      :title="titleOf(session)"
      :message-count="session.messages.length"
      :current="currentSessionId === session.id && !selectionMode"
      :selected="isSelected(session)"
      :selection-mode="selectionMode"
      :focused="index === focusedIndex"
      :folders="folders"
      @open="open(session, index)"
      @toggle-select="emit('toggle-select', session)"
      @focus="focusedIndex = index"
      @keydown="onKeydown($event, session, index)"
      @share="emit('share', session.id)"
      @rename="emit('rename', session)"
      @delete="emit('delete', session.id)"
      @assign-folder="emit('assign-folder', session.id, $event)"
    />
    <EmptyState v-if="totalCount === 0" compact :description="$t('chat.sidebar.noSessions')">
      <template #icon><Icon name="comments" size="xl" /></template>
    </EmptyState>
    <EmptyState v-else-if="sessions.length === 0" compact :description="$t('chat.sidebar.noSearchResults')">
      <template #icon><Icon name="search" size="xl" /></template>
    </EmptyState>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { EmptyState } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import ChatSessionRow from './ChatSessionRow.vue'
import type { ChatSession } from '@/stores/useChatStore'

const props = defineProps<{
  sessions: ChatSession[]
  /** All sessions, before the search filter: tells "no chats yet" from "nothing matches". */
  totalCount: number
  currentSessionId: string | null
  selectionMode: boolean
  isSelected: (session: ChatSession) => boolean
  titleOf: (session: ChatSession) => string
  folders: { id: string; name: string }[]
}>()

const emit = defineEmits<{
  open: [session: ChatSession]
  'toggle-select': [session: ChatSession]
  share: [sessionId: string]
  rename: [session: ChatSession]
  delete: [sessionId: string]
  'assign-folder': [sessionId: string, folderId: string | null]
}>()

const focusedIndex = ref(0)
const rowEls = ref<(HTMLElement | null)[]>([])

function setRowRef(row: unknown, index: number): void {
  const el = (row as { $el?: HTMLElement } | null)?.$el
  if (el) rowEls.value[index] = el
}

/** A mouse click or keyboard activation: select in selection mode, open otherwise. */
function open(session: ChatSession, index: number): void {
  focusedIndex.value = index
  if (props.selectionMode) emit('toggle-select', session)
  else emit('open', session)
}

function moveFocus(index: number): void {
  focusedIndex.value = index
  void nextTick(() => rowEls.value[index]?.focus())
}

function targetIndex(key: string, index: number): number | null {
  const last = props.sessions.length - 1
  if (key === 'ArrowDown') return index < last ? index + 1 : null
  if (key === 'ArrowUp') return index > 0 ? index - 1 : null
  if (key === 'Home') return 0
  if (key === 'End') return last
  return null
}

function onKeydown(event: KeyboardEvent, session: ChatSession, index: number): void {
  if (event.target !== event.currentTarget) return
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    open(session, index)
    return
  }
  if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const next = targetIndex(event.key, index)
  if (next !== null) moveFocus(next)
}
</script>

<style scoped>
.chat-session-list {
  display: flex;
  flex-direction: column;
  gap: var(--aui-space-1);
}
</style>
