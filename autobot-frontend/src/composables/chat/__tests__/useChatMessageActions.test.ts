// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Copy, delete and retry (#18243): the same controller calls the stream made before the split.
import { describe, it, expect, vi, beforeEach } from 'vitest'

const h = vi.hoisted(() => ({
  controller: { deleteMessage: vi.fn(), sendMessage: vi.fn(), editMessage: vi.fn() },
  confirm: vi.fn(),
  showToast: vi.fn(),
  messages: [{ id: 'm1', sender: 'user', content: 'hello', timestamp: 't' }],
}))
vi.mock('@/stores/useChatStore', () => ({ useChatStore: () => ({ currentMessages: h.messages }) }))
vi.mock('@/models/controllers', () => ({ useChatController: () => h.controller }))
vi.mock('@/composables/useConfirmDialog', () => ({ useConfirmDialog: () => ({ confirm: h.confirm }) }))
vi.mock('@/composables/useToast', () => ({ useToast: () => ({ showToast: h.showToast }) }))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))

import { copyText, useChatMessageActions } from '../useChatMessageActions'
import type { ChatMessage } from '@/stores/useChatStore'

const m = h.messages[0] as unknown as ChatMessage

beforeEach(() => { Object.values(h.controller).forEach((f) => f.mockReset()); h.confirm.mockReset(); h.showToast.mockReset() })

describe('useChatMessageActions', () => {
  it('deletes only after the user confirms', async () => {
    const { deleteMessage } = useChatMessageActions()
    h.confirm.mockResolvedValueOnce(false)
    await deleteMessage(m)
    expect(h.controller.deleteMessage).not.toHaveBeenCalled()
    h.confirm.mockResolvedValueOnce(true)
    await deleteMessage(m)
    expect(h.controller.deleteMessage).toHaveBeenCalledWith('m1')
  })

  it('retry resends the stored text and ignores an unknown id', async () => {
    const { retryMessage } = useChatMessageActions()
    await retryMessage('m1')
    expect(h.controller.sendMessage).toHaveBeenCalledWith('hello')
    await retryMessage('nope')
    expect(h.controller.sendMessage).toHaveBeenCalledTimes(1)
  })

  it('retry rethrows a failed send so the caller can tell it from a success', async () => {
    h.controller.sendMessage.mockRejectedValueOnce(new Error('down'))
    await expect(useChatMessageActions().retryMessage('m1')).rejects.toThrow('down')
  })

  it('saveEdit goes to the controller', () => {
    useChatMessageActions().saveEdit('m1', 'new')
    expect(h.controller.editMessage).toHaveBeenCalledWith('m1', 'new')
  })

  it('copyText writes to the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    expect(await copyText('abc')).toBe(true)
    expect(writeText).toHaveBeenCalledWith('abc')
  })

  it('copyMessage shows an error toast when the execCommand fallback returns false', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockRejectedValue(new Error('denied')) },
      configurable: true,
    })
    const execCommand = vi.fn().mockReturnValue(false)
    document.execCommand = execCommand
    expect(await copyText('abc')).toBe(false)
    expect(execCommand).toHaveBeenCalledWith('copy')
    await useChatMessageActions().copyMessage(m)
    expect(h.showToast).toHaveBeenCalledWith('chat.messages.copyFailed', 'error')
  })
})
