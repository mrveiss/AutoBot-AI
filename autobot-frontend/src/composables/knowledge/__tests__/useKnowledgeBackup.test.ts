// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #19721: the list's filename is the id, and restore and delete send it.
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), rawRequest: vi.fn() }))

vi.mock('@/utils/ApiClient', () => ({ default: api }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))
vi.mock('@autobot/ui', () => ({ HttpError: class extends Error {} }))

import { useKnowledgeBackup } from '../useKnowledgeBackup'

describe('useKnowledgeBackup', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.get.mockResolvedValue({
      backups: [{ filename: 'kb_backup_1.jsongz', size: 3, created_at: 'then' }],
    })
    api.post.mockResolvedValue({ status: 'success' })
    api.rawRequest.mockResolvedValue({ ok: true, json: async () => ({ status: 'success' }) })
  })

  it('names each backup by the filename the list returns', async () => {
    const { backups, loadBackups } = useKnowledgeBackup()
    await loadBackups()
    expect(backups.value[0].name).toBe('kb_backup_1.jsongz')
  })

  it('restores with that filename, so the request body is not empty', async () => {
    const { backups, loadBackups, restoreBackupDryRun } = useKnowledgeBackup()
    await loadBackups()
    await restoreBackupDryRun(backups.value[0].name)
    expect(api.post.mock.calls[0][1].backup_file).toBe('kb_backup_1.jsongz')
  })

  it('deletes with that filename, so the request body is not empty', async () => {
    const { backups, loadBackups, deleteBackup } = useKnowledgeBackup()
    await loadBackups()
    await deleteBackup(backups.value[0].name)
    const options = api.rawRequest.mock.calls[0][1]
    expect(options.body.backup_file).toBe('kb_backup_1.jsongz')
  })
})
