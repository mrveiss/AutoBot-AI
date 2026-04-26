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
  {},
  unknown
>

export default KnowledgePersistenceDialog
