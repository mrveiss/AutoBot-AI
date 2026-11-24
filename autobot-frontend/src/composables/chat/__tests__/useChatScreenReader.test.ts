// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Auto-scroll and the screen-reader line for a new message (#1312): one watcher on the array length only.
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { nextTick, reactive } from 'vue'

import { announcementPreview, useChatScreenReader } from '../useChatScreenReader'
import type { ChatMessage } from '@/stores/useChatStore'

const msg = (id: string, content = 'hello', sender = 'assistant') => ({ id, sender, content, timestamp: 't' }) as unknown as ChatMessage

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('announcementPreview', () => {
  it('strips tags and adds an ellipsis only when the preview is shorter than the message', () => {
    expect(announcementPreview(msg('1', '<b>hi</b>'))).toBe('hi...')
    expect(announcementPreview(msg('1', 'hi'))).toBe('hi')
  })

  it('leaves no markup when tags are nested to rebuild one after a single strip pass', () => {
    const preview = announcementPreview(msg('1', '<scr<script>ipt>alert(1)</script><img src=x onerror=alert(1)>ok'))
    expect(preview).not.toMatch(/<\s*(script|img)/i)
    expect(preview).toContain('ok')
  })
})

describe('useChatScreenReader', () => {
  it('scrolls on every length change, announces only an added message, and clears after 2s', async () => {
    const store = reactive({ currentMessages: [msg('1')] })
    const scroll = vi.fn()
    const { screenReaderStatus } = useChatScreenReader(store, scroll, (s, p) => `New message from who:${s}: ${p}`)
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

  it('an earlier message timer does not clear a later announcement early', async () => {
    const store = reactive({ currentMessages: [msg('1')] })
    const { screenReaderStatus } = useChatScreenReader(store, vi.fn(), (s, p) => p)
    store.currentMessages.push(msg('2', 'A', 'user'))
    await nextTick(); await nextTick()
    vi.advanceTimersByTime(1990)
    store.currentMessages.push(msg('3', 'B', 'user'))
    await nextTick(); await nextTick()
    vi.advanceTimersByTime(10)
    expect(screenReaderStatus.value).toBe('B')
    vi.advanceTimersByTime(1990)
    expect(screenReaderStatus.value).toBe('')
  })
})
