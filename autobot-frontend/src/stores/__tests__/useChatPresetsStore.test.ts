// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useChatPresetsStore } from '../useChatPresetsStore'
import type { SlashCommandPreset } from '@/types/api'

const mockPreset = (overrides: Partial<SlashCommandPreset> = {}): SlashCommandPreset => ({
  id: 'preset-1',
  name: 'greet',
  description: 'Greeting template',
  content: 'Hello! How can I help you today?',
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
  ...overrides,
})

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({
    get: vi.fn().mockResolvedValue([mockPreset()]),
    post: vi.fn().mockResolvedValue(mockPreset({ id: 'preset-2', name: 'help' })),
    put: vi.fn().mockResolvedValue(mockPreset({ description: 'Updated' })),
    delete: vi.fn().mockResolvedValue(undefined),
  }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ error: vi.fn(), info: vi.fn(), warn: vi.fn() }),
}))

describe('useChatPresetsStore (GH#8596)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('starts with empty presets', () => {
    const store = useChatPresetsStore()
    expect(store.presets).toEqual([])
    expect(store.isLoading).toBe(false)
    expect(store.error).toBeNull()
  })

  it('fetchPresets populates presets from API', async () => {
    const store = useChatPresetsStore()
    await store.fetchPresets()
    expect(store.presets).toHaveLength(1)
    expect(store.presets[0].name).toBe('greet')
  })

  it('fetchPresets sets isLoading during request', async () => {
    const store = useChatPresetsStore()
    const promise = store.fetchPresets()
    expect(store.isLoading).toBe(true)
    await promise
    expect(store.isLoading).toBe(false)
  })

  it('sortedPresets returns alphabetically sorted list', () => {
    const store = useChatPresetsStore()
    store.presets = [
      mockPreset({ id: '2', name: 'zebra' }),
      mockPreset({ id: '1', name: 'apple' }),
    ]
    expect(store.sortedPresets[0].name).toBe('apple')
    expect(store.sortedPresets[1].name).toBe('zebra')
  })

  it('filterByQuery filters by name prefix', () => {
    const store = useChatPresetsStore()
    store.presets = [
      mockPreset({ name: 'greet', description: 'A greeting' }),
      mockPreset({ id: '2', name: 'summarize', description: 'A summary' }),
    ]
    expect(store.filterByQuery('gr')).toHaveLength(1)
    expect(store.filterByQuery('gr')[0].name).toBe('greet')
  })

  it('filterByQuery matches description when name does not match', () => {
    const store = useChatPresetsStore()
    store.presets = [mockPreset({ name: 'greet', description: 'morning salutation' })]
    expect(store.filterByQuery('salutation')).toHaveLength(1)
  })

  it('filterByQuery returns all presets on empty query', () => {
    const store = useChatPresetsStore()
    store.presets = [
      mockPreset({ name: 'a' }),
      mockPreset({ id: '2', name: 'b' }),
    ]
    expect(store.filterByQuery('')).toHaveLength(2)
  })

  it('createPreset appends to presets list', async () => {
    const store = useChatPresetsStore()
    const result = await store.createPreset({ name: 'help', description: 'Help', content: 'How can I help?' })
    expect(result).not.toBeNull()
    expect(store.presets).toHaveLength(1)
    expect(store.presets[0].id).toBe('preset-2')
  })

  it('updatePreset replaces the matching preset in list', async () => {
    const store = useChatPresetsStore()
    store.presets = [mockPreset()]
    const result = await store.updatePreset('preset-1', { description: 'Updated' })
    expect(result).not.toBeNull()
    expect(store.presets[0].description).toBe('Updated')
  })

  it('deletePreset removes the preset from the list', async () => {
    const store = useChatPresetsStore()
    store.presets = [mockPreset()]
    const result = await store.deletePreset('preset-1')
    expect(result).toBe(true)
    expect(store.presets).toHaveLength(0)
  })

  it('createPreset clears stale error before starting (GH#9070)', async () => {
    const store = useChatPresetsStore()
    store.error = 'previous error'
    await store.createPreset({ name: 'help', description: 'Help', content: 'How can I help?' })
    expect(store.error).toBeNull()
  })

  it('updatePreset clears stale error before starting (GH#9070)', async () => {
    const store = useChatPresetsStore()
    store.presets = [mockPreset()]
    store.error = 'previous error'
    await store.updatePreset('preset-1', { description: 'Updated' })
    expect(store.error).toBeNull()
  })

  it('deletePreset clears stale error before starting (GH#9070)', async () => {
    const store = useChatPresetsStore()
    store.presets = [mockPreset()]
    store.error = 'previous error'
    await store.deletePreset('preset-1')
    expect(store.error).toBeNull()
  })
})
