// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/** #22191: getDesktopUrl builds the URL of the SELECTED picker entry (desktop VM or /secrets host). */
import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useChatStore } from '../useChatStore'
import { buildVncBaseUrl, getDesktopVmHost } from '@/config/vnc-client'

describe('useChatStore.getDesktopUrl', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('is built from the selected host through the one URL builder, with the chat context', () => {
    const store = useChatStore()
    const host = { host: 'box.example.test', vnc_port: 6081 }
    const url = store.getDesktopUrl('chat-1', host)
    expect(url.startsWith(`${buildVncBaseUrl(host)}/vnc.html?autoconnect=true&`)).toBe(true)
    expect(url).toContain('chatSession=chat-1')
  })

  it("works for AutoBot's desktop VM entry and has no own-display fallback", () => {
    const store = useChatStore()
    expect(store.getDesktopUrl('chat-1', getDesktopVmHost())).toContain(getDesktopVmHost().host)
    expect(store.getDesktopUrl('chat-1', null)).toBe('')
  })
})
