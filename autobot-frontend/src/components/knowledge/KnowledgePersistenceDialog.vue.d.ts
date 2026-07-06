// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { DefineComponent } from 'vue'

export interface KnowledgeChatContext {
  topic?: string
  keywords?: string[]
  file_count?: number
}

declare const KnowledgePersistenceDialog: DefineComponent<
  {
    visible?: boolean
    chatId?: string | null
    chatContext?: KnowledgeChatContext | null
  },
  Record<string, never>,
  unknown
>

export default KnowledgePersistenceDialog
