<template>
  <div
    class="p-4"
    ref="messagesContainer"
    v-bind="$attrs"
  >
    <!-- Screen reader status announcements -->
    <div role="status" aria-live="polite" aria-atomic="true" class="sr-only">
      {{ screenReaderStatus }}
    </div>

    <EmptyState
      v-if="showEmptyState"
      icon="fas fa-comments"
      title="Start a conversation"
      message="Send a message to begin chatting with the AI assistant."
    />

    <div
      v-else
      class="space-y-1"
      role="log"
      aria-live="polite"
      aria-atomic="false"
      aria-relevant="additions"
      aria-label="Chat conversation"
    >
      <div
        v-for="message in filteredMessages"
        :key="message.id"
        class="message-wrapper"
        :class="getMessageWrapperClass(message)"
      >
        <!-- Message Header -->
        <div class="message-header">
          <div class="flex items-center gap-1.5">
            <div class="message-avatar" :class="getAvatarClass(message.sender)">
              <i :class="getSenderIcon(message.sender, message.type || message.metadata?.display_type)" aria-hidden="true"></i>
            </div>
            <div class="message-info">
              <span class="sender-name">
                {{ getSenderName(message.sender) }}
                <span v-if="message.sender === 'assistant' && message.metadata?.model" class="model-name">
                  ({{ message.metadata.model }})
                </span>
              </span>
              <span class="message-time">{{ formatTime(message.timestamp) }}</span>
            </div>
          </div>

          <div class="message-actions">
            <BaseButton
              v-if="message.sender === 'user'"
              variant="ghost"
              size="xs"
              @click="editMessage(message)"
              class="action-btn"
              aria-label="Edit message"
              title="Edit message"
            >
              <i class="fas fa-edit" aria-hidden="true"></i>
            </BaseButton>
            <BaseButton
              variant="ghost"
              size="xs"
              @click="copyMessage(message)"
              class="action-btn"
              aria-label="Copy message"
              title="Copy message"
            >
              <i class="fas fa-copy" aria-hidden="true"></i>
            </BaseButton>
            <BaseButton
              variant="ghost"
              size="xs"
              @click="deleteMessage(message)"
              class="action-btn danger"
              aria-label="Delete message"
              title="Delete message"
            >
              <i class="fas fa-trash" aria-hidden="true"></i>
            </BaseButton>
          </div>
        </div>

        <!-- Enhanced Message Status -->
        <div v-if="message.sender === 'user'" class="message-status-container">
          <MessageStatus
            :status="(message.status === 'error' ? 'failed' : message.status) || 'sent'"
            :show-text="true"
            :timestamp="message.timestamp"
            :error="message.error"
            @retry="retryMessage(message.id)"
          />
        </div>

        <!-- Issue #690: Overseer Agent Plan Message -->
        <OverseerPlanMessage
          v-if="message.type === 'overseer_plan' && message.metadata?.plan"
          :plan="message.metadata.plan"
          :steps="message.metadata?.steps"
        />

        <!-- Issue #690: Overseer Agent Step Message -->
        <OverseerStepMessage
          v-else-if="message.type === 'overseer_step' && message.metadata?.step"
          :step="message.metadata.step"
        />

        <!-- Message Content -->
        <div v-else class="message-content" :class="getContentClass(message)">
          <!-- Streaming content with typing indicator -->
          <div v-if="isStreamingMessage(message)" class="streaming-content">
            <div class="message-text" v-html="formatMessageContent(message.content)"></div>
            <div v-if="store.isTyping && isLastMessage(message)" class="typing-indicator">
              <div class="typing-dots">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>

          <!-- Regular message content -->
          <div v-else class="message-text" v-html="formatMessageContent(message.content)"></div>

          <!-- Message Metadata -->
          <div v-if="message.metadata && shouldShowMetadata(message)" class="message-metadata">
            <div class="metadata-items">
              <span v-if="message.metadata.model" class="metadata-item">
                <i class="fas fa-robot" aria-hidden="true"></i>
                {{ message.metadata.model }}
              </span>
              <span v-if="message.metadata.tokens" class="metadata-item">
                <i class="fas fa-coins" aria-hidden="true"></i>
                {{ message.metadata.tokens }} tokens
              </span>
              <span v-if="message.metadata.duration" class="metadata-item">
                <i class="fas fa-clock" aria-hidden="true"></i>
                {{ message.metadata.duration }}ms
              </span>
            </div>
          </div>

          <!-- Issue #249: Knowledge Base Citations Display -->
          <div
            v-if="message.sender === 'assistant' && message.metadata?.used_knowledge && message.metadata?.citations?.length > 0"
            class="knowledge-citations"
          >
            <div class="citations-header" @click="toggleCitations(message.id)">
              <div class="citations-header-left">
                <i class="fas fa-brain text-indigo-600" aria-hidden="true"></i>
                <span class="citations-label">Knowledge Sources</span>
                <span class="citations-count">{{ message.metadata.citations.length }}</span>
              </div>
              <i :class="expandedCitations.has(message.id) ? 'fas fa-chevron-up' : 'fas fa-chevron-down'" aria-hidden="true"></i>
            </div>
            <Transition name="slide-fade">
              <div v-if="expandedCitations.has(message.id)" class="citations-list">
                <div
                  v-for="(citation, idx) in message.metadata.citations"
                  :key="citation.id || idx"
                  class="citation-item"
                >
                  <div class="citation-rank">[{{ citation.rank || idx + 1 }}]</div>
                  <div class="citation-content">
                    <div class="citation-text">{{ truncateCitation(citation.content) }}</div>
                    <div class="citation-meta">
                      <span class="citation-score" :class="getScoreClass(citation.score)">
                        <i class="fas fa-chart-line" aria-hidden="true"></i>
                        {{ (citation.score * 100).toFixed(0) }}%
                      </span>
                      <span v-if="citation.source" class="citation-source">
                        <i class="fas fa-file-alt" aria-hidden="true"></i>
                        {{ formatSourcePath(citation.source) }}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </Transition>
          </div>

          <!-- Attachments -->
          <div v-if="message.attachments && message.attachments.length > 0" class="message-attachments">
            <div class="attachment-header">
              <i class="fas fa-paperclip" aria-hidden="true"></i>
              <span>{{ message.attachments.length }} attachment{{ message.attachments.length > 1 ? 's' : '' }}</span>
            </div>
            <div class="attachment-list">
              <div
                v-for="attachment in message.attachments"
                :key="attachment.id"
                class="attachment-item"
                @click="viewAttachment(attachment)"
              >
                <i :class="getAttachmentIcon(attachment.type)"></i>
                <span class="attachment-name">{{ attachment.name }}</span>
                <span class="attachment-size">{{ formatFileSize(attachment.size) }}</span>
              </div>
            </div>
          </div>

          <!-- Code blocks with syntax highlighting -->
          <div v-if="hasCodeBlocks(message.content)" class="code-blocks">
            <!-- This would be rendered by the formatMessageContent function -->
          </div>

          <!-- Command Approval Request UI - Inline in chat history -->
          <!-- PRE-APPROVED STATE - Show blue auto-approval -->
          <div v-if="message.metadata?.approval_status === 'pre_approved'" class="approval-confirmed approval-pre-approved">
            <div class="approval-header">
              <i class="fas fa-shield-check text-blue-600" aria-hidden="true"></i>
              <span class="font-semibold">Auto-Approved</span>
            </div>
            <div class="approval-details">
              <div class="approval-detail-item">
                <span class="detail-label">Command:</span>
                <code class="detail-value">{{ message.metadata.command }}</code>
              </div>
              <div v-if="message.metadata.approval_comment" class="approval-detail-item">
                <span class="detail-label">Reason:</span>
                <span class="detail-value">{{ message.metadata.approval_comment }}</span>
              </div>
            </div>
          </div>

          <!-- USER APPROVED STATE - Show green confirmation -->
          <div v-else-if="message.metadata?.approval_status === 'approved'" class="approval-confirmed approval-approved">
            <div class="approval-header">
              <i class="fas fa-check-circle text-green-600" aria-hidden="true"></i>
              <span class="font-semibold">Command Approved</span>
            </div>
            <div class="approval-details">
              <div class="approval-detail-item">
                <span class="detail-label">Command:</span>
                <code class="detail-value">{{ message.metadata.command }}</code>
              </div>
              <div v-if="message.metadata.approval_comment" class="approval-detail-item">
                <span class="detail-label">Comment:</span>
                <span class="detail-value">{{ message.metadata.approval_comment }}</span>
              </div>
            </div>
          </div>

          <!-- DENIED STATE - Show red rejection -->
          <div v-else-if="message.metadata?.approval_status === 'denied'" class="approval-confirmed approval-denied">
            <div class="approval-header">
              <i class="fas fa-times-circle text-red-600" aria-hidden="true"></i>
              <span class="font-semibold">Command Denied</span>
            </div>
            <div class="approval-details">
              <div class="approval-detail-item">
                <span class="detail-label">Command:</span>
                <code class="detail-value">{{ message.metadata.command }}</code>
              </div>
              <div v-if="message.metadata.approval_comment" class="approval-detail-item">
                <span class="detail-label">Reason:</span>
                <span class="detail-value">{{ message.metadata.approval_comment }}</span>
              </div>
            </div>
          </div>

          <!-- PENDING APPROVAL STATE - Show approval buttons -->
          <!-- FIXED: Only show if requires_approval AND no approval_status yet -->
          <div v-else-if="message.metadata?.requires_approval && !message.metadata?.approval_status" class="approval-request">
            <div class="approval-header">
              <i class="fas fa-exclamation-triangle text-yellow-600" aria-hidden="true"></i>
              <span class="font-semibold">Command Approval Required</span>
            </div>
            <div class="approval-details">
              <div class="approval-detail-item">
                <span class="detail-label">Command:</span>
                <code class="detail-value">{{ message.metadata.command }}</code>
              </div>
              <div class="approval-detail-item">
                <span class="detail-label">Risk Level:</span>
                <span class="detail-value" :class="getRiskClass(message.metadata.risk_level)">
                  {{ message.metadata.risk_level }}
                </span>
              </div>
              <div v-if="message.metadata.purpose" class="approval-detail-item">
                <span class="detail-label">Purpose:</span>
                <span class="detail-value">{{ message.metadata.purpose }}</span>
              </div>
              <div v-if="message.metadata.reasons && message.metadata.reasons.length > 0" class="approval-detail-item">
                <span class="detail-label">Reasons:</span>
                <span class="detail-value">{{ message.metadata.reasons.join(', ') }}</span>
              </div>

              <!-- Interactive Command Warning (Issue #33) -->
              <div v-if="message.metadata.is_interactive" class="approval-detail-item interactive-warning">
                <div class="interactive-header">
                  <i class="fas fa-keyboard text-blue-600" aria-hidden="true"></i>
                  <span class="detail-label font-semibold text-blue-700">Interactive Command</span>
                </div>
                <div class="interactive-info">
                  <p class="text-sm text-blueGray-600 mb-2">
                    This command requires user input (stdin). You'll be prompted after approval.
                  </p>
                  <div v-if="message.metadata.interactive_reasons && message.metadata.interactive_reasons.length > 0" class="interactive-reasons">
                    <span class="text-xs font-medium text-blueGray-500">Input required for:</span>
                    <ul class="text-xs text-blueGray-600 mt-1 ml-4 list-disc">
                      <li v-for="(reason, idx) in message.metadata.interactive_reasons" :key="idx">{{ reason }}</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
            <!-- Comment input (when adding comment) -->
            <div v-if="showCommentInput && activeCommentSessionId === message.metadata.terminal_session_id" class="comment-input-section">
              <textarea
                v-model="approvalComment"
                class="comment-textarea"
                placeholder="Add a comment or reason for this decision..."
                rows="2"
                @keydown.ctrl.enter="submitApprovalWithComment(message.metadata.terminal_session_id, pendingApprovalDecision)"
                @keydown.meta.enter="submitApprovalWithComment(message.metadata.terminal_session_id, pendingApprovalDecision)"
              ></textarea>
              <div class="comment-actions">
                <BaseButton
                  variant="secondary"
                  size="sm"
                  @click="cancelComment"
                  class="cancel-comment-btn"
                  aria-label="Cancel comment"
                >
                  <i class="fas fa-times" aria-hidden="true"></i>
                  <span>Cancel</span>
                </BaseButton>
                <BaseButton
                  variant="primary"
                  size="sm"
                  @click="submitApprovalWithComment(message.metadata.terminal_session_id, pendingApprovalDecision)"
                  :disabled="!approvalComment.trim()"
                  class="submit-comment-btn"
                  :aria-label="`Submit ${pendingApprovalDecision ? 'approval' : 'denial'} with comment`"
                >
                  <i class="fas fa-check" aria-hidden="true"></i>
                  <span>Submit {{ pendingApprovalDecision ? 'Approval' : 'Denial' }}</span>
                </BaseButton>
              </div>
            </div>

            <!-- Auto-approve checkbox for future similar commands -->
            <div class="auto-approve-section">
              <label class="auto-approve-checkbox">
                <input
                  type="checkbox"
                  v-model="autoApproveFuture"
                  class="checkbox-input"
                />
                <span class="checkbox-label">
                  <i class="fas fa-shield-check" aria-hidden="true"></i>
                  Automatically approve similar commands in the future
                </span>
              </label>
              <div v-if="autoApproveFuture" class="auto-approve-hint">
                <i class="fas fa-info-circle" aria-hidden="true"></i>
                <span>Commands with the same pattern and risk level will be auto-approved</span>
              </div>
            </div>

            <!-- Permission v2: Remember for this project checkbox -->
            <div v-if="permissionStore.isEnabled" class="remember-project-section">
              <label class="remember-project-checkbox">
                <input
                  type="checkbox"
                  v-model="rememberForProject"
                  class="checkbox-input"
                />
                <span class="checkbox-label">
                  <i class="fas fa-folder-open" aria-hidden="true"></i>
                  Remember this approval for this project
                </span>
              </label>
              <div v-if="rememberForProject" class="remember-project-hint">
                <i class="fas fa-info-circle" aria-hidden="true"></i>
                <span>Similar commands in this project will be auto-approved ({{ currentProjectPath || 'No project context' }})</span>
              </div>
            </div>

            <div class="approval-actions">
              <BaseButton
                variant="success"
                size="sm"
                @click="approveCommand(message.metadata.terminal_session_id, true, undefined, message.metadata.command_id, { command: message.metadata.command, risk_level: message.metadata.risk_level })"
                :disabled="processingApproval || showCommentInput"
                class="approve-btn"
                aria-label="Approve command"
              >
                <i class="fas fa-check" aria-hidden="true"></i>
                <span>Approve</span>
              </BaseButton>
              <BaseButton
                variant="outline"
                size="sm"
                @click="promptForComment(message.metadata.terminal_session_id)"
                :disabled="processingApproval || showCommentInput"
                class="comment-btn"
                aria-label="Add comment to approval decision"
              >
                <i class="fas fa-comment" aria-hidden="true"></i>
                <span>Comment</span>
              </BaseButton>
              <BaseButton
                variant="danger"
                size="sm"
                @click="approveCommand(message.metadata.terminal_session_id, false, undefined, message.metadata.command_id, { command: message.metadata.command, risk_level: message.metadata.risk_level })"
                :disabled="processingApproval || showCommentInput"
                class="deny-btn"
                aria-label="Deny command"
              >
                <i class="fas fa-times" aria-hidden="true"></i>
                <span>Deny</span>
              </BaseButton>
            </div>
            <div v-if="processingApproval" class="approval-processing">
              <LoadingSpinner size="sm" />
              <span>Processing approval...</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Enhanced AI typing indicator -->
      <div v-if="store.isTyping" class="message-wrapper assistant-message typing-message">
        <div class="message-header">
          <div class="flex items-center gap-1.5">
            <div class="message-avatar assistant">
              <LoadingSpinner variant="pulse" size="sm" color="#3b82f6" />
            </div>
            <div class="message-info">
              <span class="sender-name">AI Assistant</span>
              <span class="message-time">{{ typingStatusText }}</span>
            </div>
          </div>
        </div>
        <div class="message-content">
          <div class="enhanced-typing-indicator">
            <div class="typing-animation">
              <div class="typing-dots-enhanced">
                <span></span>
                <span></span>
                <span></span>
                <span></span>
              </div>
              <div class="typing-wave"></div>
            </div>
            <div class="typing-status">
              <span class="typing-text">{{ typingDetailText }}</span>
              <span v-if="estimatedResponseTime" class="typing-eta">
                ~{{ estimatedResponseTime }}s
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Loading skeleton for initial response -->
      <div v-if="store.isTyping && !store.currentMessages.length" class="message-skeleton">
        <SkeletonLoader variant="chat-message" :animated="true" />
      </div>
    </div>
  </div>

  <!-- Edit Message Modal -->
  <BaseModal
    v-model="showEditModal"
    title="Edit Message"
    size="medium"
  >
    <textarea
      v-model="editingContent"
      class="flex-1 w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
      placeholder="Enter your message..."
      @keydown.ctrl.enter="saveEditedMessage"
      @keydown.meta.enter="saveEditedMessage"
      ref="editTextarea"
      rows="6"
    ></textarea>
    <div class="text-xs text-gray-500 mt-2">
      Press Ctrl+Enter (Cmd+Enter on Mac) to save
    </div>

    <template #actions>
      <BaseButton
        variant="secondary"
        @click="cancelEdit"
      >
        Cancel
      </BaseButton>
      <BaseButton
        variant="primary"
        @click="saveEditedMessage"
        :disabled="!editingContent.trim()"
      >
        Save
      </BaseButton>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted, onUnmounted } from 'vue'
