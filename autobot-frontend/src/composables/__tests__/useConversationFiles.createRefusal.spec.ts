// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #20217: a 413 on /files/create carries a structured `detail`; error.value must be translated text, never an object.
import { describe, it, expect, vi } from 'vitest'

const { post } = vi.hoisted(() => ({ post: vi.fn() }))

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ post, get: vi.fn() }) }))
vi.mock('@/i18n', () => ({
  default: {
    global: { t: (key: string, params: Record<string, unknown> = {}) => `${key}|${JSON.stringify(params)}` },
  },
}))

import { useConversationFiles } from '@/composables/useConversationFiles'
import { extractApiErrorMessage } from '@/utils/errorExtract'

const tooLarge = { code: 'conversation_file_too_large', message: 'File too large. Maximum size: 50MB', max_bytes: 52428800 }

describe('createFile refusal', () => {
  it('maps a client HttpError 413 code to the translated key with its figures', async () => {
    post.mockRejectedValueOnce(Object.assign(new Error('HTTP 413'), { status: 413, details: { detail: tooLarge } }))
    const files = useConversationFiles('s1')
    expect(await files.createFile('a.txt', 'x')).toBe(false)
    expect(files.error.value).toBe('chat.input.uploadError.fileTooLarge|{"maxMb":50,"limitMb":0,"liveMb":0,"pendingMb":0,"remainingMb":0}')
  })

  it('maps an axios-shaped 413 quota code too, and never stores an object', async () => {
    const detail = { code: 'conversation_file_quota_exceeded', message: 'm', limit_bytes: 1048576, live_bytes: 1048576 }
    post.mockRejectedValueOnce({ response: { status: 413, data: { detail } } })
    const files = useConversationFiles('s1')
    await files.createFile('a.txt', 'x')
    expect(typeof files.error.value).toBe('string')
    expect(files.error.value).toContain('chat.input.uploadError.quotaExceeded')
  })

  it('falls back to the structured detail message for an unrecognised code', async () => {
    post.mockRejectedValueOnce({ response: { status: 400, data: { detail: { code: 'other', message: 'Nope' } } } })
    const files = useConversationFiles('s1')
    await files.createFile('a.txt', 'x')
    expect(files.error.value).toBe('Nope')
  })
})

describe('extractApiErrorMessage', () => {
  it('returns detail.message when detail is an object, and a string detail unchanged', () => {
    expect(extractApiErrorMessage({ response: { data: { detail: tooLarge } } }, 'fb')).toBe(tooLarge.message)
    expect(extractApiErrorMessage({ response: { data: { detail: 'plain' } } }, 'fb')).toBe('plain')
  })

  it('skips an object detail with no message and uses data.message, then the fallback', () => {
    expect(extractApiErrorMessage({ response: { data: { detail: { code: 'x' }, message: 'top' } } }, 'fb')).toBe('top')
    expect(extractApiErrorMessage({ response: { data: { detail: { code: 'x' } } } }, 'fb')).toBe('fb')
  })
})
