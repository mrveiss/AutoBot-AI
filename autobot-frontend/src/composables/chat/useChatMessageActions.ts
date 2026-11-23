// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Copy, delete and retry for a chat message (#18243, step 5a batch 2), moved out of
 * ChatMessages.vue. Delete and retry go through the same controller calls as before.
 */
import { useI18n } from 'vue-i18n'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useChatController } from '@/models/controllers'
import { useChatStore, type ChatMessage } from '@/stores/useChatStore'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useChatMessageActions')

/** Clipboard API first; the legacy `execCommand` path for browsers without it. */
export async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    const area = document.createElement('textarea')
    area.value = text
    document.body.appendChild(area)
    area.select()
    document.execCommand('copy')
    document.body.removeChild(area)
  }
}

export function useChatMessageActions() {
  const { t } = useI18n()
  const { confirm } = useConfirmDialog()
  const store = useChatStore()
  const controller = useChatController()

  const copyMessage = (message: ChatMessage) => copyText(message.content)

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
    }
  }

  const saveEdit = (id: string, content: string) => controller.editMessage(id, content)

  return { copyMessage, deleteMessage, retryMessage, saveEdit }
}