import { useChatStore } from '@/stores/useChatStore'
import { useChatController } from '@/models/controllers'
import { useDisplaySettings } from '@/composables/useDisplaySettings'
import { usePermissionStore } from '@/stores/usePermissionStore'
import type { ChatMessage } from '@/stores/useChatStore'
import MessageStatus from '@/components/ui/MessageStatus.vue'
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue'
import SkeletonLoader from '@/components/ui/SkeletonLoader.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import OverseerPlanMessage from '@/components/chat/OverseerPlanMessage.vue'
import OverseerStepMessage from '@/components/chat/OverseerStepMessage.vue'
import appConfig from '@/config/AppConfig.js'
import { formatFileSize, formatTime } from '@/utils/formatHelpers'
import { useToast } from '@/composables/useToast'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ChatMessages')

// Disable automatic attribute inheritance
defineOptions({
  inheritAttrs: false
})

// Define emits for parent component
const emit = defineEmits<{
  'tool-call-detected': [toolCall: {
    command: string
    host: string
    purpose: string
    params: Record<string, any>
    terminal_session_id: string | null
  }]
}>()

const store = useChatStore()
const controller = useChatController()
const { displaySettings } = useDisplaySettings()
const permissionStore = usePermissionStore()

// Toast notifications
const { showToast } = useToast()
const notify = (message: string, type: 'info' | 'success' | 'warning' | 'error' = 'info') => {
  showToast(message, type, type === 'error' ? 5000 : 3000)
}

