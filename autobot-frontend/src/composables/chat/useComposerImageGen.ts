// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The composer's "Generate image" dialog state and submit (GH#9015), moved out of ChatInput.vue
 * (#18243). The result lands as an assistant image message, or its error text, in the chat the request was
 * submitted from -- never whichever chat is open when it completes. With no chat open the request first creates one
 * (`ensureUploadSession`, the canonical "the chat a request belongs to"), so the result always has a home.
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToast } from '@autobot/ui'
import { useChatStore } from '@/stores/useChatStore'
import { useChatController } from '@/models/controllers'
import { ensureUploadSession } from '@/utils/conversationFileUpload'
import { useImageGeneration } from '@/composables/useImageGeneration'

export type ImageProvider = 'dalle' | 'flux' | 'stable_diffusion'
export const IMAGE_PROVIDERS: readonly ImageProvider[] = ['dalle', 'flux', 'stable_diffusion']

export function useComposerImageGen() {
  const { t } = useI18n()
  const { showToast } = useToast()
  const store = useChatStore()
  const controller = useChatController()
  const { generating: imageGenerating, generateImage } = useImageGeneration()
  const showImageGenModal = ref(false)
  const imagePrompt = ref('')
  const imageProvider = ref<ImageProvider>('dalle')
  const inFlight = ref(false) // covers the session creation too, which `imageGenerating` does not

  /** Post the outcome into `sessionId`: an image message, or the failure text (a rejected request is null). */
  function postResult(result: Awaited<ReturnType<typeof generateImage>>, sessionId: string): void {
    const ok = result?.success === true
    store.addMessage({
      content: ok ? '' : (result?.error ?? t('chat.input.imageGenerationFailed')),
      sender: 'assistant',
      status: 'sent',
      type: 'image',
      metadata: result && ok
        ? {
            display_type: 'image',
            image_payload: {
              images: result.images, provider: result.provider, model: result.model, prompt: result.prompt, size: result.size,
            },
          }
        : {},
    }, sessionId)
  }

  /** The chat the request belongs to, or null (dialog reopened, prompt kept, toast shown) when none could be made. */
  async function chatForRequest(): Promise<string | null> {
    try {
      return await ensureUploadSession(store, controller) // read now: the open chat may change while it runs
    } catch {
      showImageGenModal.value = true
      showToast(t('chat.input.imageGenerationFailed'), 'error')
      return null
    }
  }

  async function submitImageGeneration(): Promise<void> {
    const prompt = imagePrompt.value.trim()
    if (!prompt || inFlight.value || imageGenerating.value) return // one request at a time, from any entry point
    inFlight.value = true
    showImageGenModal.value = false
    try {
      const sessionId = await chatForRequest()
      if (!sessionId) return
      const result = await generateImage({ prompt, provider: imageProvider.value })
      imagePrompt.value = ''
      postResult(result, sessionId)
    } finally {
      inFlight.value = false
    }
  }

  return { imageGenerating, showImageGenModal, imagePrompt, imageProvider, submitImageGeneration }
}
