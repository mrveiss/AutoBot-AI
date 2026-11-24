// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Whether answers draw on the knowledge base (RAG, #249) for the CURRENT chat -- the one source for the
 * composer's "Use Knowledge" chip, the `use_knowledge` send option and the chat header's "Knowledge on/off"
 * sub-line (#18243). It is kept per session, like extended thinking (`useThinkingMode`): switching chats shows
 * that chat's own state and a new chat starts on. Unlike thinking mode there is no server preference endpoint,
 * so the state persists in this browser only (localStorage, bounded). A choice made before the first message
 * (no session yet) moves to the session that message creates.
 */
import { computed, reactive, watch, type WritableComputedRef } from 'vue'
import { useChatStore } from '@/stores/useChatStore'

export const KNOWLEDGE_STORAGE_KEY = 'autobot_chat_knowledge_by_session'
export const MAX_REMEMBERED_SESSIONS = 200
const DRAFT = '__draft__'

function read(): Record<string, boolean> {
  try {
    const raw = JSON.parse(localStorage.getItem(KNOWLEDGE_STORAGE_KEY) ?? '{}')
    return raw && typeof raw === 'object' ? raw : {}
  } catch {
    return {}
  }
}

const states = reactive<Record<string, boolean>>(read())

function persist(): void {
  const keys = Object.keys(states)
  keys.slice(0, Math.max(0, keys.length - MAX_REMEMBERED_SESSIONS)).forEach((k) => delete states[k]) // oldest first
  try {
    localStorage.setItem(KNOWLEDGE_STORAGE_KEY, JSON.stringify(states))
  } catch {
    // storage unavailable: the state still holds for this page
  }
}

/** Forget every remembered choice (specs; also what a storage clear amounts to). */
export function resetChatKnowledgeState(): void {
  Object.keys(states).forEach((k) => delete states[k])
  try {
    localStorage.removeItem(KNOWLEDGE_STORAGE_KEY)
  } catch {
    // nothing to clear
  }
}

export function useChatKnowledge(): { enabled: WritableComputedRef<boolean> } {
  const store = useChatStore()
  const key = (): string => store.currentSessionId ?? DRAFT

  // A draft choice follows the first message into the session it creates.
  watch(() => store.currentSessionId, (id, previous) => {
    if (id && !previous && states[DRAFT] !== undefined && states[id] === undefined) {
      states[id] = states[DRAFT]
      delete states[DRAFT]
      persist()
    }
  })

  const enabled = computed<boolean>({
    get: () => states[key()] ?? true, // on by default, as before
    set: (value) => {
      delete states[key()] // re-insert so the newest choice is the last to be evicted
      states[key()] = value
      persist()
    },
  })
  return { enabled }
}
