// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Auto-scroll plus the screen-reader announcement for a new message (#1312, #18243).
 * One watcher on the array LENGTH only (O(1) per streaming chunk). Moved out of ChatMessages.vue.
 */
import { nextTick, onScopeDispose, ref, watch } from 'vue'
import type { ChatMessage } from '@/stores/useChatStore'

const ANNOUNCE_CLEAR_MS = 2000

/**
 * Plain-text preview. The HTML is parsed into an inert document (scripts never run there) and only its
 * text is read, so no markup can survive the way it can through a single-pass tag-stripping regex.
 */
export function announcementPreview(message: ChatMessage): string {
  const parsed = new DOMParser().parseFromString(message.content.substring(0, 200), 'text/html')
  const preview = (parsed.body.textContent ?? '').substring(0, 100)
  return `${preview}${preview.length < message.content.length ? '...' : ''}`
}

export function useChatScreenReader(
  store: { currentMessages: ChatMessage[] },
  scrollToBottom: () => void,
  /** Builds the full, translated announcement from the sender id and the plain-text preview. */
  announce: (sender: string, preview: string) => string,
) {
  const screenReaderStatus = ref('')
  let clearTimer: ReturnType<typeof setTimeout> | undefined
  onScopeDispose(() => clearTimeout(clearTimer))

  watch(() => store.currentMessages.length, (newLen, oldLen) => {
    nextTick(scrollToBottom)
    if (newLen <= (oldLen || 0)) return
    const latest = store.currentMessages[newLen - 1]
    if (!latest) return
    screenReaderStatus.value = announce(latest.sender, announcementPreview(latest))
    clearTimeout(clearTimer)
    clearTimer = setTimeout(() => { screenReaderStatus.value = '' }, ANNOUNCE_CLEAR_MS)
  })

  return { screenReaderStatus }
}
