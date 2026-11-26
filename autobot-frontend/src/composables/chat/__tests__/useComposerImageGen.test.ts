// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Behaviour parity for the composer's image generation, moved out of ChatInput.vue (#18243, GH#9015).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const m = vi.hoisted(() => ({
  showToast: vi.fn(), addMessage: vi.fn(), generateImage: vi.fn(), ensure: vi.fn(), store: { currentSessionId: 'session-a' as string | null },
}))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
vi.mock('@/stores/useChatStore', () => ({ useChatStore: () => Object.assign(m.store, { addMessage: m.addMessage }) }))
vi.mock('@autobot/ui', () => ({ useToast: () => ({ showToast: m.showToast }) }))
vi.mock('@/models/controllers', () => ({ useChatController: () => ({}) }))
vi.mock('@/utils/conversationFileUpload', () => ({ ensureUploadSession: m.ensure }))
vi.mock('@/composables/useImageGeneration', () => ({ useImageGeneration: () => ({ generating: ref(false), generateImage: m.generateImage }) }))

import { useComposerImageGen } from '../useComposerImageGen'

beforeEach(() => {
  ;[m.addMessage, m.generateImage, m.ensure, m.showToast].forEach((f) => f.mockReset())
  m.store.currentSessionId = 'session-a'
  m.ensure.mockImplementation(async (store: { currentSessionId: string | null }) => store.currentSessionId ?? 'created')
})

describe('useComposerImageGen', () => {
  it('ignores a blank prompt', async () => {
    const g = useComposerImageGen()
    g.showImageGenModal.value = true
    g.imagePrompt.value = '   '
    await g.submitImageGeneration()
    expect(m.generateImage).not.toHaveBeenCalled()
    expect(g.showImageGenModal.value).toBe(true)
  })

  it('closes the dialog, generates with the chosen provider and posts an image message', async () => {
    m.generateImage.mockResolvedValue({ success: true, images: ['u'], provider: 'flux', model: 'f1', prompt: 'a city', size: '1024' })
    const g = useComposerImageGen()
    g.showImageGenModal.value = true
    g.imagePrompt.value = ' a city '
    g.imageProvider.value = 'flux'
    await g.submitImageGeneration()
    expect(g.showImageGenModal.value).toBe(false)
    expect(m.generateImage).toHaveBeenCalledWith({ prompt: 'a city', provider: 'flux' })
    expect(g.imagePrompt.value).toBe('')
    expect(m.addMessage).toHaveBeenCalledWith(expect.objectContaining({
      type: 'image', sender: 'assistant', content: '',
      metadata: { display_type: 'image', image_payload: { images: ['u'], provider: 'flux', model: 'f1', prompt: 'a city', size: '1024' } },
    }), 'session-a')
  })

  it('posts the error text for a failed generation, and a translated fallback when it has none', async () => {
    m.generateImage.mockResolvedValueOnce({ success: false, error: 'quota' }).mockResolvedValueOnce({ success: false })
    const g = useComposerImageGen()
    g.imagePrompt.value = 'x'
    await g.submitImageGeneration()
    g.imagePrompt.value = 'y'
    await g.submitImageGeneration()
    expect(m.addMessage.mock.calls[0][0]).toMatchObject({ content: 'quota', metadata: {} })
    expect(m.addMessage.mock.calls[1][0]).toMatchObject({ content: 'chat.input.imageGenerationFailed' })
  })

  it('says so in the chat when the request is rejected and yields no result', async () => {
    m.generateImage.mockResolvedValue(null)
    const g = useComposerImageGen()
    g.imagePrompt.value = 'x'
    await g.submitImageGeneration()
    expect(m.addMessage).toHaveBeenCalledWith(expect.objectContaining({ content: 'chat.input.imageGenerationFailed', metadata: {} }), 'session-a')
  })

  it('posts the result into the chat that submitted it, not the one open when it completes', async () => {
    let finish!: (v: unknown) => void
    m.generateImage.mockReturnValue(new Promise((resolve) => { finish = resolve }))
    const g = useComposerImageGen()
    g.imagePrompt.value = 'x'
    const submitting = g.submitImageGeneration()
    await vi.waitFor(() => expect(m.generateImage).toHaveBeenCalled())
    m.store.currentSessionId = 'session-b' // the user opens another chat meanwhile
    finish({ success: true, images: ['u'] })
    await submitting
    expect(m.addMessage).toHaveBeenCalledWith(expect.anything(), 'session-a')
  })

  it('with no chat open it creates one first and posts the result there', async () => {
    m.store.currentSessionId = null
    m.generateImage.mockResolvedValue({ success: true, images: ['u'] })
    const g = useComposerImageGen()
    g.imagePrompt.value = 'x'
    await g.submitImageGeneration()
    expect(m.ensure).toHaveBeenCalled()
    expect(m.addMessage).toHaveBeenCalledWith(expect.anything(), 'created')
  })

  it('ignores a second submit while the first is in flight, so one request is billed', async () => {
    let finish!: (v: unknown) => void
    m.generateImage.mockReturnValue(new Promise((resolve) => { finish = resolve }))
    const g = useComposerImageGen()
    g.imagePrompt.value = 'x'
    const first = g.submitImageGeneration()
    await g.submitImageGeneration()
    await vi.waitFor(() => expect(m.generateImage).toHaveBeenCalledTimes(1)) // the first is still creating/resolving its chat
    await Promise.resolve()
    expect(m.generateImage).toHaveBeenCalledTimes(1)
    finish({ success: true, images: [] })
    await first
    expect(m.addMessage).toHaveBeenCalledTimes(1)
  })

  it('when no chat can be created it reopens the dialog with the prompt kept and says so, with no unhandled rejection', async () => {
    m.store.currentSessionId = null
    m.ensure.mockRejectedValue(new Error('create failed'))
    const g = useComposerImageGen()
    g.showImageGenModal.value = true
    g.imagePrompt.value = 'a city'
    await expect(g.submitImageGeneration()).resolves.toBeUndefined()
    expect(g.showImageGenModal.value).toBe(true)
    expect(g.imagePrompt.value).toBe('a city')
    expect(m.showToast).toHaveBeenCalledWith('chat.input.imageGenerationFailed', 'error')
    expect(m.generateImage).not.toHaveBeenCalled()
    m.ensure.mockImplementation(async () => 'created') // and the request is not stuck in flight
    m.generateImage.mockResolvedValue({ success: true, images: [] })
    await g.submitImageGeneration()
    expect(m.generateImage).toHaveBeenCalledTimes(1)
  })
})
