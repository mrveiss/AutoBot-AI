// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The composer's "Generate image" dialog state and submit (GH#9015), moved out of ChatInput.vue
 * (#18243). The result lands in the chat as an assistant image message, or its error text.
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/stores/useChatStore'
import { useImageGeneration } from '@/composables/useImageGeneration'

export type ImageProvider = 'dalle' | 'flux' | 'stable_diffusion'
export const IMAGE_PROVIDERS: readonly ImageProvider[] = ['dalle', 'flux', 'stable_diffusion']

export function useComposerImageGen() {
  const { t } = useI18n()
  const store = useChatStore()
  const { generating: imageGenerating, generateImage } = useImageGeneration()
  const showImageGenModal = ref(false)
  const imagePrompt = ref('')
  const imageProvider = ref<ImageProvider>('dalle')

  async function submitImageGeneration(): Promise<void> {
    const prompt = imagePrompt.value.trim()
    if (!prompt) return
    showImageGenModal.value = false
    const result = await generateImage({ prompt, provider: imageProvider.value })
    imagePrompt.value = ''
    if (!result) return
    store.addMessage({
      content: result.success ? '' : (result.error ?? t('chat.input.imageGenerationFailed')),
      sender: 'assistant',
      status: 'sent',
      type: 'image',
      metadata: result.success
        ? {
            display_type: 'image',
            image_payload: {
              images: result.images, provider: result.provider, model: result.model, prompt: result.prompt, size: result.size,
            },
          }
        : {},
    })
  }

  return { imageGenerating, showImageGenModal, imagePrompt, imageProvider, submitImageGeneration }
}
