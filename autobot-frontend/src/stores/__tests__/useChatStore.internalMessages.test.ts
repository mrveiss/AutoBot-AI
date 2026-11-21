// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #21846 — backend-internal bookkeeping messages never reach a selector consumer (counts, previews, export)
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useChatStore } from '../useChatStore'

describe('useChatStore internal messages', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('currentMessages excludes messages flagged metadata.internal', () => {
    const store = useChatStore()
    store.createNewSession('Internal')
    store.addMessage({ content: 'hello', sender: 'user' })
    store.addMessage({ content: '', sender: 'assistant', metadata: { internal: true } })
    store.addMessage({ content: 'the reply', sender: 'assistant' })

    expect(store.currentMessages.map((m) => m.content)).toEqual(['hello', 'the reply'])
  })
})
