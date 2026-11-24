<template>
  <div ref="messagesContainer" class="chat-stream p-4" v-bind="$attrs">
    <!-- Screen reader status announcements -->
    <div role="status" aria-live="polite" aria-atomic="true" class="sr-only">{{ screenReaderStatus }}</div>

    <EmptyState
      v-if="showEmptyState"
      :title="$t('chat.interface.startConversation')"
      :description="$t('chat.emptyState')"
    >
      <template #icon><Icon name="comments" size="xl" /></template>
    </EmptyState>

    <div
      v-else
      role="log"
      aria-live="polite"
      aria-atomic="false"
      aria-relevant="additions"
      :aria-label="$t('chat.messages.conversation')"
    >
      <!-- Issue #1314: virtual scroll spacer sets the total scrollable height -->
      <div class="relative w-full" :style="{ height: `${totalSize}px` }">
        <div
          v-for="vItem in virtualItems"
          :key="String(vItem.key)"
          class="absolute top-0 left-0 w-full pb-1"
          :data-index="vItem.index"
          :ref="(el: any) => el && measureElement(el as Element)"
          :style="{ transform: `translateY(${vItem.start}px)` }"
        >
          <!-- Issue #1314: local alias via single-element v-for -->
          <template v-for="message in [filteredMessages[vItem.index]]" :key="message?.id ?? vItem.index">
            <ChatMessageRow
              :message="message"
              :fallback-info="getFallbackForMessage(message.id)"
              @edit="editMessage"
              @copy="copyMessage"
              @delete="deleteMessage"
              @retry="retryMessage"
            >
              <ChatMessageContent
                :message="message"
                :is-typing="store.isTyping"
                :is-last="isLastMessage(message)"
                :show-json="!!displaySettings.showJson"
                @citation-step="scrollToStep"
              />
            </ChatMessageRow>
          </template>
        </div>
      </div>

      <!-- AI typing indicator -->
      <TypingIndicator
        v-if="store.isTyping"
        :is-typing="store.isTyping"
        :message-complexity="typingComplexity"
        :streaming-preview="store.streamingPreview"
      />

      <!-- Loading skeleton for initial response -->
      <StableLoadingState
        v-if="store.isTyping && !store.currentMessages.length"
        :is-loading="store.isTyping"
        :has-content="store.currentMessages.length > 0"
        variant="chat"
      >
        <SkeletonLoader variant="chat-message" :animated="true" />
      </StableLoadingState>
    </div>
  </div>

  <ChatMessageEditModal
    v-model="showEditModal"
    v-model:content="editingContent"
    @save="saveEditedMessage"
    @cancel="cancelEdit"
  />
</template>

<script setup lang="ts">
/**
 * The chat message stream (#18243, step 5a batch 2): the virtual list, the empty state, the
 * typing indicator and the edit dialog. Rows, bodies, approvals and the edit dialog live in
 * ChatMessageRow / ChatMessageContent / ChatMessageApproval / ChatMessageEditModal; the state
 * helpers in composables/chat/useChatMessage*. Behaviour is unchanged by the split.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { EmptyState } from '@autobot/ui'
import { useDisplaySettings } from '@/composables/useDisplaySettings'
import { useProviderFallbackChip } from '@/composables/useProviderFallbackChip'
import { useVirtualChatScroll } from '@/composables/useVirtualChatScroll'
import { useChatMessageActions } from '@/composables/chat/useChatMessageActions'
import { useChatMessageEdit } from '@/composables/chat/useChatMessageEdit'
import { useChatMessageFilter } from '@/composables/chat/useChatMessageFilter'
import { getSenderName } from '@/composables/chat/useChatMessageView'
import { useChatScreenReader } from '@/composables/chat/useChatScreenReader'
import { provideMessageApproval } from '@/composables/chat/useMessageApprovalContext'
import { useChatStore, type ChatMessage } from '@/stores/useChatStore'
import { useToolCallDetection, type DetectedToolCall } from '@/composables/chat/useToolCallDetection'
import { createLogger } from '@/utils/debugUtils'
import ChatMessageContent from '@/components/chat/ChatMessageContent.vue'
import ChatMessageEditModal from '@/components/chat/ChatMessageEditModal.vue'
import ChatMessageRow from '@/components/chat/ChatMessageRow.vue'
import TypingIndicator from '@/components/chat/TypingIndicator.vue'
import Icon from '@/components/ui/Icon.vue'
import SkeletonLoader from '@/components/ui/SkeletonLoader.vue'
import StableLoadingState from '@/components/ui/StableLoadingState.vue'

const logger = createLogger('ChatMessages')

// Disable automatic attribute inheritance
defineOptions({ inheritAttrs: false })

const emit = defineEmits<{ 'tool-call-detected': [toolCall: DetectedToolCall] }>()

const { t } = useI18n()
const { detectToolCalls } = useToolCallDetection((toolCall) => emit('tool-call-detected', toolCall))
defineExpose({ detectToolCalls })
const store = useChatStore()
const { displaySettings } = useDisplaySettings()
const { copyMessage, deleteMessage, retryMessage, saveEdit } = useChatMessageActions()
const { permissionStore } = provideMessageApproval()

// #11997: correlate live PROVIDER_FALLBACK events to the assistant message they answered.
const { start: startFallbackTracking, getFallbackForMessage } = useProviderFallbackChip()

const messagesContainer = ref<HTMLElement>()
const { filteredMessages, showEmptyState } = useChatMessageFilter(store, displaySettings)
const { showEditModal, editingContent, editMessage, cancelEdit, saveEditedMessage } = useChatMessageEdit(saveEdit)

// Issue #1314: virtual scrolling
const { virtualItems, totalSize, measureElement, scrollToBottom, scrollToStep } = useVirtualChatScroll({
  messagesContainerRef: messagesContainer,
  filteredMessages,
  isTyping: computed(() => store.isTyping),
  currentSessionId: computed(() => store.currentSessionId),
})

const { screenReaderStatus } = useChatScreenReader(store, scrollToBottom, (sender, preview) =>
  t('chat.messages.newMessageAnnouncement', { sender: getSenderName(sender, t), preview }))

const isLastMessage = (message: ChatMessage): boolean => {
  const messages = store.currentMessages
  return messages.length > 0 && messages[messages.length - 1].id === message.id
}

/** Length of the last message, which the indicator turns into its response-time estimate (no message: the 5s default). */
const NO_MESSAGE_COMPLEXITY = 300
const typingComplexity = computed(() => {
  const last = store.currentMessages[store.currentMessages.length - 1]
  return last ? last.content.length : NO_MESSAGE_COMPLEXITY
})

/** #11997: resolve a fallback event's conversation id to that conversation's last assistant message. */
function resolveFallbackTargetMessage(conversationId: string): string | null {
  // #11994: ONLY the event's own conversation, never the current session (cross-conversation leak).
  const session = store.sessions.find((s) => s.id === conversationId)
  if (!session) return null
  const msgs = session.messages ?? []
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].sender === 'assistant') return msgs[i].id
  }
  return null
}

let stopFallbackTracking: (() => void) | null = null

onMounted(async () => {
  stopFallbackTracking = startFallbackTracking(resolveFallbackTargetMessage)
  // Permission v2: initialise the permission store
  try {
    await permissionStore.initialize()
    logger.debug('Permission store initialized:', { enabled: permissionStore.isEnabled, mode: permissionStore.currentMode })
  } catch (error) {
    logger.warn('Failed to initialize permission store:', error)
  }
})

onUnmounted(() => {
  stopFallbackTracking?.()
  stopFallbackTracking = null
})
</script>
