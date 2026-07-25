// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Coverage for #12386 — the #12376 repoint of KnowledgeRepository.updateDocument.
 *
 * PR #12376 moved fact updates to PUT /api/knowledge-maintenance/fact/{id} and
 * changed the body to match UpdateFactRequest: `content` and `category` stay
 * top-level, while `title`/`source`/`tags` are folded into `metadata` (merged,
 * not clobbering caller-supplied metadata) so they actually persist.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { KnowledgeRepository } from '../KnowledgeRepository'
import type { KnowledgeDocument } from '../KnowledgeRepository'

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api'
}))

describe('KnowledgeRepository.updateDocument (#12386)', () => {
  let repo: KnowledgeRepository
  let putSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    repo = new KnowledgeRepository()
    putSpy = vi.fn().mockResolvedValue({ data: {} as KnowledgeDocument })
    // @ts-expect-error - override inherited method for unit test isolation
    repo.put = putSpy
  })

  it('PUTs to /api/knowledge-maintenance/fact/{id} with content/category top-level and title/source/tags under metadata', async () => {
    await repo.updateDocument('id1', {
      title: 'T',
      source: 'S',
      tags: ['x'],
      content: 'C',
      category: 'K'
    } as Partial<KnowledgeDocument>)

    expect(putSpy).toHaveBeenCalledWith('/api/knowledge-maintenance/fact/id1', {
      content: 'C',
      category: 'K',
      metadata: {
        title: 'T',
        source: 'S',
        tags: ['x']
      }
    })
  })

  it('merges title/source/tags into caller-supplied metadata without clobbering it', async () => {
    await repo.updateDocument('id2', {
      title: 'T',
      metadata: { existing: 'keep', title: 'old' }
    } as Partial<KnowledgeDocument>)

    const [, body] = putSpy.mock.calls[0] as [string, Record<string, unknown>]
    expect(body.metadata).toEqual({ existing: 'keep', title: 'T' })
    // content/category omitted when not supplied
    expect(body).not.toHaveProperty('content')
    expect(body).not.toHaveProperty('category')
  })

  it('keeps title/source/tags out of the top-level body', async () => {
    await repo.updateDocument('id3', {
      title: 'T',
      source: 'S',
      tags: ['a', 'b'],
      content: 'C'
    } as Partial<KnowledgeDocument>)

    const [, body] = putSpy.mock.calls[0] as [string, Record<string, unknown>]
    expect(body).not.toHaveProperty('title')
    expect(body).not.toHaveProperty('source')
    expect(body).not.toHaveProperty('tags')
    expect(body.content).toBe('C')
  })
})
