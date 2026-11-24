// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Behaviour parity for the composer's text box, moved out of ChatInput.vue (#18243): Enter sends and
 * Shift+Enter breaks the line, the slash dropdown owns the arrow, Escape, Tab and Enter keys while it is
 * open, and the draft is cut at the character limit.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const slash = vi.hoisted(() => ({
  show: false,
  confirmed: null as null | { id: string; name: string },
}))
const fns = vi.hoisted(() => ({
  moveUp: vi.fn(), moveDown: vi.fn(), close: vi.fn(), onInput: vi.fn(), setSelectedIndex: vi.fn(), fetchPresets: vi.fn(),
  applyPreset: vi.fn((p: { name: string }) => `applied:${p.name}`),
  confirmSelection: vi.fn(() => slash.confirmed),
}))

vi.mock('@/composables/useSlashCommands', async () => {
  const { ref: r, computed } = await import('vue')
  return {
    useSlashCommands: () => ({
      suggestions: r([]), showDropdown: computed(() => slash.show), selectedIndex: r(0), ...fns,
    }),
  }
})

import { MAX_CHARACTERS, useComposerInput } from '../useComposerInput'

const key = (k: string, extra: Partial<KeyboardEvent> = {}) => {
  const preventDefault = vi.fn()
  const event = { key: k, shiftKey: false, preventDefault, target: document.createElement('textarea'), ...extra }
  return { event: event as unknown as KeyboardEvent, preventDefault }
}

function setup(canSendValue = true) {
  const messageText = ref('')
  const sendMessage = vi.fn()
  const api = useComposerInput({ messageText, messageInput: ref(undefined), canSend: ref(canSendValue), sendMessage })
  return { messageText, sendMessage, api }
}

beforeEach(() => {
  slash.show = false
  slash.confirmed = null
  Object.values(fns).forEach((f) => f.mockClear())
})

describe('Enter and Shift+Enter', () => {
  it('Enter sends when the draft can be sent, and stops the newline', () => {
    const { api, sendMessage } = setup(true)
    const { event, preventDefault } = key('Enter')
    api.handleKeydown(event)
    expect(sendMessage).toHaveBeenCalledTimes(1)
    expect(preventDefault).toHaveBeenCalled()
  })

  it('Shift+Enter leaves the newline alone and does not send', () => {
    const { api, sendMessage } = setup(true)
    const { event, preventDefault } = key('Enter', { shiftKey: true })
    api.handleKeydown(event)
    expect(sendMessage).not.toHaveBeenCalled()
    expect(preventDefault).not.toHaveBeenCalled()
  })

  it('Enter does not send when the draft cannot be sent', () => {
    const { api, sendMessage } = setup(false)
    api.handleKeydown(key('Enter').event)
    expect(sendMessage).not.toHaveBeenCalled()
  })
})

describe('slash dropdown keys while it is open', () => {
  beforeEach(() => { slash.show = true })

  it.each([
    ['ArrowDown', 'moveDown'],
    ['ArrowUp', 'moveUp'],
    ['Escape', 'close'],
  ] as const)('%s calls %s and is consumed', (k, fn) => {
    const { api, sendMessage } = setup()
    const { event, preventDefault } = key(k)
    api.handleKeydown(event)
    expect(fns[fn]).toHaveBeenCalledTimes(1)
    expect(preventDefault).toHaveBeenCalled()
    expect(sendMessage).not.toHaveBeenCalled()
  })

  it.each(['Tab', 'Enter'])('%s inserts the selected preset instead of sending', (k) => {
    slash.confirmed = { id: '1', name: 'summarize' }
    const { api, messageText, sendMessage } = setup()
    const { event, preventDefault } = key(k)
    api.handleKeydown(event)
    expect(messageText.value).toBe('applied:summarize')
    expect(fns.close).toHaveBeenCalled()
    expect(preventDefault).toHaveBeenCalled()
    expect(sendMessage).not.toHaveBeenCalled()
  })

  it('Enter with no confirmable preset falls through to a normal send', () => {
    slash.confirmed = null
    const { api, sendMessage } = setup()
    api.handleKeydown(key('Enter').event)
    expect(sendMessage).toHaveBeenCalledTimes(1)
  })

  it('Shift+Enter is not a confirm key', () => {
    slash.confirmed = { id: '1', name: 'x' }
    const { api, messageText } = setup()
    api.handleKeydown(key('Enter', { shiftKey: true }).event)
    expect(messageText.value).toBe('')
  })
})

describe('input handling', () => {
  it('cuts the draft at the character limit and tells the slash detector', () => {
    const { api, messageText } = setup()
    const target = document.createElement('textarea')
    target.value = 'x'.repeat(MAX_CHARACTERS + 25)
    api.handleInput({ target } as unknown as Event)
    expect(target.value).toHaveLength(MAX_CHARACTERS)
    expect(messageText.value).toHaveLength(MAX_CHARACTERS)
    expect(fns.onInput).toHaveBeenCalledTimes(1)
  })

  it('flags the last tenth of the limit as near it', () => {
    const { api, messageText } = setup()
    messageText.value = 'x'.repeat(MAX_CHARACTERS * 0.9)
    expect(api.isNearLimit.value).toBe(false)
    messageText.value += 'x'
    expect(api.isNearLimit.value).toBe(true)
  })

  it('shows the typing hint only for a non-empty draft in a focused box', () => {
    const { api, messageText } = setup()
    messageText.value = 'hi'
    expect(api.isTypingIndicatorVisible.value).toBe(false)
    api.isInputFocused.value = true
    expect(api.isTypingIndicatorVisible.value).toBe(true)
    messageText.value = ''
    expect(api.isTypingIndicatorVisible.value).toBe(false)
  })
})
