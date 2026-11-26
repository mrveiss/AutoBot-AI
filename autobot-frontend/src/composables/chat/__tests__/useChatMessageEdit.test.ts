// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Edit-message state (#18243): open copies the text, save trims and goes through the callback, blank never saves.
import { describe, it, expect, vi } from 'vitest'
import { useChatMessageEdit } from '../useChatMessageEdit'
import type { ChatMessage } from '@/stores/useChatStore'

const message = { id: 'm1', sender: 'user', content: 'hello', timestamp: 't' } as unknown as ChatMessage

describe('useChatMessageEdit', () => {
  it('opens with the message text', () => {
    const edit = useChatMessageEdit(vi.fn())
    edit.editMessage(message)
    expect(edit.showEditModal.value).toBe(true)
    expect(edit.editingContent.value).toBe('hello')
  })

  it('saves the trimmed text for that message id, then closes', () => {
    const save = vi.fn()
    const edit = useChatMessageEdit(save)
    edit.editMessage(message)
    edit.editingContent.value = '  changed  '
    edit.saveEditedMessage()
    expect(save).toHaveBeenCalledWith('m1', 'changed')
    expect(edit.showEditModal.value).toBe(false)
    expect(edit.editingMessage.value).toBeNull()
  })

  it('does not save a blank edit and cancel clears the state', () => {
    const save = vi.fn()
    const edit = useChatMessageEdit(save)
    edit.editMessage(message)
    edit.editingContent.value = '   '
    edit.saveEditedMessage()
    expect(save).not.toHaveBeenCalled()
    edit.cancelEdit()
    expect(edit.editingContent.value).toBe('')
    expect(edit.showEditModal.value).toBe(false)
  })
})
