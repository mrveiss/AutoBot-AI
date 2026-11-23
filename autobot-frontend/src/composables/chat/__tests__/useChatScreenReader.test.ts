// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Auto-scroll and the screen-reader line for a new message (#1312): one watcher on the array length only.
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { nextTick, reactive } from 'vue'

vi.mock('@/utils/sanitize', () => ({ sanitizeChatHtml: (h: string) => h }))

import { announcementText, useChatScreenReader } from '../useChatScreenReader'
import type { ChatMessage } from '@/stores/useChatStore'

const msg = (id: string, content = 'hello', sender = 'assistant') => ({ id, sender, content, timestamp: 't' }) as unknown as ChatMessage

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('announcementText', () => {
  it('strips tags and adds an ellipsis only when the preview is shorter than the message', () => {
    expect(announcementText(msg('1', '<b>hi</b>'), 'AI')).toBe('New message from AI: hi...')
    expect(announcementText(msg('1', 'hi'), 'AI')).toBe('New message from AI: hi')
  })
})

describe('useChatScreenReader', () => {
  it('scrolls on every length change, announces only an added message, and clears after 2s', async () => {
    const store = reactive({ currentMessages: [msg('1')] })
    const scroll = vi.fn()
    const { screenReaderStatus } = useChatScreenReader(store, scroll, (s) => 'who:' + s)
    store.currentMessages.push(msg('2', 'hello', 'user'))
    await nextTick()
    await nextTick()
    expect(scroll).toHaveBeenCalledTimes(1)
    expect(screenReaderStatus.value).toBe('New message from who:user: hello')
    vi.advanceTimersByTime(2000)
    expect(screenReaderStatus.value).toBe('')
    store.currentMessages.pop()
    await nextTick()
    await nextTick()
    expect(scroll).toHaveBeenCalledTimes(2)
    expect(screenReaderStatus.value).toBe('')
  })
})