// Refs
const messagesContainer = ref<HTMLElement>()
const editTextarea = ref<HTMLTextAreaElement>()

// Screen reader announcements
const screenReaderStatus = ref('')

// Edit modal state
const showEditModal = ref(false)
const editingContent = ref('')
const editingMessage = ref<ChatMessage | null>(null)

// Enhanced typing indicator state
const typingStartTime = ref<number | null>(null)
const estimatedResponseTime = ref<number | null>(null)

// Issue #249: Citation display state
const expandedCitations = ref<Set<string>>(new Set())

// Approval state
const processingApproval = ref(false)

// Comment functionality state
const showCommentInput = ref(false)
const activeCommentSessionId = ref<string | null>(null)
const approvalComment = ref('')
const pendingApprovalDecision = ref<boolean | null>(null)

// Auto-approve functionality state
const autoApproveFuture = ref(false)

// Permission v2: Project memory state
const rememberForProject = ref(false)
const currentProjectPath = ref<string | null>(null)

// CRITICAL FIX: Prevent EmptyState from flashing during polling/reactivity updates
// Once messages have been loaded, never show EmptyState again (prevents flicker)
const hasEverHadMessages = ref(false)

// Track when we've had messages to prevent empty state flash
watch(() => store.currentMessages.length, (newLen) => {
  if (newLen > 0) {
    hasEverHadMessages.value = true
  }
}, { immediate: true })

// Reset when session changes (new chat should show empty state)
watch(() => store.currentSessionId, () => {
  // Only reset if the new session has no messages
  if (store.currentMessages.length === 0) {
    hasEverHadMessages.value = false
  }
})

// Computed: Show empty state only if truly empty (never had messages in this session)
const showEmptyState = computed(() => {
  return store.currentMessages.length === 0 && !hasEverHadMessages.value && !store.isTyping
})

// Computed
const filteredMessages = computed(() => {
  return store.currentMessages.filter(message => {
    // Issue #650: Check both top-level type AND metadata.display_type for filtering
    // Backend now sends display_type in metadata for proper categorization
    const displayType = message.type || message.metadata?.display_type || 'response'

    // Filter messages based on display settings and message type
    // Show Utility Messages - controls tool usage messages
    if (displayType === 'utility' && !displaySettings.value.showUtility) return false

    // Show Thoughts - controls LLM thought messages
    if (displayType === 'thought' && !displaySettings.value.showThoughts) return false

    // Show Planning Messages - controls LLM planning process messages
    if (displayType === 'planning' && !displaySettings.value.showPlanning) return false

    // Show Debug Messages - controls debug output
    if (displayType === 'debug' && !displaySettings.value.showDebug) return false

    // Show Sources - controls source reference messages
    if (displayType === 'sources' && !displaySettings.value.showSources) return false

    // Always show regular messages and responses
    return true
  })
})

const typingStatusText = computed(() => {
  const elapsed = typingStartTime.value ? Date.now() - typingStartTime.value : 0
  if (elapsed < 2000) return 'Thinking...'
  if (elapsed < 5000) return 'Processing...'
  if (elapsed < 10000) return 'Analyzing...'
  return 'Working on it...'
})

const typingDetailText = computed(() => {
  // Issue #691: Display actual streaming content when available
  // This shows real LLM thinking/reasoning instead of hardcoded placeholders
  if (store.streamingPreview && store.streamingPreview.trim()) {
    return store.streamingPreview
  }

  // Fallback to time-based placeholder text when no streaming content yet
  const elapsed = typingStartTime.value ? Date.now() - typingStartTime.value : 0
  const details = [
    'Understanding your request...',
    'Searching knowledge base...',
    'Formulating response...',
    'Crafting detailed answer...',
    'Reviewing response quality...'
  ]
  const index = Math.min(Math.floor(elapsed / 2000), details.length - 1)
  return details[index]
})

// Methods
const getMessageWrapperClass = (message: ChatMessage): string => {
  const classes = ['message']
  classes.push(`${message.sender}-message`)

  // Add message type class for type-specific styling
  // Issue #680: Exclude streaming types from type-class assignment to prevent wrong badges
  const messageType = message.type || message.metadata?.display_type
  const noTypeClassTypes = ['response', 'message', 'default', 'llm_response', 'llm_response_chunk']
  if (messageType && !noTypeClassTypes.includes(messageType)) {
    classes.push(`type-${messageType}`)
  }

  if (message.status === 'error') classes.push('error')
  if (message.status === 'sending') classes.push('sending')

  return classes.join(' ')
}

const getAvatarClass = (sender: string): string => {
  return `message-avatar ${sender}`
}

