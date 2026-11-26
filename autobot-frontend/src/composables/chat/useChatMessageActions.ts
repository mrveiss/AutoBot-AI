// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Copy, delete and retry for a chat message (#18243, step 5a batch 2), moved out of
 * ChatMessages.vue. Delete and retry go through the same controller calls as before.
 */
import { useI18n } from 'vue-i18n'
import { useClipboard } from '@/composables/useClipboard'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useToast } from '@/composables/useToast'
import { useChatController } from '@/models/controllers'
import { useChatStore, type ChatMessage } from '@/stores/useChatStore'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useChatMessageActions')

/**
 * Copy through the canonical `useClipboard` (Clipboard API, then `execCommand`).
 * Resolves false when both paths fail, including `execCommand` returning false.
 */
export function copyText(text: string): Promise<boolean> {
  return useClipboard({ copiedDuration: 0 }).copy(text)
}

export function useChatMessageActions() {
  const { t } = useI18n()
  const { confirm } = useConfirmDialog()
  const { showToast } = useToast()
  const store = useChatStore()
  const controller = useChatController()

  async function copyMessage(message: ChatMessage) {
    if (!(await copyText(message.content))) {
      showToast(t('chat.messages.copyFailed'), 'error')
    }
  }

  async function deleteMessage(message: ChatMessage) {
    if (await confirm({ title: t('common.confirm'), message: t('chat.messages.confirmDelete') })) {
      controller.deleteMessage(message.id)
    }
  }

  /** Resend the stored message text through the controller. */
  async function retryMessage(messageId: string) {
    try {
      const message = store.currentMessages.find((m) => m.id === messageId)
      if (!message || !message.content) {
        logger.error('Message not found or has no content:', messageId)
        return
      }
      await controller.sendMessage(message.content)
    } catch (error) {
      logger.error('Failed to retry message:', error)
      throw error
    }
  }

  const saveEdit = (id: string, content: string) => controller.editMessage(id, content)

  return { copyMessage, deleteMessage, retryMessage, saveEdit }
}
