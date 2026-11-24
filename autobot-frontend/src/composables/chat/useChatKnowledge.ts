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
 * (no session yet) moves to the session that message creates -- only that one: the composer marks the send
 * (`expectDraftAdoption`), so an existing chat opened later never inherits it. Several tabs share the stored
 * map; a change another tab makes is re-read on the `storage` event, and within one tab the last writer wins.
 */
import { computed, onScopeDispose, getCurrentScope, reactive, watch, type WritableComputedRef } from 'vue'
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
let adoptionPending = false // the composer's send is about to create the session the draft choice belongs to
let storageListeners = 0 // scopes using the shared listener; it is removed only when the last one ends

/** Called by the composer when a send starts with no chat open. */
export function expectDraftAdoption(): void {
  adoptionPending = true
}

/** The send ended without creating a session: no chat is waiting for the draft choice. */
export function cancelDraftAdoption(): void {
  adoptionPending = false
}

/** Replace the in-memory map with what another tab stored. */
function syncFromStorage(event: StorageEvent): void {
  if (event.key !== null && event.key !== KNOWLEDGE_STORAGE_KEY) return
  Object.keys(states).forEach((k) => delete states[k])
  Object.assign(states, read())
}

/** One `storage` listener shared by every instance, removed when the last scope using it ends. */
function listenToOtherTabs(): void {
  if (storageListeners++ === 0) window.addEventListener('storage', syncFromStorage)
  onScopeDispose(() => {
    if (--storageListeners === 0) window.removeEventListener('storage', syncFromStorage)
  })
}

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
  adoptionPending = false // the listener count is left alone: it follows live scopes
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

  // A draft choice follows the first message into the session it creates; any other session discards it.
  watch(() => store.currentSessionId, (id, previous) => {
    if (!id || previous) return
    const adopt = adoptionPending
    adoptionPending = false // consumed by the first session that appears, whatever it is
    if (states[DRAFT] === undefined) return
    if (adopt && states[id] === undefined) states[id] = states[DRAFT]
    delete states[DRAFT]
    persist()
  })
  if (getCurrentScope()) listenToOtherTabs()

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
