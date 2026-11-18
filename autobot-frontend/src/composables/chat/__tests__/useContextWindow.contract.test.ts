// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// The model-list contract end to end: the window the backend list carries reaches useContextWindow through
// the real useAvailableModels, and a failed request is reported apart from an unlisted model (#20884).

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const get = vi.fn()

vi.mock('@/utils/ApiClient', () => ({ default: { get: (...args: unknown[]) => get(...args) } }))

import { useContextWindow } from '../useContextWindow'

const messages = ref([{ metadata: { tokens: 1000 } }] as never)
const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

describe('useContextWindow with the real model list', () => {
  beforeEach(() => {
    get.mockReset()
  })

  it('carries the fetched Claude window to the indicator', async () => {
    get.mockResolvedValue({
      models: [
        { name: 'claude-test-model', provider: 'anthropic', available: true, context_window: 1_000_000, capabilities: [] },
      ],
      providers_queried: ['anthropic'],
      providers_errored: [],
    })
    const state = useContextWindow(messages, ref('claude-test-model'))
    await flush()
    expect(state.contextWindow.value).toBe(1_000_000)
    expect(state.loadError.value).toBeNull()
  })

  it('reports the request failure for a model that has no window', async () => {
    get.mockRejectedValue(new Error('boom'))
    const state = useContextWindow(messages, ref('claude-test-model'))
    await flush()
    expect(state.contextWindow.value).toBe(0)
    expect(state.loadError.value).toBe('boom')
  })
})
