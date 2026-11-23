// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #21989: selected-delete proposal: the selection cap, the empty path, the proposal call and the failure message.
import { describe, it, expect, beforeEach, vi } from 'vitest'

const { bulkDeleteDocuments, watchApprovedDelete } = vi.hoisted(() => ({
  bulkDeleteDocuments: vi.fn(),
  watchApprovedDelete: vi.fn(),
}))

vi.mock('@/i18n', () => ({
  default: {
    global: {
      t: (key: string, params?: Record<string, unknown>) =>
        params ? `${key}|${JSON.stringify(params)}` : key,
    },
  },
}))
vi.mock('@/models/repositories/KnowledgeRepository', () => ({
  knowledgeRepository: { bulkDeleteDocuments },
}))
vi.mock('../approvedDeleteWatch', () => ({ watchApprovedDelete }))

import {
  MAX_SELECTED_DELETE,
  proposeSelectedDelete,
  type SelectedDeleteHooks,
} from '../selectedDelete'

function makeHooks(): SelectedDeleteHooks {
  return {
    notify: vi.fn(),
    fail: vi.fn(),
    dropRows: vi.fn(),
    resync: vi.fn().mockResolvedValue(undefined),
    stillListed: vi.fn().mockReturnValue(false),
  }
}

describe('proposeSelectedDelete (#21989)', () => {
  beforeEach(() => {
    bulkDeleteDocuments.mockReset()
    watchApprovedDelete.mockReset()
  })

  it('an empty selection notifies deleteNothingSelected and sends no request', async () => {
    const hooks = makeHooks()
    await proposeSelectedDelete([], hooks)
    expect(hooks.notify).toHaveBeenCalledWith('knowledge.entries.deleteNothingSelected')
    expect(bulkDeleteDocuments).not.toHaveBeenCalled()
    expect(watchApprovedDelete).not.toHaveBeenCalled()
  })

  it('a selection over MAX_SELECTED_DELETE notifies deleteTooMany and sends no request', async () => {
    const hooks = makeHooks()
    const ids = Array.from({ length: MAX_SELECTED_DELETE + 1 }, (_, i) => `d${i}`)
    await proposeSelectedDelete(ids, hooks)
    expect(hooks.notify).toHaveBeenCalledWith(
      `knowledge.entries.deleteTooMany|${JSON.stringify({ max: MAX_SELECTED_DELETE })}`,
    )
    expect(bulkDeleteDocuments).not.toHaveBeenCalled()
  })

  it('a selection of exactly MAX_SELECTED_DELETE is proposed', async () => {
    bulkDeleteDocuments.mockResolvedValue({ approval_id: 'a1' })
    const ids = Array.from({ length: MAX_SELECTED_DELETE }, (_, i) => `d${i}`)
    await proposeSelectedDelete(ids, makeHooks())
    expect(bulkDeleteDocuments).toHaveBeenCalledWith(ids)
  })

  it('a successful proposal watches the approval and notifies deleteProposed', async () => {
    bulkDeleteDocuments.mockResolvedValue({ approval_id: 'a1' })
    const hooks = makeHooks()
    await proposeSelectedDelete(['d1', 'd2'], hooks)
    expect(bulkDeleteDocuments).toHaveBeenCalledWith(['d1', 'd2'])
    expect(hooks.notify).toHaveBeenCalledWith('knowledge.entries.deleteProposed')
    expect(hooks.fail).not.toHaveBeenCalled()
    const [approvalId, onApproved, settled] = watchApprovedDelete.mock.calls[0]
    expect(approvalId).toBe('a1')
    onApproved()
    expect(hooks.dropRows).toHaveBeenCalledWith(['d1', 'd2'])
    expect(await settled()).toBe(true)
    expect(hooks.resync).toHaveBeenCalledTimes(1)
  })

  it('the settled read is false while a selected row is still listed', async () => {
    bulkDeleteDocuments.mockResolvedValue({ approval_id: 'a1' })
    const hooks = makeHooks()
    vi.mocked(hooks.stillListed).mockReturnValue(true)
    await proposeSelectedDelete(['d1'], hooks)
    expect(await watchApprovedDelete.mock.calls[0][2]()).toBe(false)
  })

  it('a request failure reports deleteProposeFailed with the message and rethrows', async () => {
    bulkDeleteDocuments.mockRejectedValue(new Error('boom'))
    const hooks = makeHooks()
    await expect(proposeSelectedDelete(['d1'], hooks)).rejects.toThrow('boom')
    expect(hooks.fail).toHaveBeenCalledWith(
      `knowledge.entries.deleteProposeFailed|${JSON.stringify({ message: 'boom' })}`,
    )
    expect(watchApprovedDelete).not.toHaveBeenCalled()
    expect(hooks.notify).not.toHaveBeenCalled()
  })

  it('a non-Error failure falls back to deleteUnknownError', async () => {
    bulkDeleteDocuments.mockRejectedValue('nope')
    const hooks = makeHooks()
    await expect(proposeSelectedDelete(['d1'], hooks)).rejects.toBe('nope')
    expect(hooks.fail).toHaveBeenCalledWith(
      `knowledge.entries.deleteProposeFailed|${JSON.stringify({ message: 'knowledge.entries.deleteUnknownError' })}`,
    )
  })
})
