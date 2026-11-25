// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Which messages the stream shows, and when the empty state may show (#18243).
 * Moved out of ChatMessages.vue unchanged.
 */
import { computed, ref, watch } from 'vue'
import { visibleMessages } from '@/utils/internalMessage'
import type { ChatMessage } from '@/stores/useChatStore'

export interface DisplaySettingsLike {
  showUtility?: boolean
  showThoughts?: boolean
  showPlanning?: boolean
  showDebug?: boolean
  showSources?: boolean
  showJson?: boolean
}

/** display type -> the display setting that gates it. */
const GATES: Record<string, keyof DisplaySettingsLike> = {
  utility: 'showUtility',
  thought: 'showThoughts',
  planning: 'showPlanning',
  debug: 'showDebug',
  sources: 'showSources',
  json: 'showJson',
}

/** Issue #650: both the top-level type and `metadata.display_type` count. */
export function isMessageShown(message: ChatMessage, settings: DisplaySettingsLike): boolean {
  const displayType = message.type || message.metadata?.display_type || 'response'
  const gate = GATES[String(displayType)]
  return gate ? !!settings[gate] : true
}

export function filterMessages(messages: ChatMessage[], settings: DisplaySettingsLike): ChatMessage[] {
  return visibleMessages(messages).filter((message) => isMessageShown(message, settings)) // #21846
}

interface StoreLike {
  currentMessages: ChatMessage[]
  currentSessionId: string | null
  isTyping: boolean
}

/** The EmptyState never flashes back once the session has had messages (prevents polling flicker). */
export function useChatMessageFilter(store: StoreLike, settings: { value: DisplaySettingsLike }) {
  const hasEverHadMessages = ref(false)

  watch(() => store.currentMessages.length, (len) => {
    if (len > 0) hasEverHadMessages.value = true
  }, { immediate: true })

  watch(() => store.currentSessionId, () => {
    if (store.currentMessages.length === 0) hasEverHadMessages.value = false
  })

  const showEmptyState = computed(
    () => store.currentMessages.length === 0 && !hasEverHadMessages.value && !store.isTyping,
  )
  const filteredMessages = computed(() => filterMessages(store.currentMessages, settings.value))
  return { filteredMessages, showEmptyState, hasEverHadMessages }
}
