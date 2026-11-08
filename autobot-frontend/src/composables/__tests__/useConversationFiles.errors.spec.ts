// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #21159: every error.value the composable sets is translated; a server detail still wins over the fallback.
import { describe, it, expect, vi } from 'vitest'

const { put } = vi.hoisted(() => ({ put: vi.fn() }))

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ put, get: vi.fn() }) }))
vi.mock('@/i18n', () => ({
  default: { global: { t: (key: string) => `t:${key}` } },
}))

import { useConversationFiles } from '@/composables/useConversationFiles'

describe('conversation file errors (#21159)', () => {
  it('rename failure with no server detail shows the translated fallback', async () => {
    put.mockRejectedValueOnce({})
    const files = useConversationFiles('s1')
    expect(await files.renameFile('f1', 'b.txt')).toBe(false)
    expect(files.error.value).toBe('t:chat.conversationFiles.renameFailed')
  })

  it('rename failure keeps the server detail', async () => {
    put.mockRejectedValueOnce({ response: { data: { detail: 'Name already taken' } } })
    const files = useConversationFiles('s1')
    await files.renameFile('f1', 'b.txt')
    expect(files.error.value).toBe('Name already taken')
  })

  it('a rename the server declines (success false) is translated', async () => {
    put.mockResolvedValueOnce({ success: false })
    const files = useConversationFiles('s1')
    await files.renameFile('f1', 'b.txt')
    expect(files.error.value).toBe('t:chat.conversationFiles.renameFailed')
  })

  it('the missing-parameter guard is translated', async () => {
    const files = useConversationFiles('s1')
    expect(await files.renameFile('', 'b.txt')).toBe(false)
    expect(files.error.value).toBe('t:chat.conversationFiles.missingParameters')
  })

  it('the no-session guard is translated', async () => {
    const files = useConversationFiles('')
    await files.loadFiles()
    expect(files.error.value).toBe('t:chat.conversationFiles.noSession')
  })
})
