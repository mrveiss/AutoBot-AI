// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Sending the composer's draft (#18243, moved unchanged in behaviour out of ChatInput.vue): the
 * send options (knowledge #249, extended thinking GH#8993, reasoning effort #9460, model override
 * #11585, uploaded file ids #20195), the Overseer route (#690) with its fall-back to the normal
 * flow, and restoring the draft when the send throws.
 */
import { computed, inject, ref, type Ref } from 'vue'
import { useChatStore } from '@/stores/useChatStore'
import { useChatController } from '@/models/controllers'
import { usePreferences } from '@/composables/usePreferences'
import { useVoiceOutput } from '@/composables/useVoiceOutput'
import { usesCanonicalRoute } from '@/utils/conversationFileUpload'
import { createLogger } from '@/utils/debugUtils'
import { cancelDraftAdoption, expectDraftAdoption, useChatKnowledge } from './useChatKnowledge'

const logger = createLogger('ChatInput')
const LOG_PREVIEW_CHARS = 50

export interface ComposerSendDeps {
  messageText: Ref<string>
  attachedFiles: Ref<File[]>
  serverFileIds: (files: File[]) => string[]
  isVoiceRecording: Ref<boolean>
  /** Files are still uploading: a send now would leave them out. */
  hasPendingUploads: Ref<boolean>
  resetTextareaHeight: () => void
  thinking: { enabled: Ref<boolean>; budgetTokens: Ref<number> }
  /** The per-request model/provider override (empty when "auto"). */
  overrideFields: { readonly value: object }
}

export function useComposerSend(deps: ComposerSendDeps) {
  const store = useChatStore()
  const controller = useChatController()
  const { unlockAudio } = useVoiceOutput()
  const { enabled: useKnowledge } = useChatKnowledge()
  const { reasoningEffort } = usePreferences()
  // Issue #690: Overseer state is provided by ChatInterface
  const overseerEnabled = inject<Ref<boolean>>('overseerEnabled', ref(false))
  const submitOverseerQuery = inject<(query: string) => Promise<boolean>>('submitOverseerQuery', async () => false)

  const isSending = ref(false)
  const canSend = computed(
    () => deps.messageText.value.trim().length > 0 && !isSending.value && !deps.isVoiceRecording.value && !deps.hasPendingUploads.value,
  )

  function sendOptionsFor(attachmentIds: string[]): Record<string, unknown> {
    return {
      attachments: attachmentIds,
      use_knowledge: useKnowledge.value, // Issue #249: RAG toggle
      ...(deps.thinking.enabled.value ? { thinking_enabled: true, thinking_budget_tokens: deps.thinking.budgetTokens.value } : {}),
      // #9460/#9471: omit 'auto' so the request stays inert
      ...(reasoningEffort.value !== 'auto' ? { reasoning_effort: reasoningEffort.value } : {}),
      ...deps.overrideFields.value, // #11585: empty when "auto"
    }
  }

  /** Issue #690: through the Overseer unless the turn carries files (#20195); fall back to the normal flow. */
  async function dispatch(message: string, options: Record<string, unknown>, attachmentIds: string[]): Promise<void> {
    if (usesCanonicalRoute(overseerEnabled.value, attachmentIds)) {
      await controller.sendMessage(message, options)
      return
    }
    logger.info('[ChatInput] Sending via Overseer Agent:', message.substring(0, LOG_PREVIEW_CHARS))
    // The user's message appears immediately; the overseer answers over the WebSocket.
    // the chat may change during the awaits below: the duplicate is removed from the chat it was added to
    const shownIn = store.currentSessionId ?? undefined
    const shownId = store.addMessage({ content: message, sender: 'user', status: 'sent', type: 'message' }, shownIn)
    if (await submitOverseerQuery(message)) return
    logger.warn('[ChatInput] Overseer submission failed, falling back to normal flow')
    // the controller adds the user turn itself: drop ours so the fall-back yields exactly one
    if (shownId) store.deleteMessage(shownId, shownIn)
    await controller.sendMessage(message, options)
  }

  async function sendMessage(): Promise<void> {
    if (!canSend.value) return
    unlockAudio() // Issue #1146: TTS needs an AudioContext unlocked from a user gesture
    const message = deps.messageText.value.trim()
    const files = [...deps.attachedFiles.value]
    deps.messageText.value = '' // cleared immediately for better UX
    deps.attachedFiles.value = []
    deps.resetTextareaHeight()
    isSending.value = true
    const attachmentIds = deps.serverFileIds(files) // #20195: the server ids, never browser File objects
    if (!store.currentSessionId) expectDraftAdoption() // this send creates the chat the draft choice belongs to
    try {
      await dispatch(message, sendOptionsFor(attachmentIds), attachmentIds)
    } catch (error) {
      logger.error('Failed to send message:', error)
      cancelDraftAdoption()
      deps.messageText.value = message
      deps.attachedFiles.value = [...files, ...deps.attachedFiles.value] // keep a file that finished uploading meanwhile
    } finally {
      isSending.value = false
    }
  }

  return { isSending, canSend, sendMessage }
}
