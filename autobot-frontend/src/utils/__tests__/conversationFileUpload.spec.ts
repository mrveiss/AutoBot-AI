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
  usesCanonicalRoute,
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

describe('a 413 refusal keeps its stable reason (#20217)', () => {
  const refuse = async (status: number, body: string) => {
    const p = postConversationUpload('s1', file(), () => {})
    FakeXhr.last.status = status
    FakeXhr.last.responseText = body
    FakeXhr.last.listeners.load()
    return p.catch((e) => e)
  }
  beforeEach(() => vi.stubGlobal('XMLHttpRequest', FakeXhr))
  afterEach(() => vi.unstubAllGlobals())

  it('maps the quota code and carries the server figures', async () => {
    const detail = {
      code: 'conversation_file_quota_exceeded',
      message: 'x',
      limit_bytes: 20,
      live_bytes: 8,
      pending_removal_bytes: 12,
      remaining_bytes: 0,
    }
    const error = await refuse(413, JSON.stringify({ detail }))
    expect(error).toMatchObject({
      code: 'quota_exceeded',
      status: 413,
      refusal: { live_bytes: 8, pending_removal_bytes: 12 },
    })
  })

  it('maps the file-too-large code', async () => {
    const detail = { code: 'conversation_file_too_large', max_bytes: 52428800 }
    expect(await refuse(413, JSON.stringify({ detail }))).toMatchObject({ code: 'file_too_large', status: 413 })
  })

  it('stays a plain http error for an unknown code, a non-413, a string detail or an unreadable body', async () => {
    const unknown = JSON.stringify({ detail: { code: 'something_else' } })
    const quotaOn401 = JSON.stringify({ detail: { code: 'conversation_file_quota_exceeded' } })
    expect(await refuse(413, unknown)).toMatchObject({ code: 'http', status: 413 })
    expect(await refuse(401, quotaOn401)).toMatchObject({ code: 'http', status: 401 })
    expect(await refuse(413, JSON.stringify({ detail: 'File too large' }))).toMatchObject({ code: 'http', status: 413 })
    expect(await refuse(413, '<html>')).toMatchObject({ code: 'http', status: 413 })
  })
})

describe('describeUploadError for server refusals (#20217)', () => {
  const t = (key: string, params?: Record<string, unknown>) => `${key}|${JSON.stringify(params ?? {})}`
  const MB = 1024 * 1024

  it('names the maximum for an oversize file', () => {
    const error = new ConversationUploadError('file_too_large', 413, { max_bytes: 50 * MB })
    expect(describeUploadError(error, t)).toBe(
      'chat.input.uploadError.fileTooLarge|{"maxMb":50,"limitMb":0,"liveMb":0,"pendingMb":0,"remainingMb":0}'
    )
  })

  it('reports live bytes and the room left when nothing awaits removal', () => {
    const error = new ConversationUploadError('quota_exceeded', 413, {
      limit_bytes: 1024 * MB,
      live_bytes: 1000 * MB,
      pending_removal_bytes: 0,
      remaining_bytes: 24 * MB,
    })
    expect(describeUploadError(error, t)).toBe(
      'chat.input.uploadError.quotaExceeded|{"maxMb":0,"limitMb":1024,"liveMb":1000,"pendingMb":0,"remainingMb":24}'
    )
  })

  it('uses the human-review wording when deleted bytes still count', () => {
    const error = new ConversationUploadError('quota_exceeded', 413, {
      limit_bytes: 1024 * MB,
      live_bytes: 100 * MB,
      pending_removal_bytes: 924 * MB,
      remaining_bytes: 0,
    })
    expect(describeUploadError(error, t)).toContain('chat.input.uploadError.quotaExceededPendingRemoval|')
    expect(describeUploadError(error, t)).toContain('"pendingMb":924')
  })

  it('every key it can ask for exists in en.json', async () => {
    const en = (await import('@/i18n/locales/en.json')).default as any
    for (const key of ['fileTooLarge', 'quotaExceeded', 'quotaExceededPendingRemoval']) {
      expect(en.chat.input.uploadError[key]).toEqual(expect.any(String))
    }
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

describe('usesCanonicalRoute (#20195)', () => {
  it('sends a turn with files to the canonical route even when the overseer is on', () => {
    expect(usesCanonicalRoute(true, ['file-1'])).toBe(true)
  })

  it('lets the overseer take a turn with no files', () => {
    expect(usesCanonicalRoute(true, [])).toBe(false)
  })

  it('uses the canonical route whenever the overseer is off', () => {
    expect(usesCanonicalRoute(false, [])).toBe(true)
    expect(usesCanonicalRoute(false, ['file-1'])).toBe(true)
  })

  it('control: the decision depends on the ids, not on the overseer flag alone', () => {
    expect(usesCanonicalRoute(true, [])).not.toBe(usesCanonicalRoute(true, ['file-1']))
  })
})
