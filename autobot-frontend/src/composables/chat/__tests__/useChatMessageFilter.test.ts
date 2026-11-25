// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Which messages the stream shows (#650): display settings gate the typed kinds; the empty state never flashes back.
import { describe, it, expect } from 'vitest'
import { nextTick, reactive } from 'vue'
import { filterMessages, isMessageShown, useChatMessageFilter } from '../useChatMessageFilter'
import type { ChatMessage } from '@/stores/useChatStore'

const msg = (id: string, over: Record<string, unknown> = {}) =>
  ({ id, sender: 'assistant', content: 'x', timestamp: 't', ...over }) as unknown as ChatMessage
const off = {}
const on = { showUtility: true, showThoughts: true, showPlanning: true, showDebug: true, showSources: true, showJson: true }

describe('isMessageShown', () => {
  it.each([
    ['utility', 'showUtility'], ['thought', 'showThoughts'], ['planning', 'showPlanning'],
    ['debug', 'showDebug'], ['sources', 'showSources'], ['json', 'showJson'],
  ])('%s is hidden until %s is on', (type, setting) => {
    expect(isMessageShown(msg('1', { type }), off)).toBe(false)
    expect(isMessageShown(msg('1', { type }), { [setting]: true })).toBe(true)
  })

  it('always shows regular responses and reads metadata.display_type', () => {
    expect(isMessageShown(msg('1'), off)).toBe(true)
    expect(isMessageShown(msg('1', { type: 'overseer_plan' }), off)).toBe(true)
    expect(isMessageShown(msg('1', { metadata: { display_type: 'debug' } }), off)).toBe(false)
  })

  it('keeps the order of the visible messages', () => {
    const list = [msg('a'), msg('b', { type: 'debug' }), msg('c')]
    expect(filterMessages(list, off).map((m) => m.id)).toEqual(['a', 'c'])
    expect(filterMessages(list, on).map((m) => m.id)).toEqual(['a', 'b', 'c'])
  })
})

describe('useChatMessageFilter empty state', () => {
  it('shows only while empty, idle and never had a message; then never again in that session', async () => {
    const store = reactive({ currentMessages: [] as ChatMessage[], currentSessionId: 's1', isTyping: false })
    const { showEmptyState } = useChatMessageFilter(store, { value: off })
    expect(showEmptyState.value).toBe(true)
    store.currentMessages = [msg('a')]
    await nextTick()
    expect(showEmptyState.value).toBe(false)
    store.currentMessages = []
    await nextTick()
    expect(showEmptyState.value).toBe(false)
  })

  it('resets on a session change to an empty session, and hides while typing', async () => {
    const store = reactive({ currentMessages: [msg('a')], currentSessionId: 's1', isTyping: false })
    const { showEmptyState } = useChatMessageFilter(store, { value: off })
    store.currentMessages = []
    store.currentSessionId = 's2'
    await nextTick()
    expect(showEmptyState.value).toBe(true)
    store.isTyping = true
    expect(showEmptyState.value).toBe(false)
  })
})
