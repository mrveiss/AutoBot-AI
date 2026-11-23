// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Auto-scroll plus the screen-reader announcement for a new message (#1312, #18243).
 * One watcher on the array LENGTH only (O(1) per streaming chunk). Moved out of ChatMessages.vue.
 */
import { nextTick, ref, watch } from 'vue'
import { sanitizeChatHtml } from '@/utils/sanitize'
import type { ChatMessage } from '@/stores/useChatStore'

const ANNOUNCE_CLEAR_MS = 2000

/** Plain-text preview: DOMPurify-backed sanitiser first, then any remaining tag is stripped. */
export function announcementText(message: ChatMessage, senderName: string): string {
  const preview = sanitizeChatHtml(message.content.substring(0, 200))
    .replace(/<[^>]*>/g, '')
    .substring(0, 100)
  return `New message from ${senderName}: ${preview}${preview.length < message.content.length ? '...' : ''}`
}

export function useChatScreenReader(
  store: { currentMessages: ChatMessage[] },
  scrollToBottom: () => void,
  senderName: (sender: string) => string,
) {
  const screenReaderStatus = ref('')

  watch(() => store.currentMessages.length, (newLen, oldLen) => {
    nextTick(scrollToBottom)
    if (newLen <= (oldLen || 0)) return
    const latest = store.currentMessages[newLen - 1]
    if (!latest) return
    screenReaderStatus.value = announcementText(latest, senderName(latest.sender))
    setTimeout(() => { screenReaderStatus.value = '' }, ANNOUNCE_CLEAR_MS)
  })

  return { screenReaderStatus }
}