const getSenderIcon = (sender: string, messageType?: string): string => {
  // Type-specific icons take precedence over sender icons
  if (messageType) {
    const typeIcons: Record<string, string> = {
      thought: 'fas fa-brain',
      planning: 'fas fa-list-check',
      debug: 'fas fa-bug',
      utility: 'fas fa-wrench',
      sources: 'fas fa-book-open',
      command_approval_request: 'fas fa-shield-halved',
      terminal_output: 'fas fa-terminal',
      terminal_command: 'fas fa-terminal',
      overseer_plan: 'fas fa-sitemap',
      overseer_step: 'fas fa-tasks',
      llm_response: 'fas fa-robot',
      llm_response_chunk: 'fas fa-robot'
    }
    if (typeIcons[messageType]) return typeIcons[messageType]
  }

  const icons: Record<string, string> = {
    user: 'fas fa-user',
    assistant: 'fas fa-robot',
    system: 'fas fa-cog',
    error: 'fas fa-exclamation-triangle',
    thought: 'fas fa-brain',
    'tool-code': 'fas fa-code',
    'tool-output': 'fas fa-terminal'
  }

  return icons[sender] || 'fas fa-comment'
}

const getSenderName = (sender: string): string => {
  const names = {
    user: 'You',
    assistant: 'AI Assistant',
    system: 'System',
    error: 'Error',
    thought: 'AI Thought',
    'tool-code': 'Code Execution',
    'tool-output': 'Output'
  }

  return names[sender as keyof typeof names] || sender
}

const getContentClass = (message: ChatMessage): string => {
  const classes = ['message-content']
  if (message.sender === 'user') classes.push('user-content')
  if (message.sender === 'assistant') classes.push('assistant-content')
  if (message.sender === 'system') classes.push('system-content')

  return classes.join(' ')
}

// NOTE: formatTime removed - now using shared utility from @/utils/formatHelpers

const formatMessageContent = (content: string): string => {
  // Strip ANSI escape codes FIRST (terminal color codes, cursor movements, etc.)
  // This removes sequences like: \x1b[31m (red), \x1b[0m (reset), \x1b]0;... (set title), [?2004h, etc.
  let formatted = content
    .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '') // CSI sequences: \x1b[...m, \x1b[...H, etc.
    .replace(/\x1b\][0-9;]*[^\x07]*\x07/g, '') // OSC sequences: \x1b]...BEL
    .replace(/\x1b\][0-9;]*[^\x07\x1b]*(?:\x1b\\)?/g, '') // OSC sequences: \x1b]...ST
    .replace(/\x1b[=>]/g, '') // Set numeric keypad mode
    .replace(/\x1b[()][AB012]/g, '') // Character set selection
    .replace(/\[[?\d;]*[hlHJ]/g, '') // Bracket sequences without ESC: [?2004h, etc.
    .replace(/\]0;[^\x07\n]*\x07?/g, '') // Set title without ESC: ]0;...
    .trim()

  // Strip message type tags (Issue #680: Tags should not be visible in chat)
  // These tags are used internally for message categorization but shouldn't display
  // Handles both complete tags [TAG] and malformed tags [TAG without closing bracket
  formatted = formatted
    .replace(/\[THOUGHT\]?/gi, '')
    .replace(/\[\/THOUGHT\]?/gi, '')
    .replace(/\[PLANNING\]?/gi, '')
    .replace(/\[\/PLANNING\]?/gi, '')
    .replace(/\[DEBUG\]?/gi, '')
    .replace(/\[\/DEBUG\]?/gi, '')
    .replace(/\[SOURCES\]?/gi, '')
    .replace(/\[\/SOURCES\]?/gi, '')
    .trim()

  // Strip TOOL_CALL tags (internal metadata that shouldn't be displayed)
  // Removes: <tool_call name="..." params="...">content</tool_call>
  formatted = formatted.replace(/<tool_call[^>]*>.*?<\/tool_call>/gs, '')

  // Process code blocks THIRD (after ANSI stripping and tool_call removal, before inline code and newlines)
  formatted = formatted.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
    return `<pre class="code-block${lang ? ` language-${lang}` : ''}"><code>${code.trim()}</code></pre>`
  })

  // Then basic markdown-like formatting
  formatted = formatted
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')

  // Links
  formatted = formatted.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>')

  return formatted
}

const getStatusText = (status: string): string => {
  const statusMap = {
    sending: 'Sending...',
    sent: 'Sent',
    error: 'Failed to send'
  }

  return statusMap[status as keyof typeof statusMap] || status
}

const isStreamingMessage = (message: ChatMessage): boolean => {
  return message.sender === 'assistant' && store.isTyping && isLastMessage(message)
}

const isLastMessage = (message: ChatMessage): boolean => {
  const messages = store.currentMessages
  return messages.length > 0 && messages[messages.length - 1].id === message.id
}

const shouldShowMetadata = (message: ChatMessage): boolean => {
  return !!displaySettings.value.showJson &&
         message.sender === 'assistant' &&
         !!message.metadata &&
         Object.keys(message.metadata).length > 0
}

const hasCodeBlocks = (content: string): boolean => {
  return /```[\s\S]*?```/.test(content)
}

// Issue #249: Citation helper functions
const toggleCitations = (messageId: string) => {
  if (expandedCitations.value.has(messageId)) {
    expandedCitations.value.delete(messageId)
  } else {
    expandedCitations.value.add(messageId)
  }
  // Force reactivity update for Set
  expandedCitations.value = new Set(expandedCitations.value)
}

const truncateCitation = (content: string, maxLength: number = 200): string => {
  if (!content) return ''
  if (content.length <= maxLength) return content
  return content.substring(0, maxLength).trim() + '...'
}

const getScoreClass = (score: number): string => {
  if (score >= 0.9) return 'score-excellent'
  if (score >= 0.8) return 'score-good'
  if (score >= 0.7) return 'score-acceptable'
  return 'score-low'
}

const formatSourcePath = (sourcePath: string): string => {
  if (!sourcePath) return 'Unknown'
  // Extract filename from path
  const parts = sourcePath.split('/')
  return parts[parts.length - 1] || sourcePath
}

const editMessage = async (message: ChatMessage) => {
  editingMessage.value = message
  editingContent.value = message.content
  showEditModal.value = true

  await nextTick()
  editTextarea.value?.focus()
}

const saveEditedMessage = async () => {
  if (editingMessage.value && editingContent.value.trim()) {
    controller.editMessage(editingMessage.value.id, editingContent.value.trim())
    cancelEdit()
  }
}

const cancelEdit = () => {
  showEditModal.value = false
  editingMessage.value = null
  editingContent.value = ''
}

const copyMessage = async (message: ChatMessage) => {
  try {
    await navigator.clipboard.writeText(message.content)
    // Could show a toast notification here
  } catch (error) {
    // Fallback for older browsers
    const textArea = document.createElement('textarea')
    textArea.value = message.content
    document.body.appendChild(textArea)
    textArea.select()
    document.execCommand('copy')
    document.body.removeChild(textArea)
  }
}

const deleteMessage = (message: ChatMessage) => {
  if (confirm('Delete this message? This action cannot be undone.')) {
    controller.deleteMessage(message.id)
  }
}

const getAttachmentIcon = (type: string): string => {
  if (type.startsWith('image/')) return 'fas fa-image'
  if (type.startsWith('video/')) return 'fas fa-video'
  if (type.startsWith('audio/')) return 'fas fa-music'
  if (type.includes('pdf')) return 'fas fa-file-pdf'
  if (type.includes('word')) return 'fas fa-file-word'
  if (type.includes('excel')) return 'fas fa-file-excel'
  return 'fas fa-file'
}

// NOTE: formatFileSize removed - now using shared utility from @/utils/formatHelpers

const viewAttachment = (attachment: any) => {
  // Handle attachment viewing
  if (attachment.url) {
    window.open(attachment.url, '_blank')
  }
}

