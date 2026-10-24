// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * ChromaDBExplorer labels research-quarantined rows (#19163).
 *
 * The admin documents and search endpoints return `quarantined_ids` / a per-row `quarantined`
 * flag; the explorer must surface it so an admin never reads a quarantined research fact as trusted.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

const apiClient = { get: vi.fn(), post: vi.fn() }
vi.mock('@/plugins/api', () => ({ useApiClient: () => apiClient }))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
}))

import ChromaDBExplorer from '../ChromaDBExplorer.vue'

const BADGE_KEY = 'knowledge.chroma.quarantined'

function arrange(): void {
  apiClient.get.mockImplementation(async (url: string) =>
    url.endsWith('/collections')
      ? { success: true, data: [{ name: 'kb', count: 2, metadata: null }] }
      : {
          success: true,
          total: 2,
          data: {
            ids: ['good', 'held'],
            documents: ['trusted text', 'research text'],
            metadatas: [{}, { collection: 'research' }],
            embedding_dim: 384,
            quarantined_ids: ['held'],
          },
        },
  )
  apiClient.post.mockResolvedValue({
    success: true,
    data: [
      { id: 'good', document: 'a', metadata: null, distance: 0.1, quarantined: false },
      { id: 'held', document: 'b', metadata: null, distance: 0.2, quarantined: true },
    ],
  })
}

async function openCollection() {
  const wrapper = mount(ChromaDBExplorer)
  await flushPromises()
  await wrapper.find('.collection-item, .collections-list button').trigger('click')
  await flushPromises()
  return wrapper
}

describe('ChromaDBExplorer quarantine labelling', () => {
  beforeEach(() => {
    apiClient.get.mockReset()
    apiClient.post.mockReset()
    arrange()
  })

  it('labels only the document rows listed in quarantined_ids', async () => {
    const wrapper = await openCollection()
    const rows = wrapper.findAll('.document-item')
    expect(rows.map((r) => r.find('.document-id').text())).toEqual(['good', 'held'])
    expect(rows.map((r) => r.text().includes(BADGE_KEY))).toEqual([false, true])
  })

  it('labels only the search results the server flagged quarantined', async () => {
    const wrapper = await openCollection()
    await wrapper.find('.search-input').setValue('q')
    await wrapper.find('.search-btn').trigger('click')
    await flushPromises()
    const rows = wrapper.findAll('.search-result-item')
    expect(rows.map((r) => r.text().includes(BADGE_KEY))).toEqual([false, true])
  })
})
