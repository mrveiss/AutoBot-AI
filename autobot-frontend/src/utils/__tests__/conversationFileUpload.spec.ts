// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #20133: the chat attachment upload goes to an admin-gated route, so it must carry the stored bearer,
// keep byte-level progress, surface a 401 as a rejection the chat shows inline, and still reject on abort.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

const { token } = vi.hoisted(() => ({ token: { value: 'live-jwt' as string | null } }))

vi.mock('@/utils/authToken', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/utils/authToken')>()),
  readStoredAuthToken: () => token.value,
}))

import {
  ConversationUploadError,
  describeUploadError,
  ensureUploadSession,
  postConversationUpload,
} from '@/utils/conversationFileUpload'

type Listener = (event?: unknown) => void

class FakeXhr {
  static last: FakeXhr
  headers: Record<string, string> = {}
  listeners: Record<string, Listener> = {}
  uploadListeners: Record<string, Listener> = {}
  status = 200
  responseText = '{"upload_id":"u1","file_info":{"file_id":"f1"}}'
  method = ''
  url = ''
  body: unknown
  upload = { addEventListener: (n: string, l: Listener) => (this.uploadListeners[n] = l) }
  constructor() {
    FakeXhr.last = this
  }
  addEventListener(n: string, l: Listener) {
    this.listeners[n] = l
  }
  open(method: string, url: string) {
    this.method = method
    this.url = url
  }
  setRequestHeader(name: string, value: string) {
    this.headers[name] = value
  }
  send(body: unknown) {
    this.body = body
  }
}

const file = () => new File(['abc'], 'a.txt')

describe('postConversationUpload (#20133)', () => {
  beforeEach(() => {
    token.value = 'live-jwt'
    vi.stubGlobal('XMLHttpRequest', FakeXhr)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('posts to the conversation upload route with the stored bearer', async () => {
    const p = postConversationUpload('s1', file(), () => {})
    expect(FakeXhr.last.method).toBe('POST')
    expect(FakeXhr.last.url).toMatch(/\/conversation-files\/conversation\/s1\/upload$/)
    expect(FakeXhr.last.headers.Authorization).toBe('Bearer live-jwt')
    FakeXhr.last.listeners.load()
    await expect(p).resolves.toEqual({ upload_id: 'u1', file_info: { file_id: 'f1' } })
  })

  it('sends no Authorization header without a stored token', () => {
    token.value = null
    void postConversationUpload('s1', file(), () => {})
    expect(FakeXhr.last.headers.Authorization).toBeUndefined()
  })

  it('reports byte progress only when the length is computable', () => {
    const seen: Array<[number, number]> = []
    void postConversationUpload('s1', file(), (l, t) => seen.push([l, t]))
    FakeXhr.last.uploadListeners.progress({ lengthComputable: false, loaded: 1, total: 0 })
    FakeXhr.last.uploadListeners.progress({ lengthComputable: true, loaded: 1, total: 3 })
    expect(seen).toEqual([[1, 3]])
  })

  it('rejects with code http and the status on a 401 so the chat shows it inline', async () => {
    const p = postConversationUpload('s1', file(), () => {})
    FakeXhr.last.status = 401
    FakeXhr.last.listeners.load()
    const error = await p.catch((e) => e)
    expect(error).toBeInstanceOf(ConversationUploadError)
    expect(error).toMatchObject({ code: 'http', status: 401 })
  })

  it('rejects with a code on abort, network error and an unparseable body', async () => {
    const a = postConversationUpload('s1', file(), () => {})
    FakeXhr.last.listeners.abort()
    await expect(a).rejects.toMatchObject({ code: 'cancelled', status: undefined })
    const n = postConversationUpload('s1', file(), () => {})
    FakeXhr.last.listeners.error()
    await expect(n).rejects.toMatchObject({ code: 'network', status: undefined })
    const b = postConversationUpload('s1', file(), () => {})
    FakeXhr.last.responseText = 'not json'
    FakeXhr.last.listeners.load()
    await expect(b).rejects.toMatchObject({ code: 'invalid_response', status: undefined })
  })
})

describe('describeUploadError (#20133)', () => {
  const t = (key: string, params?: Record<string, unknown>) => `${key}|${JSON.stringify(params ?? {})}`

  it('maps each code to its translation key, passing the status for http', () => {
    expect(describeUploadError(new ConversationUploadError('http', 413), t)).toBe(
      'chat.input.uploadError.http|{"status":413}'
    )
    expect(describeUploadError(new ConversationUploadError('invalid_response'), t)).toBe(
      'chat.input.uploadError.invalidResponse|{}'
    )
    expect(describeUploadError(new ConversationUploadError('network'), t)).toBe(
      'chat.input.uploadError.network|{}'
    )
    expect(describeUploadError(new ConversationUploadError('cancelled'), t)).toBe(
      'chat.input.uploadError.cancelled|{}'
    )
  })

  it('never shows the diagnostic message, and falls back to the generic key for other errors', () => {
    const typed = new ConversationUploadError('network')
    expect(describeUploadError(typed, t)).not.toContain(typed.message)
    expect(describeUploadError(new Error('boom'), t)).toBe('chat.input.uploadError.unknown|{}')
  })
})

describe('ensureUploadSession (#20133)', () => {
  it('uses the current session and creates nothing', async () => {
    const create = vi.fn()
    expect(await ensureUploadSession({ currentSessionId: 's-1' }, { createNewSession: create })).toBe('s-1')
    expect(create).not.toHaveBeenCalled()
  })

  it('creates one session, never the id "default", when the chat has none', async () => {
    const create = vi.fn().mockResolvedValue('new-1')
    expect(await ensureUploadSession({ currentSessionId: null }, { createNewSession: create })).toBe('new-1')
    expect(create).toHaveBeenCalledTimes(1)
  })

  it('shares one creation between files picked together, then allows a later one', async () => {
    const create = vi.fn().mockResolvedValue('new-2')
    const store = { currentSessionId: null }
    const ids = await Promise.all([1, 2, 3].map(() => ensureUploadSession(store, { createNewSession: create })))
    expect(ids).toEqual(['new-2', 'new-2', 'new-2'])
    expect(create).toHaveBeenCalledTimes(1)
    await ensureUploadSession(store, { createNewSession: create })
    expect(create).toHaveBeenCalledTimes(2)
  })

  it('rejects, and creates again next time, when the backend create fails', async () => {
    const create = vi.fn().mockRejectedValueOnce(new Error('down')).mockResolvedValueOnce('new-3')
    await expect(ensureUploadSession({ currentSessionId: null }, { createNewSession: create })).rejects.toThrow('down')
    expect(await ensureUploadSession({ currentSessionId: null }, { createNewSession: create })).toBe('new-3')
  })
})