const retryMessage = async (messageId: string) => {
  try {
    // Find the message in the store
    const message = store.currentMessages.find(m => m.id === messageId)
    if (!message || !message.content) {
      logger.error('Message not found or has no content:', messageId)
      return
    }

    // Resend the message using the controller
    await controller.sendMessage(message.content)
  } catch (error) {
    logger.error('Failed to retry message:', error)
  }
}

// TOOL_CALL Detection
const detectToolCalls = (message: ChatMessage) => {
  const toolCallRegex = /<TOOL_CALL\s+name="execute_command"\s+params='({.*?})'>(.*?)<\/TOOL_CALL>/gs
  const matches = [...message.content.matchAll(toolCallRegex)]

  for (const match of matches) {
    try {
      const params = JSON.parse(match[1])
      const description = match[2].trim()

      logger.debug('TOOL_CALL detected:', { command: params.command, host: params.host, purpose: description })

      // Search for terminal_session_id in recent assistant messages
      // The terminal_session_id might be in metadata of streaming chunks, not necessarily the message with TOOL_CALL
      let terminal_session_id = message.metadata?.terminal_session_id || null

      if (!terminal_session_id) {
        // Search backwards through recent assistant messages for terminal_session_id
        const recentAssistantMessages = store.currentMessages
          .filter(m => m.sender === 'assistant')
          .reverse()
          .slice(0, 10) // Check last 10 assistant messages

        for (const msg of recentAssistantMessages) {
          if (msg.metadata?.terminal_session_id) {
            terminal_session_id = msg.metadata.terminal_session_id
            logger.debug('Found terminal_session_id in message metadata:', terminal_session_id)
            break
          }
        }

        if (!terminal_session_id) {
          logger.warn('No terminal_session_id found in recent messages')
        }
      }

      // Emit event to parent to show approval dialog
      emit('tool-call-detected', {
        command: params.command,
        host: params.host || 'main',
        purpose: description,
        params: params,
        terminal_session_id: terminal_session_id
      })
    } catch (error) {
      logger.error('Failed to parse TOOL_CALL:', error)
    }
  }
}

// Poll command state from queue (event-driven, no timeouts!)
const pollCommandState = async (command_id: string, callback: (result: any) => void) => {
  const maxAttempts = 100  // 100 * 500ms = 50 seconds max
  let attempt = 0

  const poll = async () => {
    try {
      const backendUrl = await appConfig.getApiUrl(`/api/agent-terminal/commands/${command_id}`)
      const response = await fetch(backendUrl)

      if (!response.ok) {
        logger.error('Failed to get command state:', response.status)
        if (attempt < maxAttempts) {
          attempt++
          setTimeout(poll, 500)
        } else {
          callback({ state: 'error', error: 'HTTP error' })
        }
        return
      }

      const command = await response.json()
      logger.debug(`Command state (attempt ${attempt + 1}):`, command.state)

      // Check if command is finished
      if (command.state === 'completed' || command.state === 'failed' || command.state === 'denied') {
        logger.debug('Command finished:', {
          state: command.state,
          output_length: command.output?.length || 0,
          return_code: command.return_code
        })
        callback({
          state: command.state,
          output: command.output,
          stderr: command.stderr,
          return_code: command.return_code,
          command: command.command
        })
        return  // Stop polling
      }

      // Command still running - poll again
      if (attempt < maxAttempts) {
        attempt++
        setTimeout(poll, 500)  // Poll every 500ms
      } else {
        logger.error('Polling timed out after 50 seconds')
        callback({ state: 'timeout', error: 'Polling timeout' })
      }
    } catch (error) {
      logger.error('Polling error:', error)
      if (attempt < maxAttempts) {
        attempt++
        setTimeout(poll, 500)
      } else {
        callback({ state: 'error', error: (error as Error).message })
      }
    }
  }

  // Start polling
  logger.debug('Starting command state polling for:', command_id)
  poll()
}

// Command Approval - Use HTTP POST to agent-terminal API with dynamic URL
// Permission v2: Enhanced with project memory support
const approveCommand = async (
  terminal_session_id: string,
  approved: boolean,
  comment?: string,
  command_id?: string,
  commandInfo?: { command: string; risk_level: string }  // Permission v2: Command details for memory
) => {
  if (!terminal_session_id) {
    logger.error('No terminal_session_id provided for approval')
    return
  }

  processingApproval.value = true
  logger.debug(`${approved ? 'Approving' : 'Denying'} command for session:`, terminal_session_id)
  if (comment) {
    logger.debug('With comment:', comment)
  }
  if (autoApproveFuture.value) {
    logger.debug('Auto-approve similar commands in future:', autoApproveFuture.value)
  }
  if (rememberForProject.value) {
    logger.debug('Remember for project:', currentProjectPath.value)
  }

  try {
    // Get backend URL from appConfig
    const backendUrl = await appConfig.getApiUrl(`/api/agent-terminal/sessions/${terminal_session_id}/approve`)

    const response = await fetch(backendUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        approved,
        user_id: 'web_user',
        comment: comment || null,
        auto_approve_future: autoApproveFuture.value,  // Send auto-approve preference
        remember_for_project: rememberForProject.value,  // Permission v2
        project_path: currentProjectPath.value  // Permission v2
      })
    })

    const result = await response.json()
    logger.debug('Approval response:', result)

    if (result.status === 'approved' || result.status === 'denied') {
      logger.debug(`Command ${approved ? 'approved' : 'denied'} successfully`)
      notify(`Command ${approved ? 'approved' : 'denied'}`, approved ? 'success' : 'warning')

      // Update the message metadata to reflect approval status
      const targetMessage = store.currentMessages.find(
        msg => msg.metadata?.terminal_session_id === terminal_session_id &&
               msg.metadata?.requires_approval === true
      )

      if (targetMessage && targetMessage.metadata) {
        targetMessage.metadata.approval_status = result.status
        targetMessage.metadata.approval_comment = comment || result.comment
        logger.debug('Updated message approval status:', targetMessage.metadata)
      } else {
        logger.warn('Could not find message to update approval status')
      }

      // START POLLING: If approved and we have command_id, poll for completion
      if (result.status === 'approved' && approved && command_id) {
        logger.debug('Starting polling for approved command:', command_id)

        pollCommandState(command_id, (pollResult) => {
          logger.debug('Command execution complete:', pollResult)

          if (pollResult.state === 'completed') {
            logger.debug('Command completed successfully')
            logger.debug('Output:', pollResult.output)
            // Note: Backend already handles LLM interpretation and sends it to chat
            // The output will appear naturally through the WebSocket/streaming flow
          } else if (pollResult.state === 'failed') {
            logger.error('Command failed:', pollResult.stderr)
            notify('Command execution failed', 'error')
          } else if (pollResult.state === 'timeout') {
            logger.warn('Polling timed out')
            notify('Command execution timed out', 'warning')
          } else if (pollResult.state === 'error') {
            logger.error('Polling error:', pollResult.error)
            notify('Command polling error', 'error')
          }
        })
      } else if (!command_id && approved) {
        logger.warn('No command_id available for polling (legacy approval flow)')
      }

      // Permission v2: Store approval in project memory if requested
      if (
        rememberForProject.value &&
        approved &&
        currentProjectPath.value &&
        commandInfo &&
        permissionStore.isEnabled
      ) {
        const stored = await permissionStore.storeApproval(
          currentProjectPath.value,
          'web_user',
          commandInfo.command,
          commandInfo.risk_level,
          'Bash',
          comment
        )
        if (stored) {
          logger.info('Approval stored in project memory')
          notify('Approval remembered for this project', 'info')
        }
      }

      // Reset checkboxes after submission
      autoApproveFuture.value = false
      rememberForProject.value = false
    } else if (result.status === 'error') {
      logger.error('Approval error:', result.error)
      notify(`Approval failed: ${result.error}`, 'error')
    }

    processingApproval.value = false
  } catch (error) {
    logger.error('Error sending approval:', error)
    notify('Failed to process command approval', 'error')
    processingApproval.value = false
  }
}

