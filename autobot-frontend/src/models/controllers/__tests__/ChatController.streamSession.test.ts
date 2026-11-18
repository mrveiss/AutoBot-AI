// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
// #21357: a response stream writes into the chat it was started in, not the chat that is open when a chunk arrives.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('@/utils/ApiClient', () => ({ default: { invalidateCache: vi.fn() } }))
vi.mock('@/composables/useRequestQueue', () => ({
  requestQueue: { enqueue: vi.fn(({ fn }: { fn: () => unknown }) => fn()) }
}))
vi.mock('@/models/repositories', async () => {
  const mod = await import('../../repositories/ChatRepository')
  return { chatRepository: new mod.ChatRepository() }
})

import { ChatController } from '../ChatController'
import { useChatStore } from '@/stores/useChatStore'

const sse = (chunk: Record<string, unknown>) => `data: ${JSON.stringify(chunk)}\n`

/** A Response whose body yields the chunks one `push` at a time, so a test can act between them. */
function controlledStream() {
  let controller!: ReadableStreamDefaultController<Uint8Array>
  const body = new ReadableStream<Uint8Array>({ start: (c) => { controller = c } })
  const enc = new TextEncoder()
  return {
    response: { body } as unknown as Response,
    push: (chunk: Record<string, unknown>) => controller.enqueue(enc.encode(sse(chunk))),
    close: () => controller.close()
  }
}

const tick = () => new Promise((r) => setTimeout(r, 120)) // past the 80ms stream flush

describe('ChatController stream is bound to its originating chat (#21357)', () => {
  let chat: ChatController
  let store: ReturnType<typeof useChatStore>
  let a: string
  let b: string

  beforeEach(() => {
    setActivePinia(createPinia())
    chat = new ChatController()
    store = useChatStore()
    a = store.createNewSession('A')
    b = store.createNewSession('B')
    store.switchToSession(a)
  })

  const contents = (id: string) => store.sessions.find((s) => s.id === id)!.messages.map((m) => m.content)

  it('keeps writing to chat A after the person switches to chat B mid-stream', async () => {
    const s = controlledStream()
    const done = chat.handleStreamingResponse(s.response)
    s.push({ type: 'response', content: 'Hello', metadata: { message_id: 'm1' } })
    await tick()

    store.switchToSession(b) // the person moves on while A's reply is still arriving
    s.push({ type: 'response', content: 'Hello world', metadata: { message_id: 'm1' } })
    s.close()
    await done

    expect(contents(a)).toEqual(['Hello world'])
    expect(contents(b)).toEqual([])
    expect(store.sessions.find((x) => x.id === a)!.messages[0].status).toBe('sent')
  })

  it('a stream started in A keeps its message count when B streams at the same time', async () => {
    const sa = controlledStream()
    const doneA = chat.handleStreamingResponse(sa.response)
    sa.push({ type: 'response', content: 'from A', metadata: { message_id: 'ma' } })
    await tick()

    store.switchToSession(b)
    const sb = controlledStream()
    const doneB = chat.handleStreamingResponse(sb.response)
    sb.push({ type: 'response', content: 'from B', metadata: { message_id: 'mb' } })
    sa.push({ type: 'response', content: 'from A, more', metadata: { message_id: 'ma' } })
    sa.close()
    sb.close()
    await Promise.all([doneA, doneB])

    expect(contents(a)).toEqual(['from A, more'])
    expect(contents(b)).toEqual(['from B'])
  })

  it('does not touch the open chat typing state from a stream running in another chat', async () => {
    const s = controlledStream()
    const done = chat.handleStreamingResponse(s.response)
    s.push({ type: 'response', content: 'x', metadata: { message_id: 'm1' } })
    await tick()
    store.switchToSession(b)
    store.setTyping(true) // B's own turn is in flight
    s.push({ type: 'command_approval_request', content: 'ok?', metadata: { message_id: 'm2' } })
    s.close()
    await done

    expect(store.isTyping).toBe(true)
    expect(store.hasPendingApproval).toBe(false) // B is open and has no approval of its own
    expect(store.isPendingApproval(a)).toBe(true) // the approval belongs to A and is waiting there
    store.switchToSession(a)
    expect(store.hasPendingApproval).toBe(true)
    expect(contents(b)).toEqual([])
  })

  it('drops the stream writes when the originating chat was deleted', async () => {
    const s = controlledStream()
    const done = chat.handleStreamingResponse(s.response)
    store.switchToSession(b)
    store.deleteSession(a)
    s.push({ type: 'response', content: 'orphan', metadata: { message_id: 'm1' } })
    s.close()
    await done

    expect(contents(b)).toEqual([])
  })

  it('restores the typing indicator when the person returns to the chat that is still streaming', async () => {
    const s = controlledStream()
    const done = chat.handleStreamingResponse(s.response)
    s.push({ type: 'response', content: 'x', metadata: { message_id: 'm1' } })
    await tick()
    store.switchToSession(b)
    expect(store.isTyping).toBe(false)

    await chat.switchToSession(a)
    expect(store.isTyping).toBe(true)
    s.close()
    await done
  })

  it('interleaved streams each keep their buffered update through one flush', async () => {
    const sa = controlledStream()
    const doneA = chat.handleStreamingResponse(sa.response)
    store.switchToSession(b)
    const sb = controlledStream()
    const doneB = chat.handleStreamingResponse(sb.response)
    sa.push({ type: 'response', content: 'A text', metadata: { message_id: 'ma' } })
    sb.push({ type: 'response', content: 'B text', metadata: { message_id: 'mb' } })
    await tick() // one flush interval: neither stream's update replaced the other's

    expect(contents(a)).toEqual(['A text'])
    expect(contents(b)).toEqual(['B text'])
    sa.close()
    sb.close()
    await Promise.all([doneA, doneB])
  })

  it('shows a stream preview only while its chat is the open one', async () => {
    const closed = controlledStream()
    store.setTyping(true)
    const doneClosed = chat.handleStreamingResponse(closed.response) // started in A
    store.switchToSession(b)
    store.setTyping(true) // B has its own turn in flight
    closed.push({ type: 'response', content: 'Thinking about the plan for A.', metadata: { message_id: 'm1' } })
    await new Promise((r) => setTimeout(r, 260)) // past the 200ms preview throttle
    expect(store.streamingPreview).toBe('') // A is not open: its preview stays out of B

    const open = controlledStream()
    const doneOpen = chat.handleStreamingResponse(open.response) // started in B, the open chat
    open.push({ type: 'response', content: 'Working through the plan for B.', metadata: { message_id: 'm2' } })
    await new Promise((r) => setTimeout(r, 260))
    expect(store.streamingPreview).toContain('plan for B')

    closed.close()
    open.close()
    await Promise.all([doneClosed, doneOpen])
  })

  it('keeps the typing indicator for a chat whose send is still in the request', async () => {
    let settle!: (v: unknown) => void
    vi.spyOn(chat as unknown as { sendMessageWithRetry: () => Promise<unknown> }, 'sendMessageWithRetry').mockImplementation(
      () => new Promise((r) => { settle = r })
    )
    const sent = chat.sendMessage('hello')
    await Promise.resolve()
    await Promise.resolve()
    store.switchToSession(b)
    await chat.switchToSession(a)
    expect(store.isTyping).toBe(true)

    settle({ type: 'json', data: {} })
    await sent
    expect(store.isTyping).toBe(false)
  })
})
