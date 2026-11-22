// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/** Main-category state of the Knowledge Browser (#18244): load, fallback, edit modal, Populate. */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const h = vi.hoisted(() => ({
  fetchMainCategories: vi.fn(),
  populateAutoBotDocs: vi.fn().mockResolvedValue({ ok: true }),
  refreshSystemKnowledge: vi.fn().mockResolvedValue({ ok: true }),
}))

vi.mock('@/composables/knowledge/useKnowledgeBrowser', () => ({ fetchMainCategories: h.fetchMainCategories }))
vi.mock('@/composables/knowledge/useManPages', () => ({ useManPages: () => ({ populateAutoBotDocs: h.populateAutoBotDocs }) }))
vi.mock('@/composables/knowledge/useMachineKnowledge', () => ({
  useMachineKnowledge: () => ({ refreshSystemKnowledge: h.refreshSystemKnowledge }),
}))

import { useKnowledgeBrowserCategories } from '../useKnowledgeBrowserCategories'

const CAT = (id: string, count = 1) => ({ id, name: id, description: '', icon: 'book', color: '', count })

beforeEach(() => vi.clearAllMocks())
afterEach(() => vi.useRealTimers())

describe('useKnowledgeBrowserCategories', () => {
  it('loads the cards and the connectivity flag', async () => {
    h.fetchMainCategories.mockResolvedValue({ categories: [CAT('a')], kb_connected: false })
    const c = useKnowledgeBrowserCategories(async () => {})
    await c.loadMainCategories()
    expect(c.mainCategories.value.map((x) => x.id)).toEqual(['a'])
    expect(c.kbConnected.value).toBe(false)
    expect(c.kbFetchError.value).toBe(false)
  })

  it('treats a missing kb_connected as connected', async () => {
    h.fetchMainCategories.mockResolvedValue({ categories: [CAT('a')] })
    const c = useKnowledgeBrowserCategories(async () => {})
    await c.loadMainCategories()
    expect(c.kbConnected.value).toBe(true)
  })

  it('falls back to the three default cards on a fetch error and flags it', async () => {
    h.fetchMainCategories.mockRejectedValue(new Error('500'))
    const c = useKnowledgeBrowserCategories(async () => {})
    await c.loadMainCategories()
    expect(c.kbFetchError.value).toBe(true)
    expect(c.mainCategories.value.map((x) => x.id)).toEqual(['autobot-documentation', 'system-knowledge', 'user-knowledge'])
  })

  it('opens the edit modal on a card, then closes it on update or delete', async () => {
    h.fetchMainCategories.mockResolvedValue({ categories: [CAT('a'), CAT('b')], kb_connected: true })
    const c = useKnowledgeBrowserCategories(async () => {})
    await c.loadMainCategories()
    c.handleEditCategory(c.mainCategories.value[0])
    expect(c.showCategoryEditModal.value).toBe(true)
    c.handleCategoryUpdated({ ...c.mainCategories.value[0], name: 'renamed' } as never)
    expect(c.mainCategories.value[0].name).toBe('renamed')
    expect(c.showCategoryEditModal.value).toBe(false)
    c.handleEditCategory(c.mainCategories.value[1])
    c.handleCategoryDeleted('b')
    expect(c.mainCategories.value.map((x) => x.id)).toEqual(['a'])
    expect(c.categoryToEdit.value).toBeNull()
  })

  it('Populate runs the right source, steps the progress, reloads the tree and resets', async () => {
    vi.useFakeTimers()
    const reload = vi.fn().mockResolvedValue(undefined)
    const c = useKnowledgeBrowserCategories(reload)
    const done = c.handlePopulate('system-knowledge')
    await vi.advanceTimersByTimeAsync(1500)
    expect(c.populationStates.value['system-knowledge']).toEqual({ isPopulating: true, progress: 30 })
    await vi.advanceTimersByTimeAsync(5000)
    await done
    expect(h.refreshSystemKnowledge).toHaveBeenCalledTimes(1)
    expect(h.populateAutoBotDocs).not.toHaveBeenCalled()
    expect(reload).toHaveBeenCalledTimes(1)
    expect(c.populationStates.value['system-knowledge']).toEqual({ isPopulating: false, progress: 0 })
  })

  it('ignores a second Populate while one is running', async () => {
    vi.useFakeTimers()
    const c = useKnowledgeBrowserCategories(async () => {})
    const first = c.handlePopulate('autobot-documentation')
    await c.handlePopulate('autobot-documentation')
    expect(h.populateAutoBotDocs).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(5000)
    await first
  })
})