const getRiskClass = (riskLevel: string): string => {
  const riskClasses: Record<string, string> = {
    'LOW': 'text-green-600',
    'MODERATE': 'text-yellow-600',
    'HIGH': 'text-orange-600',
    'DANGEROUS': 'text-red-600'
  }
  return riskClasses[riskLevel] || 'text-gray-600'
}

// Comment functionality methods
const promptForComment = (sessionId: string) => {
  showCommentInput.value = true
  activeCommentSessionId.value = sessionId
  approvalComment.value = ''
  pendingApprovalDecision.value = null
}

const submitApprovalWithComment = async (sessionId: string, approved: boolean | null) => {
  if (!approvalComment.value.trim()) {
    logger.warn('Cannot submit approval with empty comment')
    return
  }

  // Determine approval decision
  const finalDecision = approved !== null ? approved : pendingApprovalDecision.value

  if (finalDecision === null) {
    logger.error('No approval decision provided')
    return
  }

  // Call existing approveCommand with comment
  await approveCommand(sessionId, finalDecision, approvalComment.value)

  // Reset state
  cancelComment()
}

const cancelComment = () => {
  showCommentInput.value = false
  activeCommentSessionId.value = null
  approvalComment.value = ''
  pendingApprovalDecision.value = null
}

const scrollToBottom = () => {
  if (store.settings.autoSave && messagesContainer.value) { // Using autoSave as proxy for auto-scroll
    // Scroll the parent container (UnifiedLoadingView handles scrolling now)
    const scrollableParent = messagesContainer.value.closest('.overflow-y-auto')
    if (scrollableParent) {
      scrollableParent.scrollTop = scrollableParent.scrollHeight
    }
  }
}

// Auto-scroll when new messages arrive
watch(() => store.currentMessages.length, () => {
  nextTick(scrollToBottom)
})

// Announce new messages to screen readers
watch(() => store.currentMessages, (newMessages, oldMessages) => {
  // Only announce if a new message was added
  if (newMessages.length > (oldMessages?.length || 0)) {
    const latestMessage = newMessages[newMessages.length - 1]
    if (latestMessage) {
      const sender = getSenderName(latestMessage.sender)
      const preview = latestMessage.content.substring(0, 100).replace(/<[^>]*>/g, '') // Strip HTML
      screenReaderStatus.value = `New message from ${sender}: ${preview}${preview.length < latestMessage.content.length ? '...' : ''}`

      // Clear announcement after 2 seconds to allow new announcements
      setTimeout(() => {
        screenReaderStatus.value = ''
      }, 2000)
    }
  }
}, { deep: true })

// Watch typing status to manage timing
watch(() => store.isTyping, (isTyping) => {
  if (isTyping) {
    typingStartTime.value = Date.now()
    // Estimate response time based on message complexity
    const lastMessage = store.currentMessages[store.currentMessages.length - 1]
    if (lastMessage) {
      const complexity = Math.min(lastMessage.content.length / 100, 10)
      estimatedResponseTime.value = Math.ceil(2 + complexity)
    } else {
      estimatedResponseTime.value = 5
    }
  } else {
    typingStartTime.value = null
    estimatedResponseTime.value = null
  }
})

// DISABLED: Watch for TOOL_CALL markers in assistant messages
// This caused duplicate approval dialogs for auto-approved SAFE commands
// Only use `requires_approval` metadata from backend for approval UI
// watch(() => store.currentMessages, (messages) => {
//   const lastMessage = messages[messages.length - 1]
//   if (lastMessage?.sender === 'assistant' && lastMessage.content) {
//     detectToolCalls(lastMessage)
//   }
// }, { deep: true })

// DISABLED: Watch for popup trigger - keeping inline approval in chat instead
// Approval UI stays in chat history showing the state (pending/approved/denied)
// watch(() => store.currentMessages, (messages) => {
//   const lastMessage = messages[messages.length - 1]
//   if (lastMessage?.metadata?.requires_approval) {
//     emit('tool-call-detected', { ... })
//   }
// }, { deep: true })

// Scroll to bottom on mount and initialize permission store
onMounted(async () => {
  nextTick(scrollToBottom)

  // Permission v2: Initialize permission store
  try {
    await permissionStore.initialize()
    logger.debug('Permission store initialized:', {
      enabled: permissionStore.isEnabled,
      mode: permissionStore.currentMode
    })
  } catch (error) {
    logger.warn('Failed to initialize permission store:', error)
  }
})
</script>

<style scoped>
.message-wrapper {
  @apply rounded-lg shadow-sm border transition-all duration-200 relative;
  max-width: 85%;
  padding: 6px 10px;
}

.message-wrapper:hover {
  @apply shadow-md;
}

/* USER MESSAGES - Right side, blue theme */
.message-wrapper.user-message {
  @apply bg-blue-600 text-white border-blue-700 ml-auto mr-0;
  border-radius: 18px 18px 4px 18px;
}

.message-wrapper.user-message .sender-name,
.message-wrapper.user-message .message-time {
  @apply text-blue-100;
}

.message-wrapper.user-message .message-content {
  @apply text-white;
}

/* ASSISTANT MESSAGES - Left side, gray theme */
.message-wrapper.assistant-message {
  @apply bg-gray-100 text-gray-900 border-gray-300 mr-auto ml-0;
  border-radius: 18px 18px 18px 4px;
}

.message-wrapper.assistant-message .sender-name {
  @apply text-gray-900;
}

.message-wrapper.assistant-message .message-time {
  @apply text-gray-600;
}

.message-wrapper.assistant-message .message-content {
  @apply text-gray-900;
}

/* SYSTEM MESSAGES - Centered, subtle */
.message-wrapper.system-message {
  @apply bg-gray-50 border-gray-200 mx-auto text-gray-700;
  max-width: 70%;
  border-radius: 12px;
}

/* ============================================
   MESSAGE TYPE STYLING
   Different visual styles for message types:
   - thought: Purple theme (AI reasoning)
   - planning: Indigo theme (task planning)
   - debug: Orange theme (debug output)
   - utility: Slate theme (tool/utility output)
   - sources: Teal theme (source references)
   ============================================ */

/* THOUGHT MESSAGES - Purple theme for AI reasoning */
.message-wrapper.type-thought {
  @apply bg-purple-50 border-purple-300 text-purple-900;
  border-left: 4px solid theme('colors.purple.500');
}

.message-wrapper.type-thought .message-avatar {
  @apply bg-purple-600;
}

.message-wrapper.type-thought .sender-name {
  @apply text-purple-800;
}

.message-wrapper.type-thought .message-time {
  @apply text-purple-600;
}

.message-wrapper.type-thought::before {
  content: '';
  @apply absolute top-2 right-2 w-2 h-2 rounded-full bg-purple-400;
}

/* PLANNING MESSAGES - Indigo theme for task planning */
.message-wrapper.type-planning {
  @apply bg-indigo-50 border-indigo-300 text-indigo-900;
  border-left: 4px solid theme('colors.indigo.500');
}

.message-wrapper.type-planning .message-avatar {
  @apply bg-indigo-600;
}

.message-wrapper.type-planning .sender-name {
  @apply text-indigo-800;
}

.message-wrapper.type-planning .message-time {
  @apply text-indigo-600;
}

/* DEBUG MESSAGES - Orange/Amber theme for debug output */
.message-wrapper.type-debug {
  @apply bg-amber-50 border-amber-300 text-amber-900;
  border-left: 4px solid theme('colors.amber.500');
}

.message-wrapper.type-debug .message-avatar {
  @apply bg-amber-600;
}

.message-wrapper.type-debug .sender-name {
  @apply text-amber-800;
}

.message-wrapper.type-debug .message-time {
  @apply text-amber-600;
}

.message-wrapper.type-debug .message-text {
  @apply font-mono text-xs;
}

/* UTILITY MESSAGES - Slate theme for tool/utility output */
.message-wrapper.type-utility {
  @apply bg-slate-100 border-slate-300 text-slate-800;
  border-left: 4px solid theme('colors.slate.500');
}

.message-wrapper.type-utility .message-avatar {
  @apply bg-slate-600;
}

