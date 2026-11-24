// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Behaviour parity for the composer's image generation, moved out of ChatInput.vue (#18243, GH#9015).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const m = vi.hoisted(() => ({ addMessage: vi.fn(), generateImage: vi.fn() }))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
vi.mock('@/stores/useChatStore', () => ({ useChatStore: () => ({ addMessage: m.addMessage }) }))
vi.mock('@/composables/useImageGeneration', () => ({ useImageGeneration: () => ({ generating: ref(false), generateImage: m.generateImage }) }))

import { useComposerImageGen } from '../useComposerImageGen'

beforeEach(() => Object.values(m).forEach((f) => f.mockReset()))

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
    }))
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
    expect(m.addMessage).toHaveBeenCalledWith(expect.objectContaining({ content: 'chat.input.imageGenerationFailed', metadata: {} }))
  })
})
