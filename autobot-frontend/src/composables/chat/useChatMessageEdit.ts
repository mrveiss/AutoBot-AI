// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/** Edit-message modal state (#18243), moved out of ChatMessages.vue (the textarea focus lives in ChatMessageEditModal). The save goes through the controller. */
import { ref } from 'vue'
import type { ChatMessage } from '@/stores/useChatStore'

export function useChatMessageEdit(save: (id: string, content: string) => void) {
  const showEditModal = ref(false)
  const editingContent = ref('')
  const editingMessage = ref<ChatMessage | null>(null)

  function editMessage(message: ChatMessage) {
    editingMessage.value = message
    editingContent.value = message.content
    showEditModal.value = true
  }

  function cancelEdit() {
    showEditModal.value = false
    editingMessage.value = null
    editingContent.value = ''
  }

  function saveEditedMessage() {
    if (editingMessage.value && editingContent.value.trim()) {
      save(editingMessage.value.id, editingContent.value.trim())
      cancelEdit()
    }
  }

  return { showEditModal, editingContent, editingMessage, editMessage, cancelEdit, saveEditedMessage }
}