.message-wrapper.type-utility .sender-name {
  @apply text-slate-700;
}

.message-wrapper.type-utility .message-time {
  @apply text-slate-500;
}

/* SOURCES MESSAGES - Teal theme for source references */
.message-wrapper.type-sources {
  @apply bg-teal-50 border-teal-300 text-teal-900;
  border-left: 4px solid theme('colors.teal.500');
}

.message-wrapper.type-sources .message-avatar {
  @apply bg-teal-600;
}

.message-wrapper.type-sources .sender-name {
  @apply text-teal-800;
}

.message-wrapper.type-sources .message-time {
  @apply text-teal-600;
}

/* JSON MESSAGES - Cyan theme for structured data */
.message-wrapper.type-json {
  @apply bg-cyan-50 border-cyan-300 text-cyan-900;
  border-left: 4px solid theme('colors.cyan.500');
}

.message-wrapper.type-json .message-avatar {
  @apply bg-cyan-600;
}

.message-wrapper.type-json .message-text {
  @apply font-mono text-xs;
}

/* TERMINAL OUTPUT MESSAGES - Dark theme for terminal output */
.message-wrapper.type-terminal_output {
  @apply bg-gray-900 border-gray-700 text-gray-100;
  border-left: 4px solid theme('colors.green.500');
}

.message-wrapper.type-terminal_output .message-avatar {
  @apply bg-green-600;
}

.message-wrapper.type-terminal_output .sender-name {
  @apply text-green-400;
}

.message-wrapper.type-terminal_output .message-time {
  @apply text-gray-400;
}

.message-wrapper.type-terminal_output .message-text {
  @apply font-mono text-sm leading-relaxed whitespace-pre-wrap;
  color: #d4d4d4;
}

.message-wrapper.type-terminal_output .message-content {
  @apply text-gray-100;
}

/* COMMAND APPROVAL REQUEST - Yellow/Warning theme */
.message-wrapper.type-command_approval_request {
  @apply bg-yellow-50 border-yellow-400 text-yellow-900;
  border-left: 4px solid theme('colors.yellow.500');
}

.message-wrapper.type-command_approval_request .message-avatar {
  @apply bg-yellow-600;
}

/* Message type indicator badge */
.message-wrapper[class*="type-"]::after {
  @apply absolute top-1 right-1 px-1.5 py-0.5 text-xs font-medium rounded-full opacity-75;
}

.message-wrapper.type-thought::after {
  content: 'Thought';
  @apply bg-purple-200 text-purple-800;
}

.message-wrapper.type-planning::after {
  content: 'Planning';
  @apply bg-indigo-200 text-indigo-800;
}

.message-wrapper.type-debug::after {
  content: 'Debug';
  @apply bg-amber-200 text-amber-800;
}

.message-wrapper.type-utility::after {
  content: 'Utility';
  @apply bg-slate-200 text-slate-800;
}

.message-wrapper.type-sources::after {
  content: 'Sources';
  @apply bg-teal-200 text-teal-800;
}

.message-wrapper.type-terminal_output::after {
  content: 'Terminal';
  @apply bg-gray-700 text-green-400;
}

/* Issue #690: Overseer Agent Message Styles */
.message-wrapper.type-overseer_plan::after {
  content: 'Plan';
  @apply bg-indigo-700 text-indigo-100;
}

.message-wrapper.type-overseer_step::after {
  content: 'Step';
  @apply bg-purple-700 text-purple-100;
}

.message-wrapper.type-overseer_plan,
.message-wrapper.type-overseer_step {
  @apply bg-gray-800/50 border-indigo-600/50;
}

.message-wrapper.error {
  @apply bg-red-50 border-red-300 text-red-900;
}

.message-wrapper.sending {
  @apply opacity-70;
}

.message-header {
  @apply flex items-start justify-between mb-1;
}

.message-avatar {
  @apply w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-semibold;
}

.message-avatar.user {
  @apply bg-blue-700;
}

.message-avatar.assistant {
  @apply bg-gray-600;
}

.message-avatar.system {
  @apply bg-gray-500;
}

.message-info {
  @apply flex flex-col ml-1.5;
}

.sender-name {
  @apply font-semibold text-xs;
}

.model-name {
  @apply font-normal text-xs opacity-80 ml-1;
}

.message-time {
  @apply text-xs leading-tight;
}

.message-actions {
  @apply flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity;
}

/* Button styling handled by BaseButton component */

.message-status {
  @apply flex items-center gap-1.5 mb-1.5 text-xs;
}

.message-content {
  @apply leading-snug text-sm;
}

.message-text {
  @apply break-words;
  line-height: 1.4;
}

/* User message code styling - lighter for blue background */
.user-message .message-text :deep(code) {
  @apply bg-blue-500 text-blue-50 px-1.5 py-0.5 rounded text-xs font-mono;
}

.user-message .message-text :deep(pre) {
  @apply bg-blue-800 text-blue-50 p-3 rounded-lg overflow-x-auto my-1.5;
}

.user-message .message-text :deep(a) {
  @apply text-blue-100 hover:text-white underline;
}

/* Assistant message code styling - standard colors for light background */
.assistant-message .message-text :deep(code) {
  @apply bg-gray-200 text-gray-800 px-1.5 py-0.5 rounded text-xs font-mono;
}

.assistant-message .message-text :deep(pre) {
  @apply bg-gray-800 text-gray-100 p-3 rounded-lg overflow-x-auto my-1.5;
}

.assistant-message .message-text :deep(a) {
  @apply text-blue-600 hover:text-blue-800 underline;
}

/* User message metadata - lighter border for blue background */
.user-message .message-metadata {
  @apply mt-1.5 pt-1 border-t border-blue-400;
}

.user-message .metadata-items {
  @apply flex flex-wrap gap-1.5 text-xs text-blue-100;
}

/* Assistant message metadata - standard styling */
.assistant-message .message-metadata {
  @apply mt-1.5 pt-1 border-t border-gray-300;
}

.assistant-message .metadata-items {
  @apply flex flex-wrap gap-1.5 text-xs text-gray-600;
}

.metadata-item {
  @apply flex items-center gap-1;
}

.message-attachments {
  @apply mt-2 pt-1.5 border-t border-gray-200;
}

.attachment-header {
  @apply flex items-center gap-1.5 text-xs text-gray-600 mb-1.5;
}

.attachment-list {
  @apply space-y-1;
}

.attachment-item {
  @apply flex items-center gap-1.5 p-1.5 bg-gray-50 rounded cursor-pointer hover:bg-gray-100 transition-colors;
}

.attachment-name {
  @apply flex-1 text-xs text-gray-700 truncate;
}

.attachment-size {
  @apply text-xs text-gray-500;
}

.typing-indicator {
  @apply flex items-center gap-1.5;
}

.typing-indicator.large {
  @apply py-3;
}

.typing-dots {
  @apply flex gap-1;
}

.typing-dots span {
  @apply w-1.5 h-1.5 bg-gray-400 rounded-full animate-pulse;
  animation-delay: calc(var(--index) * 0.2s);
}

.typing-dots span:nth-child(1) { --index: 0; }
.typing-dots span:nth-child(2) { --index: 1; }
.typing-dots span:nth-child(3) { --index: 2; }

.typing-text {
  @apply text-xs text-gray-500;
}

.streaming-content {
  @apply space-y-1.5;
}

/* Enhanced Typing Indicator */
.typing-message {
  @apply animate-pulse;
}

.enhanced-typing-indicator {
  @apply flex flex-col gap-2 p-3;
}

.typing-animation {
  @apply relative;
}

.typing-dots-enhanced {
  @apply flex gap-1.5;
}

.typing-dots-enhanced span {
  @apply w-2.5 h-2.5 bg-blue-500 rounded-full;
  animation: typingBounce 1.4s ease-in-out infinite both;
}

.typing-dots-enhanced span:nth-child(1) { animation-delay: -0.32s; }
.typing-dots-enhanced span:nth-child(2) { animation-delay: -0.16s; }
.typing-dots-enhanced span:nth-child(3) { animation-delay: 0s; }
.typing-dots-enhanced span:nth-child(4) { animation-delay: 0.16s; }

