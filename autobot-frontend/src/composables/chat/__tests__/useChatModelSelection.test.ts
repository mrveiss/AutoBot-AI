// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Tests for useChatModelSelection (#11585 — per-request/per-conversation
// model & provider override picker).

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick, ref } from 'vue'
import type { AvailableModel } from '../../useAvailableModels'

const mockModels = ref<AvailableModel[]>([])

vi.mock('../../useAvailableModels', () => ({
  useAvailableModels: () => ({
    models: mockModels,
    isLoading: ref(false),
    error: ref(null),
    fetchModels: vi.fn().mockResolvedValue(undefined),
  }),
}))

import { useChatModelSelection } from '../useChatModelSelection'

function makeModel(name: string, provider: string): AvailableModel {
  return { name, provider, available: true, context_window: 8192, capabilities: [] }
}

describe('useChatModelSelection', () => {
  beforeEach(() => {
    localStorage.clear()
    mockModels.value = [makeModel('llama3.2:3b', 'ollama'), makeModel('gpt-4o', 'openai')]
    const { selectedModel } = useChatModelSelection()
    selectedModel.value = ''
  })

  it('sends no override fields when set to auto (empty selection)', () => {
    const { overrideFields } = useChatModelSelection()
    expect(overrideFields.value).toEqual({})
  })

  it('derives provider from live model metadata for the selected model', () => {
    const { selectedModel, selectedProvider, overrideFields } = useChatModelSelection()
    selectedModel.value = 'gpt-4o'
    expect(selectedProvider.value).toBe('openai')
    expect(overrideFields.value).toEqual({ model: 'gpt-4o', provider: 'openai' })
  })

  it('omits provider when the selected model has no live metadata', () => {
    const { selectedModel, overrideFields } = useChatModelSelection()
    selectedModel.value = 'vanished-model'
    expect(overrideFields.value).toEqual({ model: 'vanished-model' })
  })

  it('keeps a persisted selection visible in picker options when not in the live list', () => {
    const { selectedModel, pickerModels } = useChatModelSelection()
    selectedModel.value = 'vanished-model'
    expect(pickerModels.value.map((m) => m.name)).toContain('vanished-model')
  })

  it('picker options match the live list when the selection is live', () => {
    const { selectedModel, pickerModels } = useChatModelSelection()
    selectedModel.value = 'llama3.2:3b'
    expect(pickerModels.value).toHaveLength(2)
  })

  it('persists the selection to localStorage and clears it on auto', async () => {
    const { selectedModel } = useChatModelSelection()
    selectedModel.value = 'llama3.2:3b'
    await nextTick() // flush watcher
    expect(localStorage.getItem('autobot-chat-model-override')).toBe('llama3.2:3b')
    selectedModel.value = ''
    await nextTick()
    expect(localStorage.getItem('autobot-chat-model-override')).toBeNull()
  })
})
