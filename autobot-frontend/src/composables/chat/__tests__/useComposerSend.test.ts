// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Behaviour parity for sending the composer's draft, moved out of ChatInput.vue (#18243): the send
 * options, the Overseer route and its fall-back, the file-turn exception (#20195), and restoring the draft
 * when a send throws.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h, provide, ref, type Ref } from 'vue'
import { mount } from '@vue/test-utils'

const m = vi.hoisted(() => ({
  addMessage: vi.fn(),
  sendMessage: vi.fn(),
  unlockAudio: vi.fn(),
  reasoning: { value: 'auto' } as { value: string },
}))

vi.mock('@/stores/useChatStore', () => ({ useChatStore: () => ({ addMessage: m.addMessage }) }))
vi.mock('@/models/controllers', () => ({ useChatController: () => ({ sendMessage: m.sendMessage }) }))
vi.mock('@/composables/usePreferences', () => ({ usePreferences: () => ({ reasoningEffort: m.reasoning }) }))
vi.mock('@/composables/useVoiceOutput', () => ({ useVoiceOutput: () => ({ unlockAudio: m.unlockAudio }) }))
vi.mock('@/utils/conversationFileUpload', () => ({
  usesCanonicalRoute: (overseer: boolean, ids: readonly string[]) => !overseer || ids.length > 0,
}))

import { useComposerSend } from '../useComposerSend'
import { useChatKnowledge } from '../useChatKnowledge'

interface Harness {
  text: Ref<string>
  files: Ref<File[]>
  recording: Ref<boolean>
  thinkingEnabled: Ref<boolean>
  api: ReturnType<typeof useComposerSend>
  reset: ReturnType<typeof vi.fn>
}

function setup(overseer: boolean, submit: (q: string) => Promise<boolean> = async () => true): Harness {
  const text = ref('hello ')
  const files = ref<File[]>([])
  const recording = ref(false)
  const thinkingEnabled = ref(false)
  const reset = vi.fn()
  let api!: ReturnType<typeof useComposerSend>
  const Child = defineComponent({
    setup() {
      api = useComposerSend({
        messageText: text, attachedFiles: files, serverFileIds: (fs) => fs.map((f) => `id-${f.name}`),
        isVoiceRecording: recording, resetTextareaHeight: reset,
        thinking: { enabled: thinkingEnabled, budgetTokens: ref(5000) },
        overrideFields: { value: { model: 'm1' } },
      })
      return () => h('div')
    },
  })
  mount(defineComponent({
    setup() {
      provide('overseerEnabled', ref(overseer))
      provide('submitOverseerQuery', submit)
      return () => h(Child)
    },
  }))
  return { text, files, recording, thinkingEnabled, api, reset }
}

beforeEach(() => {
  Object.values(m).forEach((f) => typeof f === 'function' && 'mockReset' in f && f.mockReset())
  m.sendMessage.mockResolvedValue('id')
  m.reasoning.value = 'auto'
  useChatKnowledge().enabled.value = true
})

describe('canSend', () => {
  it('needs text, and is false while sending or recording', () => {
    const h1 = setup(false)
    expect(h1.api.canSend.value).toBe(true)
    h1.text.value = '   '
    expect(h1.api.canSend.value).toBe(false)
    h1.text.value = 'x'
    h1.recording.value = true
    expect(h1.api.canSend.value).toBe(false)
  })
})

describe('sendMessage, normal route', () => {
  it('clears the draft at once and sends the trimmed text with the options', async () => {
    const h1 = setup(false)
    await h1.api.sendMessage()
    expect(m.unlockAudio).toHaveBeenCalled()
    expect(h1.text.value).toBe('')
    expect(h1.reset).toHaveBeenCalled()
    expect(m.sendMessage).toHaveBeenCalledWith('hello', { attachments: [], use_knowledge: true, model: 'm1' })
    expect(h1.api.isSending.value).toBe(false)
  })

  it('carries the knowledge switch, extended thinking and a non-auto reasoning effort', async () => {
    const h1 = setup(false)
    useChatKnowledge().enabled.value = false
    h1.thinkingEnabled.value = true
    m.reasoning.value = 'high'
    await h1.api.sendMessage()
    expect(m.sendMessage).toHaveBeenCalledWith('hello', {
      attachments: [], use_knowledge: false, thinking_enabled: true, thinking_budget_tokens: 5000, reasoning_effort: 'high', model: 'm1',
    })
  })

  it('sends the server ids of the attached files, never the File objects', async () => {
    const h1 = setup(true) // even with Overseer on, a turn with files takes the canonical route (#20195)
    h1.files.value = [new File(['a'], 'a.txt')]
    await h1.api.sendMessage()
    expect(m.sendMessage).toHaveBeenCalledWith('hello', expect.objectContaining({ attachments: ['id-a.txt'] }))
    expect(m.addMessage).not.toHaveBeenCalled()
    expect(h1.files.value).toEqual([])
  })

  it('does nothing when it cannot send', async () => {
    const h1 = setup(false)
    h1.text.value = ''
    await h1.api.sendMessage()
    expect(m.sendMessage).not.toHaveBeenCalled()
    expect(m.unlockAudio).not.toHaveBeenCalled()
  })

  it('restores the draft and files when the send throws', async () => {
    m.sendMessage.mockRejectedValue(new Error('offline'))
    const h1 = setup(false)
    const file = new File(['a'], 'a.txt')
    h1.files.value = [file]
    await h1.api.sendMessage()
    expect(h1.text.value).toBe('hello')
    expect(h1.files.value).toEqual([file])
    expect(h1.api.isSending.value).toBe(false)
  })
})

describe('sendMessage, Overseer route (#690)', () => {
  it('shows the user message at once and submits to the overseer instead of sending', async () => {
    const submit = vi.fn().mockResolvedValue(true)
    const h1 = setup(true, submit)
    await h1.api.sendMessage()
    expect(m.addMessage).toHaveBeenCalledWith({ content: 'hello', sender: 'user', status: 'sent', type: 'message' })
    expect(submit).toHaveBeenCalledWith('hello')
    expect(m.sendMessage).not.toHaveBeenCalled()
  })

  it('falls back to the normal flow when the overseer refuses', async () => {
    const h1 = setup(true, async () => false)
    await h1.api.sendMessage()
    expect(m.sendMessage).toHaveBeenCalledWith('hello', expect.objectContaining({ use_knowledge: true }))
  })
})
