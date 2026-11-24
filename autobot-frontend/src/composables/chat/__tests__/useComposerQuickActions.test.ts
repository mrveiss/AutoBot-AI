// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Behaviour parity for the composer's insert-into-draft helpers, moved out of ChatInput.vue (#18243).
 */
import { describe, it, expect, vi } from 'vitest'
import { nextTick, ref } from 'vue'

const addMessage = vi.hoisted(() => vi.fn())
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
vi.mock('@/stores/useChatStore', () => ({ useChatStore: () => ({ addMessage }) }))

import { useComposerQuickActions } from '../useComposerQuickActions'
import { MAX_CHARACTERS } from '../useComposerInput'

function setup(text = '') {
  const messageText = ref(text)
  const textarea = document.createElement('textarea')
  document.body.appendChild(textarea)
  const api = useComposerQuickActions(messageText, ref(textarea))
  return { messageText, textarea, api }
}

describe('useComposerQuickActions', () => {
  it('lists help, summarize, translate and explain, in that order', () => {
    expect(setup().api.quickActions.value.map((a) => a.id)).toEqual(['help', 'summarize', 'translate', 'explain'])
  })

  it('a text action starts the draft with its starter text and focuses the box', async () => {
    const { api, messageText, textarea } = setup('old')
    api.runQuickAction('explain')
    await nextTick()
    expect(messageText.value).toBe('chat.input.quickActionText.explain')
    expect(document.activeElement).toBe(textarea)
  })

  it('Translate toggles its panel and leaves the draft alone', () => {
    const { api, messageText } = setup('keep')
    api.runQuickAction('translate')
    expect(api.showTranslatePanel.value).toBe(true)
    api.runQuickAction('translate')
    expect(api.showTranslatePanel.value).toBe(false)
    expect(messageText.value).toBe('keep')
  })

  it('inserts at the caret, replacing the selection', async () => {
    const { api, messageText, textarea } = setup('abcdef')
    textarea.value = 'abcdef'
    textarea.setSelectionRange(2, 4)
    api.insertAtCaret('X')
    await nextTick()
    expect(messageText.value).toBe('abXef')
    expect(textarea.selectionStart).toBe(3)
  })

  it('an insert at the limit is cut, as typing is', async () => {
    const full = 'x'.repeat(MAX_CHARACTERS)
    const { api, messageText, textarea } = setup(full)
    textarea.value = full
    textarea.setSelectionRange(MAX_CHARACTERS, MAX_CHARACTERS)
    api.insertAtCaret('🔥')
    await nextTick()
    expect(messageText.value).toHaveLength(MAX_CHARACTERS)
    api.handlePromptInsert('y'.repeat(MAX_CHARACTERS + 10))
    expect(messageText.value).toHaveLength(MAX_CHARACTERS)
  })

  it('a prompt template replaces the draft and focuses the box', async () => {
    const { api, messageText, textarea } = setup('old')
    api.handlePromptInsert('template')
    await nextTick()
    expect(messageText.value).toBe('template')
    expect(document.activeElement).toBe(textarea)
  })

  it('a translation result closes the panel and lands in the chat as an assistant message', () => {
    const { api } = setup()
    api.showTranslatePanel.value = true
    api.handleTranslationResult({ originalText: 'hi', translatedText: 'sveiki', targetLanguage: 'Latvian' })
    expect(api.showTranslatePanel.value).toBe(false)
    expect(addMessage).toHaveBeenCalledWith({ content: '**Latvian:**\nsveiki', sender: 'assistant', status: 'sent', type: 'message' })
  })
})
