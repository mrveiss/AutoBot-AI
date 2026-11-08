// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// useContextWindow: a Claude window comes from the backend model list, never a frontend number (#20884).

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import type { AvailableModel } from '../../useAvailableModels'

const mockModels = ref<AvailableModel[]>([])
const mockError = ref<string | null>(null)

vi.mock('@/composables/useAvailableModels', () => ({
  useAvailableModels: () => ({
    models: mockModels,
    fetchModels: vi.fn().mockResolvedValue(undefined),
    error: mockError,
  }),
}))

import { useContextWindow } from '../useContextWindow'

const messages = ref([{ metadata: { tokens: 1000 } }] as never)

describe('useContextWindow', () => {
  beforeEach(() => {
    mockModels.value = []
    mockError.value = null
  })

  it('takes a Claude window from the live model list', () => {
    mockModels.value = [
      { name: 'claude-test-model', provider: 'anthropic', available: true, context_window: 1_000_000, capabilities: [] },
    ]
    const { contextWindow } = useContextWindow(messages, ref('claude-test-model'))
    expect(contextWindow.value).toBe(1_000_000)
  })

  it('reports a Claude model absent from the list as unknown, not a guessed number', () => {
    const { contextWindow, hasData } = useContextWindow(messages, ref('claude-test-model'))
    expect(contextWindow.value).toBe(0)
    expect(hasData.value).toBe(false)
  })

  it('keeps the non-Claude fallback when the list is empty', () => {
    const { contextWindow } = useContextWindow(messages, ref('gpt-4o'))
    expect(contextWindow.value).toBe(128_000)
  })

  it('reports a failed model-list request apart from an unlisted model', () => {
    const unlisted = useContextWindow(messages, ref('claude-test-model'))
    expect(unlisted.loadError.value).toBeNull()
    mockError.value = 'network down'
    expect(unlisted.loadError.value).toBe('network down')
  })
})
