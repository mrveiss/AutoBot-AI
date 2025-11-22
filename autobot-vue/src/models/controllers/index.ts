// Controller exports - Business logic layer for AutoBot
export { ChatController } from './ChatController'
export { KnowledgeController } from './KnowledgeController'

// Controller composables for Vue components
import { reactive } from 'vue'
import { ChatController } from './ChatController'
import { KnowledgeController } from './KnowledgeController'

// Singleton controller instances
const chatController = reactive(new ChatController())
const knowledgeController = reactive(new KnowledgeController())

// Composable hooks for using controllers in components
export function useChatController() {
  return chatController
}

export function useKnowledgeController() {
  return knowledgeController
}