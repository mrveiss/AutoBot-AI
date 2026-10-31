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

import { postConversationUpload } from '@/utils/conversationFileUpload'

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

  it('rejects with the status on a 401 so the chat shows it inline', async () => {
    const p = postConversationUpload('s1', file(), () => {})
    FakeXhr.last.status = 401
    FakeXhr.last.listeners.load()
    await expect(p).rejects.toThrow('Upload failed with status: 401')
  })

  it('rejects on abort, network error and an unparseable body', async () => {
    const a = postConversationUpload('s1', file(), () => {})
    FakeXhr.last.listeners.abort()
    await expect(a).rejects.toThrow('Upload cancelled')
    const n = postConversationUpload('s1', file(), () => {})
    FakeXhr.last.listeners.error()
    await expect(n).rejects.toThrow('Network error during upload')
    const b = postConversationUpload('s1', file(), () => {})
    FakeXhr.last.responseText = 'not json'
    FakeXhr.last.listeners.load()
    await expect(b).rejects.toThrow('Invalid response from server')
  })
})