@keyframes typingBounce {
  0%, 80%, 100% {
    transform: scale(0.8);
    opacity: 0.5;
  }
  40% {
    transform: scale(1.2);
    opacity: 1;
  }
}

.typing-wave {
  @apply absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-transparent via-blue-400 to-transparent rounded-full;
  animation: typingWave 2s ease-in-out infinite;
}

@keyframes typingWave {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

.typing-status {
  @apply flex justify-between items-center text-xs;
}

.typing-eta {
  @apply text-blue-600 font-medium;
}

/* Message Status Container */
.message-status-container {
  @apply mt-1.5 flex justify-end;
}

/* Message Skeleton */
.message-skeleton {
  @apply mt-3;
}

/* Scrollbar styling */
.overflow-y-auto::-webkit-scrollbar {
  width: 6px;
}

.overflow-y-auto::-webkit-scrollbar-track {
  background: #f8fafc;
}

.overflow-y-auto::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 3px;
}

.overflow-y-auto::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}

/* Animation for new messages */
@keyframes slideInFromBottom {
  from {
    opacity: 0;
    transform: translateY(15px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.message-wrapper {
  animation: slideInFromBottom 0.25s ease-out;
}

/* Approval Request Styles */
.approval-request {
  @apply mt-3 p-4 bg-yellow-50 border-2 border-yellow-300 rounded-lg;
}

/* Pre-approved State - Blue theme (auto-approved by security policy) */
.approval-confirmed.approval-pre-approved {
  @apply mt-3 p-4 bg-blue-50 border-2 border-blue-300 rounded-lg;
}

.approval-confirmed.approval-pre-approved .approval-header {
  @apply flex items-center gap-2 mb-3 text-blue-900 font-semibold;
}

/* User Approved State - Green theme (manually approved by user) */
.approval-confirmed.approval-approved {
  @apply mt-3 p-4 bg-green-50 border-2 border-green-300 rounded-lg;
}

.approval-confirmed.approval-approved .approval-header {
  @apply flex items-center gap-2 mb-3 text-green-900 font-semibold;
}

/* Denied State - Red theme (manually denied by user) */
.approval-confirmed.approval-denied {
  @apply mt-3 p-4 bg-red-50 border-2 border-red-300 rounded-lg;
}

.approval-confirmed.approval-denied .approval-header {
  @apply flex items-center gap-2 mb-3 text-red-900 font-semibold;
}

.approval-header {
  @apply flex items-center gap-2 mb-3 text-yellow-900 font-semibold;
}

.approval-details {
  @apply space-y-2 mb-3;
}

.approval-detail-item {
  @apply flex items-start gap-2 text-sm;
}

.detail-label {
  @apply font-medium text-gray-700 min-w-24;
}

.detail-value {
  @apply flex-1 text-gray-900;
}

.detail-value code {
  @apply bg-gray-200 px-2 py-1 rounded text-xs font-mono;
}

/* Interactive Command Warning Styles (Issue #33) */
.interactive-warning {
  @apply flex-col bg-blue-50 p-3 rounded-lg border border-blue-200 mt-2;
}

.interactive-header {
  @apply flex items-center gap-2 mb-2;
}

.interactive-info {
  @apply ml-6;
}

.interactive-reasons {
  @apply mt-2 p-2 bg-white rounded border border-blue-100;
}

.approval-actions {
  @apply flex gap-2;
}

/* Button styling handled by BaseButton component */

.approval-processing {
  @apply flex items-center gap-2 mt-2 text-sm text-gray-600;
}

/* Responsive adjustments */
@media (max-width: 768px) {
  .message-wrapper.user-message {
    @apply ml-1 mr-0.5;
  }

  .message-wrapper.assistant-message {
    @apply mr-1 ml-0.5;
  }

  .message-wrapper.system-message {
    @apply mx-0.5;
  }

  .message-avatar {
    @apply w-5 h-5 text-xs;
  }

  .sender-name {
    @apply text-xs;
  }

  .message-time {
    @apply text-xs;
  }

  /* Responsive button styling handled by BaseButton component */

  .approval-actions {
    @apply flex-col;
  }
}

/* Comment Input Section Styles */
.comment-input-section {
  @apply mt-3 mb-3 p-3 bg-white border border-gray-300 rounded-lg;
}

.comment-textarea {
  @apply w-full px-3 py-2 border border-gray-300 rounded-md resize-none focus:outline-none focus:ring-2 focus:ring-blue-500;
}

.comment-actions {
  @apply flex gap-2 mt-2;
}

/* Button styling handled by BaseButton component */

/* Auto-approve checkbox section */
.auto-approve-section {
  @apply mt-3 mb-3 p-3 bg-blue-50 border border-blue-200 rounded-lg;
}

.auto-approve-checkbox {
  @apply flex items-center gap-2 cursor-pointer;
}

.checkbox-input {
  @apply w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-2 focus:ring-blue-500 cursor-pointer;
}

.checkbox-label {
  @apply flex items-center gap-2 text-sm font-medium text-gray-700 cursor-pointer select-none;
}

.checkbox-label i {
  @apply text-blue-600;
}

.auto-approve-hint {
  @apply mt-2 pl-6 flex items-start gap-2 text-xs text-blue-700;
}

.auto-approve-hint i {
  @apply mt-0.5;
}

/* Permission v2: Remember for project checkbox section */
.remember-project-section {
  @apply mt-3 mb-3 p-3 bg-green-50 border border-green-200 rounded-lg;
}

.remember-project-checkbox {
  @apply flex items-center gap-2 cursor-pointer;
}

.remember-project-checkbox .checkbox-label i {
  @apply text-green-600;
}

.remember-project-hint {
  @apply mt-2 pl-6 flex items-start gap-2 text-xs text-green-700;
}

.remember-project-hint i {
  @apply mt-0.5;
}

/* Issue #249: Knowledge Citations Styles */
.knowledge-citations {
  @apply mt-3 border border-indigo-200 rounded-lg overflow-hidden bg-indigo-50;
}

.citations-header {
  @apply flex items-center justify-between px-3 py-2 cursor-pointer transition-colors;
}

.citations-header:hover {
  @apply bg-indigo-100;
}

.citations-header-left {
  @apply flex items-center gap-2;
}

.citations-label {
  @apply text-sm font-medium text-indigo-700;
}

.citations-count {
  @apply px-1.5 py-0.5 text-xs font-semibold bg-indigo-600 text-white rounded-full;
}

.citations-list {
  @apply border-t border-indigo-200 bg-white;
}

.citation-item {
  @apply flex gap-2 px-3 py-2 border-b border-indigo-100 last:border-b-0;
}

.citation-rank {
  @apply text-sm font-mono font-semibold text-indigo-600 flex-shrink-0;
}

.citation-content {
  @apply flex-1 min-w-0;
}

.citation-text {
  @apply text-sm text-gray-700 leading-snug mb-1;
}

.citation-meta {
  @apply flex flex-wrap gap-3 text-xs text-gray-500;
}

.citation-score {
  @apply flex items-center gap-1 font-medium;
}

.citation-score.score-excellent {
  @apply text-green-600;
}

.citation-score.score-good {
  @apply text-blue-600;
}

.citation-score.score-acceptable {
  @apply text-yellow-600;
}

.citation-score.score-low {
  @apply text-gray-500;
}

.citation-source {
  @apply flex items-center gap-1 text-gray-500;
}

/* Citation slide transition */
.slide-fade-enter-active {
  transition: all 0.2s ease-out;
}

.slide-fade-leave-active {
  transition: all 0.15s ease-in;
}

.slide-fade-enter-from,
.slide-fade-leave-to {
  opacity: 0;
  max-height: 0;
  transform: translateY(-10px);
}

.slide-fade-enter-to,
.slide-fade-leave-from {
  opacity: 1;
  max-height: 500px;
  transform: translateY(0);
}
</style>
