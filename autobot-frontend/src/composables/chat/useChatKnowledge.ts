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
 * (no session yet) is held in this tab only -- never stored, so no other tab can see or change an unsent
 * draft -- and moves to the session that message creates: only a session that did not exist when the send
 * started (the composer marks the send, `expectDraftAdoption`), so an existing chat opened later never
 * inherits it. Several tabs share the stored map; each write merges into what is stored now, so another
 * tab's completed choice survives, and a change another tab makes is re-read on the `storage` event.
 */
import { computed, onScopeDispose, getCurrentScope, reactive, watch, type WritableComputedRef } from 'vue'
import { useChatStore } from '@/stores/useChatStore'

export const KNOWLEDGE_STORAGE_KEY = 'autobot_chat_knowledge_by_session'
export const MAX_REMEMBERED_SESSIONS = 200

/** The stored map, or null when storage is unreadable (the caller then keeps what it holds in memory). */
function read(): Record<string, boolean> | null {
  try {
    const raw = JSON.parse(localStorage.getItem(KNOWLEDGE_STORAGE_KEY) ?? '{}')
    return raw && typeof raw === 'object' ? raw : {}
  } catch {
    return null
  }
}

const states = reactive<Record<string, boolean>>(read() ?? {})
const draft = reactive<{ value: boolean | undefined }>({ value: undefined }) // this tab only, never stored
let adoptionBaseline: Set<string> | null = null // the sessions that existed when the send started
let storageListeners = 0 // scopes using the shared listener; it is removed only when the last one ends

function replaceStates(next: Record<string, boolean>): void {
  Object.keys(states).forEach((k) => delete states[k])
  Object.assign(states, next)
}

/** Called by the composer when a send starts with no chat open. */
export function expectDraftAdoption(): void {
  adoptionBaseline = new Set(useChatStore().sessions.map((s) => s.id))
}

/** The send ended without creating a session: no chat is waiting for the draft choice. */
export function cancelDraftAdoption(): void {
  adoptionBaseline = null
}

/** Replace the in-memory map with what another tab stored. */
function syncFromStorage(event: StorageEvent): void {
  if (event.key !== null && event.key !== KNOWLEDGE_STORAGE_KEY) return
  const stored = read()
  if (stored) replaceStates(stored)
}

/** One `storage` listener shared by every instance, removed when the last scope using it ends. */
function listenToOtherTabs(): void {
  if (storageListeners++ === 0) {
    const stored = read() // no storage event replays what changed while nobody listened
    if (stored) replaceStates(stored)
    window.addEventListener('storage', syncFromStorage)
  }
  onScopeDispose(() => {
    if (--storageListeners === 0) window.removeEventListener('storage', syncFromStorage)
  })
}

/** Store one session's choice (`undefined` forgets it), merged into the map as stored right now. */
function persist(id: string, value: boolean | undefined): void {
  const next = read() ?? { ...states }
  delete next[id] // re-insert so the newest choice is the last to be evicted
  if (value !== undefined) next[id] = value
  const keys = Object.keys(next)
  keys.slice(0, Math.max(0, keys.length - MAX_REMEMBERED_SESSIONS)).forEach((k) => delete next[k]) // oldest first
  replaceStates(next)
  try {
    localStorage.setItem(KNOWLEDGE_STORAGE_KEY, JSON.stringify(next))
  } catch {
    // storage unavailable: the state still holds for this page
  }
}

/** Forget every remembered choice (specs; also what a storage clear amounts to). */
export function resetChatKnowledgeState(): void {
  adoptionBaseline = null // the listener count is left alone: it follows live scopes
  draft.value = undefined
  replaceStates({})
  try {
    localStorage.removeItem(KNOWLEDGE_STORAGE_KEY)
  } catch {
    // nothing to clear
  }
}

/** Where this tab's choice lives: the open session's stored entry, or the unsent draft with none open. */
function choiceFor(id: string | null): boolean | undefined {
  return id ? states[id] : draft.value
}

function storeChoice(id: string | null, value: boolean | undefined): void {
  if (id) persist(id, value)
  else draft.value = value
}

/** A draft choice follows the send into the session it creates; opening any other chat discards it. */
function settleDraft(id: string, previous: string | null | undefined): void {
  if (adoptionBaseline && adoptionBaseline.has(id)) return // an existing chat opened mid-send: the new one is still to come
  const adopt = adoptionBaseline !== null
  adoptionBaseline = null // consumed by the session the send created
  if (!adopt && previous) return
  if (adopt && draft.value !== undefined && states[id] === undefined) persist(id, draft.value)
  draft.value = undefined
}

export function useChatKnowledge(): { enabled: WritableComputedRef<boolean> } {
  const store = useChatStore()
  watch(() => store.currentSessionId, (id, previous) => { if (id) settleDraft(id, previous) })
  if (getCurrentScope()) listenToOtherTabs()

  const enabled = computed<boolean>({
    get: () => choiceFor(store.currentSessionId) ?? true, // on by default, as before
    set: (value) => storeChoice(store.currentSessionId, value),
  })
  return { enabled }
}
