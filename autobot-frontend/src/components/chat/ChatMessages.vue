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
      icon="comments"
      :title="$t('chat.interface.startConversation')"
      :message="$t('chat.emptyState')"
    />

    <div
      v-else
      role="log"
      aria-live="polite"
      aria-atomic="false"
      aria-relevant="additions"
      :aria-label="$t('chat.messages.conversation')"
    >
      <!-- Issue #1314: Virtual scroll spacer — sets total scrollable height -->
      <div
        :style="{
          height: `${totalSize}px`,
          width: '100%',
          position: 'relative',
        }"
      >
        <div
          v-for="vItem in virtualItems"
          :key="String(vItem.key)"
          :data-index="vItem.index"
          :ref="(el: any) => el && measureElement(el as Element)"
          :style="{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            transform: `translateY(${vItem.start}px)`,
            paddingBottom: '4px',
          }"
        >
        <!-- Issue #1314: Local alias via single-element v-for -->
        <template v-for="message in [filteredMessages[vItem.index]]" :key="message?.id ?? vItem.index">
        <div
          class="message-wrapper"
          :class="getMessageWrapperClass(message)"
        >
        <!-- Message Header -->
        <div class="message-header">
          <div class="flex items-center gap-1.5">
            <div class="message-avatar" :class="getAvatarClass(message.sender)">
              <i :class="getSenderIcon(message.sender, (message.type || (message.metadata?.display_type as string)) || undefined)" aria-hidden="true"></i>
            </div>
            <div class="message-info">
              <span class="sender-name">
                {{ getSenderName(message.sender) }}
                <span v-if="message.sender === 'assistant' && message.metadata?.model" class="model-name">
                  ({{ message.metadata.model }})
                </span>
              </span>
              <!-- MVA-1993: Lightweight mode cost indicator -->
              <span
                v-if="message.sender === 'assistant' && message.metadata?.lightweight_mode_used"
                class="message-type-badge badge-info"
                :title="$t('chat.lightweightModeTooltip', { default: '~90% cheaper than standard mode' })"
              >
                <i class="fas fa-bolt mr-1"></i>
                {{ $t('chat.lightweightMode', { default: 'Lightweight' }) }}
              </span>
              <!-- Issue #1310: Visible type badge for typed messages -->
              <span
                v-if="getMessageTypeBadge(message)"
                class="message-type-badge"
                :class="`badge-${getMessageTypeBadge(message)!.type}`"
              >
                <i :class="getMessageTypeBadge(message)!.icon" class="mr-1"></i>
                {{ getMessageTypeBadge(message)!.label }}
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
              :aria-label="$t('chat.editMessage')"
              :title="$t('chat.editMessage')"
            >
              <Icon name="edit" />
            </BaseButton>
            <BaseButton
              variant="ghost"
              size="xs"
              @click="copyMessage(message)"
              class="action-btn"
              :aria-label="$t('chat.copyMessage')"
              :title="$t('chat.copyMessage')"
            >
              <Icon name="copy" />
            </BaseButton>
            <BaseButton
              variant="ghost"
              size="xs"
              @click="deleteMessage(message)"
              class="action-btn danger"
              :aria-label="$t('chat.deleteMessage')"
              :title="$t('chat.deleteMessage')"
            >
              <Icon name="trash" />
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
          :plan="message.metadata.plan as any"
          :steps="message.metadata?.steps as any"
        />

        <!-- Issue #690: Overseer Agent Step Message -->
        <OverseerStepMessage
          v-else-if="message.type === 'overseer_step' && message.metadata?.step"
          :step="message.metadata.step as any"
        />

        <!-- GH#9015: AI-generated image message -->
        <ImageCell
          v-else-if="(message.type === 'image' || message.metadata?.display_type === 'image') && message.metadata?.image_payload"
          :rich-payload="(message.metadata.image_payload as Record<string, unknown>)"
        />

        <!-- GH#9016: AI-generated video message -->
        <VideoCell
          v-else-if="(message.type === 'video' || message.metadata?.display_type === 'video') && message.metadata?.video_payload"
          :rich-payload="(message.metadata.video_payload as Record<string, unknown>)"
        />

        <!-- MVA-2006: Context summary message -->
        <div
          v-else-if="message.type === 'summary' || message.metadata?.is_summary"
          class="message-content summary-message"
        >
          <div class="summary-header">
            <span class="summary-icon">📝</span>
            <span class="summary-title">{{ $t('chat.contextWindow.summaryTitle') }}</span>
          </div>
          <details class="summary-details">
            <summary class="summary-toggle">
              {{ $t('chat.contextWindow.summaryToggle') }}
            </summary>
            <div class="summary-content message-text" v-html="formatMessageContent(message.content, message.id)"></div>
          </details>
        </div>

        <!-- Message Content -->
        <div v-else class="message-content" :class="getContentClass(message)">
          <!-- Streaming content with typing indicator -->
          <div v-if="isStreamingMessage(message)" class="streaming-content">
            <div class="message-text" v-html="formatMessageContent(message.content, message.id)"></div>
            <div v-if="store.isTyping && isLastMessage(message)" class="typing-indicator">
              <div class="typing-dots">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>

          <!-- Regular message content -->
          <div v-else class="message-text" v-html="formatMessageContent(message.content, message.id)"></div>

          <!-- Message Metadata -->
          <div v-if="message.metadata && shouldShowMetadata(message)" class="message-metadata">
            <div class="metadata-items">
              <!-- GH#8993: Thinking used indicator -->
              <span v-if="message.sender === 'assistant' && message.metadata.thinking_used" class="metadata-item thinking-used-badge">
                🧠 {{ $t('chat.messages.thinkingUsed', 'Extended thinking') }}
              </span>
              <span v-if="message.metadata.model" class="metadata-item">
                <Icon name="robot" />
                {{ message.metadata.model }}
              </span>
              <span v-if="message.metadata.tokens" class="metadata-item">
                <Icon name="dollar-sign" />
                {{ $t('chat.messages.tokens', { count: message.metadata.tokens }) }}
              </span>
              <span v-if="message.metadata.duration" class="metadata-item">
                <Icon name="clock" />
                {{ message.metadata.duration }}ms
              </span>
            </div>
          </div>

          <!-- Issue #249, #1186, #4448: Source Attribution Display
               Prefer top-level message.sources (persisted via Issue #4448) when
               present; fall back to metadata.citations for live-streaming chunks
               where sources have not been persisted yet.  Only knowledge_base
               entries are included in message.sources so no llm_training
               sentinel is appended here. -->
          <CitationsDisplay
            v-if="message.sender === 'assistant' && getMessageCitations(message).length > 0"
            :citations="getMessageCitations(message)"
          />

          <!-- Attachments -->
          <div v-if="message.attachments && message.attachments.length > 0" class="message-attachments">
            <div class="attachment-header">
              <Icon name="paperclip" />
              <span>{{ $t('chat.messages.attachments', { count: message.attachments.length }, message.attachments.length) }}</span>
            </div>
            <div class="attachment-list">
              <div
                v-for="attachment in message.attachments"
                :key="attachment.id"
                class="attachment-item"
                @click="viewAttachment(attachment)"
              >
                <Icon :name="getAttachmentIcon(attachment.type)" />
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
              <Icon name="shield-check" class="text-blue-600" />
              <span class="font-semibold">{{ $t('chat.approval.autoApproved') }}</span>
            </div>
            <div class="approval-details">
              <div class="approval-detail-item">
                <span class="detail-label">{{ $t('chat.approval.command') }}:</span>
                <code class="detail-value">{{ message.metadata.command }}</code>
              </div>
              <div v-if="message.metadata.approval_comment" class="approval-detail-item">
                <span class="detail-label">{{ $t('chat.approval.reason') }}:</span>
                <span class="detail-value">{{ message.metadata.approval_comment }}</span>
              </div>
            </div>
          </div>

          <!-- USER APPROVED STATE - Show green confirmation -->
          <div v-else-if="message.metadata?.approval_status === 'approved'" class="approval-confirmed approval-approved">
            <div class="approval-header">
              <Icon name="check-circle" class="text-green-600" />
              <span class="font-semibold">{{ $t('chat.approval.commandApproved') }}</span>
            </div>
            <div class="approval-details">
              <div class="approval-detail-item">
                <span class="detail-label">{{ $t('chat.approval.command') }}:</span>
                <code class="detail-value">{{ message.metadata.command }}</code>
              </div>
              <div v-if="message.metadata.approval_comment" class="approval-detail-item">
                <span class="detail-label">{{ $t('chat.approval.comment') }}:</span>
                <span class="detail-value">{{ message.metadata.approval_comment }}</span>
              </div>
            </div>
          </div>

          <!-- DENIED STATE - Show red rejection -->
          <div v-else-if="message.metadata?.approval_status === 'denied'" class="approval-confirmed approval-denied">
            <div class="approval-header">
              <Icon name="times-circle" class="text-red-600" />
              <span class="font-semibold">{{ $t('chat.approval.commandDenied') }}</span>
            </div>
            <div class="approval-details">
              <div class="approval-detail-item">
                <span class="detail-label">{{ $t('chat.approval.command') }}:</span>
                <code class="detail-value">{{ message.metadata.command }}</code>
              </div>
              <div v-if="message.metadata.approval_comment" class="approval-detail-item">
                <span class="detail-label">{{ $t('chat.approval.reason') }}:</span>
                <span class="detail-value">{{ message.metadata.approval_comment }}</span>
              </div>
            </div>
          </div>

          <!-- PENDING APPROVAL STATE - Show approval buttons -->
          <!-- FIXED: Only show if requires_approval AND no approval_status yet -->
          <div v-else-if="message.metadata?.requires_approval && !message.metadata?.approval_status" class="approval-request">
            <div class="approval-header">
              <Icon name="exclamation-triangle" class="text-yellow-600" />
              <span class="font-semibold">{{ $t('chat.approval.approvalRequired') }}</span>
            </div>
            <div class="approval-details">
              <div class="approval-detail-item">
                <span class="detail-label">{{ $t('chat.approval.command') }}:</span>
                <code class="detail-value">{{ message.metadata.command }}</code>
              </div>
              <div class="approval-detail-item">
                <span class="detail-label">{{ $t('chat.approval.riskLevel') }}:</span>
                <span class="detail-value" :class="getRiskClass((message.metadata as any).risk_level)">
                  {{ (message.metadata as any).risk_level }}
                </span>
              </div>
              <div v-if="(message.metadata as any).purpose" class="approval-detail-item">
                <span class="detail-label">{{ $t('chat.approval.purpose') }}:</span>
                <span class="detail-value">{{ (message.metadata as any).purpose }}</span>
              </div>
              <div v-if="(message.metadata as any).reasons && (message.metadata as any).reasons.length > 0" class="approval-detail-item">
                <span class="detail-label">{{ $t('chat.approval.reasons') }}:</span>
                <span class="detail-value">{{ (message.metadata as any).reasons.join(', ') }}</span>
              </div>

              <!-- Interactive Command Warning (Issue #33) -->
              <div v-if="(message.metadata as any).is_interactive" class="approval-detail-item interactive-warning">
                <div class="interactive-header">
                  <Icon name="keyboard" class="text-blue-600" />
                  <span class="detail-label font-semibold text-blue-700">{{ $t('chat.approval.interactiveCommand') }}</span>
                </div>
                <div class="interactive-info">
                  <p class="text-sm text-autobot-text-secondary mb-2">
                    {{ $t('chat.approval.interactiveInfo') }}
                  </p>
                  <div v-if="(message.metadata as any).interactive_reasons && (message.metadata as any).interactive_reasons.length > 0" class="interactive-reasons">
                    <span class="text-xs font-medium text-autobot-text-secondary">{{ $t('chat.approval.inputRequired') }}:</span>
                    <ul class="text-xs text-autobot-text-secondary mt-1 ml-4 list-disc">
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
                :placeholder="$t('chat.approval.commentPlaceholder')"
                rows="2"
                @keydown.ctrl.enter="submitApprovalWithComment(message.metadata.terminal_session_id as string, pendingApprovalDecision)"
                @keydown.meta.enter="submitApprovalWithComment(message.metadata.terminal_session_id as string, pendingApprovalDecision)"
              ></textarea>
              <div class="comment-actions">
                <BaseButton
                  variant="secondary"
                  size="sm"
                  @click="cancelComment"
                  class="cancel-comment-btn"
                  :aria-label="$t('chat.approval.cancelComment')"
                >
                  <Icon name="times" />
                  <span>{{ $t('common.cancel') }}</span>
                </BaseButton>
                <BaseButton
                  variant="primary"
                  size="sm"
                  @click="submitApprovalWithComment(message.metadata.terminal_session_id as string, pendingApprovalDecision)"
                  :disabled="!approvalComment.trim()"
                  class="submit-comment-btn"
                  :aria-label="$t('chat.approval.submitWithComment', { action: pendingApprovalDecision ? $t('chat.approval.approval') : $t('chat.approval.denial') })"
                >
                  <Icon name="check" />
                  <span>{{ $t('chat.approval.submit') }} {{ pendingApprovalDecision ? $t('chat.approval.approval') : $t('chat.approval.denial') }}</span>
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
                  <Icon name="shield-check" />
                  {{ $t('chat.approval.autoApproveFuture') }}
                </span>
              </label>
              <div v-if="autoApproveFuture" class="auto-approve-hint">
                <Icon name="info-circle" />
                <span>{{ $t('chat.approval.autoApproveHint') }}</span>
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
                  <Icon name="folder-open" />
                  {{ $t('chat.approval.rememberProject') }}
                </span>
              </label>
              <div v-if="rememberForProject" class="remember-project-hint">
                <Icon name="info-circle" />
                <span>{{ $t('chat.approval.rememberProjectHint', { path: currentProjectPath || $t('chat.approval.noProjectContext') }) }}</span>
              </div>
            </div>

            <div class="approval-actions">
              <BaseButton
                variant="success"
                size="sm"
                @click="approveCommand((message.metadata as any).terminal_session_id as string, true, undefined, (message.metadata as any).command_id, { command: (message.metadata as any).command as string, risk_level: (message.metadata as any).risk_level as string })"
                :disabled="processingApproval || showCommentInput"
                class="approve-btn"
                :aria-label="$t('chat.approval.approveCommand')"
              >
                <Icon name="check" />
                <span>{{ $t('chat.approval.approve') }}</span>
              </BaseButton>
              <BaseButton
                variant="outline-solid"
                size="sm"
                @click="promptForComment((message.metadata as any).terminal_session_id as string)"
                :disabled="processingApproval || showCommentInput"
                class="comment-btn"
                :aria-label="$t('chat.approval.addComment')"
              >
                <Icon name="comment" />
                <span>{{ $t('chat.approval.comment') }}</span>
              </BaseButton>
              <BaseButton
                variant="error"
                size="sm"
                @click="approveCommand((message.metadata as any).terminal_session_id as string, false, undefined, (message.metadata as any).command_id, { command: (message.metadata as any).command as string, risk_level: (message.metadata as any).risk_level as string })"
                :disabled="processingApproval || showCommentInput"
                class="deny-btn"
                :aria-label="$t('chat.approval.denyCommand')"
              >
                <Icon name="times" />
                <span>{{ $t('chat.approval.deny') }}</span>
              </BaseButton>
            </div>
            <div v-if="processingApproval" class="approval-processing">
              <LoadingSpinner size="sm" />
              <span>{{ $t('chat.approval.processing') }}</span>
            </div>
          </div>
        </div>
      </div>
      </template>
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
              <span class="sender-name">{{ $t('chat.messages.aiAssistant') }}</span>
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

  <!-- Edit Message Modal -->
  <BaseModal
    v-model="showEditModal"
    :title="$t('chat.messages.editMessage')"
    size="md"
  >
    <textarea
      v-model="editingContent"
      class="flex-1 w-full px-3 py-2 border border-autobot-border rounded-md focus:outline-none focus:ring-2 focus:ring-electric-500 resize-none"
      :placeholder="$t('chat.messages.enterMessage')"
      @keydown.ctrl.enter="saveEditedMessage"
      @keydown.meta.enter="saveEditedMessage"
      ref="editTextarea"
      rows="6"
    ></textarea>
    <div class="text-xs text-autobot-text-muted mt-2">
      {{ $t('chat.messages.ctrlEnterToSave') }}
    </div>

    <template #actions>
      <BaseButton
        variant="secondary"
        @click="cancelEdit"
      >
        {{ $t('common.cancel') }}
      </BaseButton>
      <BaseButton
        variant="primary"
        @click="saveEditedMessage"
        :disabled="!editingContent.trim()"
      >
        {{ $t('common.save') }}
      </BaseButton>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import type { IconName } from '@/components/ui/Icon.vue'
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, nextTick, watch, onMounted } from 'vue'
import { useExpansion } from '@/composables/useExpansion'
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/stores/useChatStore'
import { useChatController } from '@/models/controllers'
import { useDisplaySettings } from '@/composables/useDisplaySettings'
import { usePermissionStore } from '@/stores/usePermissionStore'
import { useVirtualChatScroll } from '@/composables/useVirtualChatScroll'
import type { ChatMessage } from '@/stores/useChatStore'
import MessageStatus from '@/components/ui/MessageStatus.vue'
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue'
import SkeletonLoader from '@/components/ui/SkeletonLoader.vue'
import StableLoadingState from '@/components/ui/StableLoadingState.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import OverseerPlanMessage from '@/components/chat/OverseerPlanMessage.vue'
import OverseerStepMessage from '@/components/chat/OverseerStepMessage.vue'
import CitationsDisplay from '@/components/chat/CitationsDisplay.vue'
import ImageCell from '@/components/artifact-cells/ImageCell.vue'
import VideoCell from '@/components/artifact-cells/VideoCell.vue'
import { formatFileSize, formatTime } from '@/utils/formatHelpers'
import { createLogger } from '@/utils/debugUtils'
import { useCommandApproval } from '@/composables/useCommandApproval'
import { sanitizeChatHtml } from '@/utils/sanitize'

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

const { t } = useI18n()
const store = useChatStore()
const controller = useChatController()
const { displaySettings } = useDisplaySettings()
const permissionStore = usePermissionStore()

// Command Approval composable — replaces all inline fetchWithAuth calls
const {
  processingApproval,
  showCommentInput,
  activeCommentSessionId,
  approvalComment,
  pendingApprovalDecision,
  autoApproveFuture,
  rememberForProject,
  currentProjectPath,
  approveCommand: _approveCommand,
  promptForComment,
  submitApprovalWithComment,
  cancelComment,
  getRiskClass,
} = useCommandApproval()

/**
 * Thin wrapper: calls the composable's approveCommand with the store's
 * message-update callback wired in.
 */
const approveCommand = (
  terminal_session_id: string,
  approved: boolean,
  comment?: string,
  command_id?: string,
  commandInfo?: { command: string; risk_level: string }
) => {
  const onMessageUpdate = (sessionId: string, status: string, updateComment?: string) => {
    const targetMessage = store.currentMessages.find(
      msg => msg.metadata?.terminal_session_id === sessionId &&
             msg.metadata?.requires_approval === true
    )
    if (targetMessage && targetMessage.metadata) {
      targetMessage.metadata.approval_status = status
      targetMessage.metadata.approval_comment = updateComment
    } else {
      logger.warn('Could not find message to update approval status')
    }
  }
  return _approveCommand(terminal_session_id, approved, comment, command_id, onMessageUpdate, commandInfo)
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
const citationExpansion = useExpansion<string>()
const expandedCitations = citationExpansion.expanded

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

    // Show Metadata - controls json/metadata responses (mapMessageType → 'json')
    if (displayType === 'json' && !displaySettings.value.showJson) return false

    // Always show regular messages and responses
    return true
  })
})

// Issue #1314: Virtual scrolling composable
const {
  virtualItems,
  totalSize,
  measureElement,
  scrollToBottom,
  isStuckToBottom,
} = useVirtualChatScroll({
  messagesContainerRef: messagesContainer,
  filteredMessages,
  isTyping: computed(() => store.isTyping),
  currentSessionId: computed(() => store.currentSessionId),
})

const typingStatusText = computed(() => {
  const elapsed = typingStartTime.value ? Date.now() - typingStartTime.value : 0
  if (elapsed < 2000) return t('chat.messages.thinking')
  if (elapsed < 5000) return t('chat.messages.processingStatus')
  if (elapsed < 10000) return t('chat.messages.analyzing')
  return t('chat.messages.workingOnIt')
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
    t('chat.messages.understandingRequest'),
    t('chat.messages.searchingKnowledge'),
    t('chat.messages.formulatingResponse'),
    t('chat.messages.craftingAnswer'),
    t('chat.messages.reviewingQuality')
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
  const messageType = message.type || (message.metadata as any)?.display_type
  const noTypeClassTypes = ['response', 'message', 'default', 'llm_response', 'llm_response_chunk']
  if (messageType && !noTypeClassTypes.includes(String(messageType))) {
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
      thought: 'brain',
      planning: 'list-check',
      debug: 'bug',
      utility: 'wrench',
      sources: 'book-open',
      command_approval_request: 'shield-alt',
      terminal_output: 'terminal',
      terminal_command: 'terminal',
      overseer_plan: 'sitemap',
      overseer_step: 'tasks',
      llm_response: 'robot',
      llm_response_chunk: 'robot'
    }
    if (typeIcons[messageType]) return typeIcons[messageType]
  }

  const icons: Record<string, string> = {
    user: 'user',
    assistant: 'robot',
    system: 'cog',
    error: 'exclamation-triangle',
    thought: 'brain',
    'tool-code': 'code',
    'tool-output': 'terminal'
  }

  return icons[sender] || 'comment'
}

const getSenderName = (sender: string): string => {
  const names: Record<string, string> = {
    user: t('chat.messages.senderYou'),
    assistant: t('chat.messages.aiAssistant'),
    system: t('chat.messages.senderSystem'),
    error: t('common.error'),
    thought: t('chat.messages.senderThought'),
    'tool-code': t('chat.messages.senderCodeExecution'),
    'tool-output': t('chat.messages.senderOutput')
  }

  return names[sender] || sender
}

/** Issue #1310: Visible badge for typed messages so they're clearly distinguishable. */
const getMessageTypeBadge = (message: ChatMessage): { label: string; icon: string; type: string } | null => {
  const msgType = message.type || (message.metadata as any)?.display_type
  if (!msgType) return null

  const badges: Record<string, { label: string; icon: string; type: string }> = {
    thought:  { label: t('chat.messages.badgeThought'),  icon: 'brain',      type: 'thought' },
    planning: { label: t('chat.messages.badgePlanning'), icon: 'list-check',  type: 'planning' },
    debug:    { label: t('chat.messages.badgeDebug'),    icon: 'bug',         type: 'debug' },
    utility:  { label: t('chat.messages.badgeUtility'),  icon: 'wrench',      type: 'utility' },
    sources:  { label: t('chat.messages.badgeSources'),  icon: 'book-open',   type: 'sources' },
  }

  return badges[String(msgType)] || null
}

const getContentClass = (message: ChatMessage): string => {
  const classes = ['message-content']
  if (message.sender === 'user') classes.push('user-content')
  if (message.sender === 'assistant') classes.push('assistant-content')
  if (message.sender === 'system') classes.push('system-content')

  return classes.join(' ')
}

// NOTE: formatTime removed - now using shared utility from @/utils/formatHelpers

/**
 * Issue #1312: Memoized format cache.
 * Key: message id + content length (cheap proxy for content identity).
 * Avoids re-running 11 regex ops for unchanged messages on every render.
 */
const formatCache = new Map<string, string>()
const FORMAT_CACHE_MAX = 500

const formatMessageContentRaw = (content: string): string => {
  // Strip ANSI escape codes FIRST (terminal color codes, cursor movements, etc.)
  let formatted = content
    .replace(/\u001b\[[0-9;]*[a-zA-Z]/g, '') // CSI sequences
    .replace(/\u001b\][0-9;]*[^\u0007]*\u0007/g, '') // OSC sequences: BEL
    .replace(/\u001b\][0-9;]*[^\u0007\u001b]*(?:\u001b\\)?/g, '') // OSC sequences: ST
    .replace(/\u001b[=>]/g, '') // Set numeric keypad mode
    .replace(/\u001b[()][AB012]/g, '') // Character set selection
    .replace(/\u001b\[[?\d;]*[hlHJ]/g, '') // Bracket sequences
    .replace(/\u001b\]0;[^\u0007\n]*\u0007?/g, '') // Set title
    .trim()

  // Strip message type tags (Issue #680)
  formatted = formatted
    .replace(/\[\/?(THOUGHT|PLANNING|DEBUG|SOURCES)\]?/gi, '')
    .replace(/\[\/?(?:THO(?:UGH?T?)?|PLA(?:NN?I?N?G?)?|DEB(?:UG?)?|SOU(?:RC?E?S?)?)\]?$/gi, '')
    .trim()

  // Strip TOOL_CALL tags
  formatted = formatted.replace(/<tool_call[^>]*>.*?<\/tool_call>/gs, '')

  // Process code blocks
  formatted = formatted.replace(/```(\w+)?\n([\s\S]*?)```/g, (_match, lang, code) => {
    return `<pre class="code-block${lang ? ` language-${lang}` : ''}"><code>${code.trim()}</code></pre>`
  })

  // Basic markdown formatting
  formatted = formatted
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')

  // Links
  formatted = formatted.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>')

  return sanitizeChatHtml(formatted)
}

const formatMessageContent = (content: string, messageId?: string): string => {
  const cacheKey = messageId ? `${messageId}:${content.length}` : content
  const cached = formatCache.get(cacheKey)
  if (cached !== undefined) return cached

  const result = formatMessageContentRaw(content)

  // Evict oldest entries when cache is full
  if (formatCache.size >= FORMAT_CACHE_MAX) {
    const firstKey = formatCache.keys().next().value
    if (firstKey !== undefined) formatCache.delete(firstKey)
  }
  formatCache.set(cacheKey, result)
  return result
}

const getStatusText = (status: string): string => {
  const statusMap: Record<string, string> = {
    sending: t('chat.messages.statusSending'),
    sent: t('chat.messages.statusSent'),
    error: t('chat.messages.statusFailed')
  }

  return statusMap[status] || status
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

/**
 * Issue #4448: Return the canonical citation list for a message.
 *
 * Priority order:
 * 1. message.sources — top-level persisted sources (knowledge_base entries only,
 *    shape: {title, path, score, chunk_id}).  Present after the message is saved
 *    and reloaded from the backend.
 * 2. metadata.citations — present during live streaming before persistence.
 *    May include the always-appended llm_training sentinel; filter it out so
 *    the user only sees real knowledge-base references.
 *
 * Returns a Citation-compatible array accepted by CitationsDisplay.
 */
const getMessageCitations = (message: ChatMessage): Record<string, unknown>[] => {
  if (Array.isArray(message.sources) && message.sources.length > 0) {
    return message.sources.map((s) => ({
      id: s.chunk_id,
      title: s.title,
      source: s.path,
      score: s.score,
      type: 'knowledge_base' as const,
      reliability: 'high' as const,
    }))
  }
  const metaCitations = (message.metadata as Record<string, unknown> | undefined)
    ?.citations
  if (Array.isArray(metaCitations)) {
    return (metaCitations as Record<string, unknown>[]).filter(
      (c) => c.type !== 'llm_training'
    )
  }
  return []
}

const hasCodeBlocks = (content: string): boolean => {
  return /```[\s\S]*?```/.test(content)
}

// Issue #249: Citation helper functions
const toggleCitations = (messageId: string) => {
  citationExpansion.toggle(messageId)
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
  if (confirm(t('chat.messages.confirmDelete'))) {
    controller.deleteMessage(message.id)
  }
}

const getAttachmentIcon = (type: string): IconName => {
  if (type.startsWith('image/')) return 'image'
  if (type.startsWith('video/')) return 'video'
  if (type.startsWith('audio/')) return 'music'
  if (type.includes('pdf')) return 'file-pdf'
  if (type.includes('word')) return 'file-word'
  if (type.includes('excel')) return 'file-excel'
  return 'file'
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
      let terminal_session_id: string | null = ((message.metadata as any)?.terminal_session_id as string) || null

      if (!terminal_session_id) {
        // Search backwards through recent assistant messages for terminal_session_id
        const recentAssistantMessages = store.currentMessages
          .filter(m => m.sender === 'assistant')
          .reverse()
          .slice(0, 10) // Check last 10 assistant messages

        for (const msg of recentAssistantMessages) {
          const metadataSessionId = (msg.metadata as any)?.terminal_session_id as string | null
          if (metadataSessionId) {
            terminal_session_id = metadataSessionId
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

// Issue #1312: Consolidated watcher — auto-scroll + screen reader announcement
// Replaces two separate watchers (one with deep: true that traversed all message
// properties on every streaming chunk). Now watches only array length (O(1)).
watch(() => store.currentMessages.length, (newLen, oldLen) => {
  // Auto-scroll on any length change (new message or streaming update)
  nextTick(scrollToBottom)

  // Announce to screen readers only when a new message is added
  if (newLen > (oldLen || 0)) {
    const latestMessage = store.currentMessages[newLen - 1]
    if (latestMessage) {
      const sender = getSenderName(latestMessage.sender)
      // Use DOMPurify-backed sanitizeChatHtml to strip scripts/event-handlers, then
      // remove any remaining HTML tags to obtain plain text for the aria-live region.
      const preview = sanitizeChatHtml(latestMessage.content.substring(0, 200))
        .replace(/<[^>]*>/g, '')  // strip remaining HTML tags → plain text
        .substring(0, 100)
      screenReaderStatus.value = `New message from ${sender}: ${preview}${preview.length < latestMessage.content.length ? '...' : ''}`

      setTimeout(() => {
        screenReaderStatus.value = ''
      }, 2000)
    }
  }
})

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

// Initialize permission store on mount (scroll handled by useVirtualChatScroll)
onMounted(async () => {
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

<style scoped src="@/design-system/styles/chat-message-shared.css"></style>

<style scoped>
@reference "../../assets/tailwind.css";

.message-wrapper {
  @apply rounded-lg shadow-sm border transition-all duration-200 relative;
  max-width: 85%;
  padding: var(--spacing-1-5) var(--spacing-2-5);
}

.message-wrapper.user-message .message-content {
  color: var(--text-inverse);
}

/* ASSISTANT MESSAGES - Left side, design token theme */
.message-wrapper.assistant-message {
  @apply bg-autobot-bg-tertiary text-autobot-text-primary border-autobot-border mr-auto ml-0;
  border-radius: 18px 18px 18px 4px;
}

/* MVA-2006: SUMMARY MESSAGES - Context compression indicator */
.summary-message {
  @apply bg-blue-50 border border-blue-200 rounded-lg p-3 mb-2;
}

.summary-header {
  @apply flex items-center gap-2 font-semibold text-blue-900 mb-2;
}

.summary-icon {
  @apply text-xl;
}

.summary-title {
  @apply text-sm;
}

.summary-details {
  @apply mt-2;
}

.summary-toggle {
  @apply cursor-pointer text-sm text-blue-700 hover:text-blue-900 select-none;
  list-style: none;
}

.summary-toggle::marker {
  display: none;
}

.summary-toggle::before {
  content: '▶ ';
  display: inline-block;
  transition: transform 0.2s;
}

.summary-details[open] .summary-toggle::before {
  transform: rotate(90deg);
}

.summary-content {
  @apply mt-2 pt-2 border-t border-blue-200 text-sm text-gray-700;
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
  background: rgba(139, 92, 246, 0.08);
  border-color: rgba(139, 92, 246, 0.4);
  color: var(--text-secondary);
}

.message-wrapper.type-thought .message-avatar {
  background: var(--color-info);
}

.message-wrapper.type-thought .sender-name {
  color: var(--text-secondary);
}

.message-wrapper.type-thought .message-time {
  color: var(--text-muted);
}

.message-wrapper.type-thought .message-content {
  color: var(--text-secondary);
}

.message-wrapper.type-thought .message-text {
  color: var(--text-secondary);
}

.message-wrapper.type-thought::before {
  content: '';
  @apply absolute top-2 right-2 w-2 h-2 rounded-full;
  background: var(--color-info);
}

/* PLANNING MESSAGES - Indigo theme for task planning */
.message-wrapper.type-planning {
  background: rgba(99, 102, 241, 0.08);
  border-color: rgba(99, 102, 241, 0.4);
  color: var(--text-secondary);
}

.message-wrapper.type-planning .message-avatar {
  background: var(--color-info);
}

.message-wrapper.type-planning .sender-name {
  color: var(--text-secondary);
}

.message-wrapper.type-planning .message-time {
  color: var(--text-muted);
}

.message-wrapper.type-planning .message-content {
  color: var(--text-secondary);
}

.message-wrapper.type-planning .message-text {
  color: var(--text-secondary);
}

.message-wrapper.type-planning::before {
  content: '';
  @apply absolute top-2 right-2 w-2 h-2 rounded-full;
  background: var(--color-info);
}

/* DEBUG MESSAGES - Orange/Amber theme for debug output */
.message-wrapper.type-debug {
  background: var(--color-warning-bg);
  border-color: rgba(245, 158, 11, 0.5);
  color: var(--text-secondary);
}

.message-wrapper.type-debug .message-avatar {
  background: var(--color-warning);
}

.message-wrapper.type-debug .sender-name {
  color: var(--color-warning);
}

.message-wrapper.type-debug .message-time {
  color: var(--text-muted);
}

.message-wrapper.type-debug .message-content {
  color: var(--text-secondary);
}

.message-wrapper.type-debug .message-text {
  @apply font-mono text-xs;
  color: var(--text-secondary);
}

/* UTILITY MESSAGES - Neutral theme-aware for tool/utility output */
.message-wrapper.type-utility {
  @apply bg-autobot-bg-tertiary border-autobot-border text-autobot-text-primary;
}

.message-wrapper.type-utility .message-avatar {
  @apply bg-autobot-text-secondary;
}

.message-wrapper.type-utility .sender-name {
  @apply text-autobot-text-primary;
}

.message-wrapper.type-utility .message-time {
  @apply text-autobot-text-secondary;
}

/* SOURCES MESSAGES - Info-tinted theme-aware for source references */
.message-wrapper.type-sources {
  background: var(--color-info-bg);
  border-color: rgba(59, 130, 246, 0.4);
  color: var(--text-primary);
}

.message-wrapper.type-sources .message-avatar {
  background: var(--color-info);
}

.message-wrapper.type-sources .sender-name {
  @apply text-autobot-text-primary;
}

.message-wrapper.type-sources .message-time {
  @apply text-autobot-text-secondary;
}

/* JSON MESSAGES - Primary-tinted theme-aware for structured data */
.message-wrapper.type-json {
  background: rgba(59, 130, 246, 0.12);
  border-color: rgba(59, 130, 246, 0.5);
  color: var(--text-primary);
}

.message-wrapper.type-json .message-avatar {
  background: var(--color-primary);
}

.message-wrapper.type-json .message-text {
  @apply font-mono text-xs;
}

/* TERMINAL OUTPUT MESSAGES - Always-dark (intentional terminal aesthetic) */
.message-wrapper.type-terminal_output {
  @apply bg-gray-900 text-gray-100;
  border-color: rgba(16, 185, 129, 0.5);
}

.message-wrapper.type-terminal_output .message-avatar {
  background: var(--color-success);
}

.message-wrapper.type-terminal_output .sender-name {
  color: var(--color-success);
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

/* COMMAND APPROVAL REQUEST - Warning theme-aware */
.message-wrapper.type-command_approval_request {
  background: var(--color-warning-bg);
  border-color: rgba(245, 158, 11, 0.5);
  color: var(--text-primary);
}

.message-wrapper.type-command_approval_request .message-avatar {
  background: var(--color-warning);
}

.message-wrapper.type-command_approval_request .message-content {
  color: var(--text-primary);
}

/* Message type indicator badge */
.message-wrapper[class*="type-"]::after {
  @apply absolute top-1 right-1 px-1.5 py-0.5 text-xs font-medium rounded-full opacity-75;
}

.message-wrapper.type-thought::after {
  content: 'Thought';
  background: var(--color-info-bg);
  color: var(--color-info);
}

.message-wrapper.type-planning::after {
  content: 'Planning';
  background: var(--color-info-bg);
  color: var(--color-info);
}

.message-wrapper.type-debug::after {
  content: 'Debug';
  background: var(--color-warning-bg);
  color: var(--color-warning);
  border: 1px solid var(--color-warning-border);
}

.message-wrapper.type-utility::after {
  content: 'Utility';
  @apply bg-autobot-bg-tertiary text-autobot-text-secondary;
}

.message-wrapper.type-sources::after {
  content: 'Sources';
  background: var(--color-info-bg);
  color: var(--color-info);
}

.message-wrapper.type-terminal_output::after {
  content: 'Terminal';
  background: var(--bg-tertiary);
  color: var(--color-success);
}

/* Issue #690: Overseer Agent Message Styles */
.message-wrapper.type-overseer_plan::after {
  content: 'Plan';
  @apply bg-autobot-primary text-white;
}

.message-wrapper.type-overseer_step::after {
  content: 'Step';
  background: var(--color-info);
  color: var(--text-inverse);
}

.message-wrapper.type-overseer_plan,
.message-wrapper.type-overseer_step {
  @apply bg-autobot-bg-secondary border-autobot-border;
}

.message-wrapper.error {
  background: var(--color-error-bg);
  border-color: rgba(239, 68, 68, 0.3);
  color: var(--color-error);
}

.message-avatar.assistant {
  @apply bg-autobot-bg-secondary;
}

.message-avatar.system {
  @apply bg-autobot-bg-secondary;
}

/* Issue #1310: Type badges for clear message identification */
.message-type-badge {
  @apply inline-flex items-center text-xs font-semibold px-1.5 py-0.5 rounded ml-2;
  font-size: var(--text-xs);
  line-height: 1.2;
}

.badge-thought {
  background: var(--color-info-bg);
  color: var(--color-info);
  border: 1px solid rgba(139, 92, 246, 0.3);
}

.badge-planning {
  background: var(--color-info-bg);
  color: var(--color-info);
  border: 1px solid rgba(99, 102, 241, 0.3);
}

.badge-debug {
  background: var(--color-warning-bg);
  color: var(--color-warning);
  border: 1px solid var(--color-warning-border);
}

.badge-utility {
  background: var(--bg-tertiary);
  color: var(--text-muted);
  border: 1px solid var(--border-color);
}

.badge-sources {
  background: var(--color-info-bg);
  color: var(--color-info);
  border: 1px solid rgba(20, 184, 166, 0.3);
}

/* Button styling handled by BaseButton component */

.message-status {
  @apply flex items-center gap-1.5 mb-1.5 text-xs;
}

/* User message code styling - lighter for blue background */
.user-message .message-text :deep(code) {
  @apply px-1.5 py-0.5 rounded text-xs font-mono;
  background: rgba(0, 0, 0, 0.2);
  color: var(--text-inverse);
}

/* Assistant message code styling - standard colors for light background */
.assistant-message .message-text :deep(code) {
  @apply bg-autobot-bg-tertiary text-autobot-text-primary px-1.5 py-0.5 rounded text-xs font-mono;
}

.assistant-message .message-text :deep(a) {
  color: var(--text-link);
  text-decoration: underline;
}

.assistant-message .message-text :deep(a):hover {
  color: var(--text-link-hover);
}

/* User message metadata - lighter border for blue background */
.user-message .message-metadata {
  @apply mt-1.5 pt-1 border-t;
  border-color: rgba(255, 255, 255, 0.3);
}

/* Assistant message metadata - standard styling */
.assistant-message .message-metadata {
  @apply mt-1.5 pt-1 border-t border-autobot-border;
}

/* GH#8993: Thinking used badge */
.thinking-used-badge {
  @apply bg-amber-50 text-amber-700 px-1.5 py-0.5 rounded text-xs font-medium border border-amber-200;
}

.message-attachments {
  @apply mt-2 pt-1.5 border-t border-autobot-border;
}

.attachment-header {
  @apply flex items-center gap-1.5 text-xs text-autobot-text-secondary mb-1.5;
}

.attachment-list {
  @apply space-y-1;
}

.attachment-item {
  @apply flex items-center gap-1.5 p-1.5 bg-autobot-bg-tertiary rounded cursor-pointer hover:bg-autobot-bg-secondary transition-colors;
}

.attachment-name {
  @apply flex-1 text-xs text-autobot-text-secondary truncate;
}

.attachment-size {
  @apply text-xs text-autobot-text-muted;
}

.typing-indicator.large {
  @apply py-3;
}

.typing-dots span:nth-child(1) { --index: 0; }

.typing-dots span:nth-child(2) { --index: 1; }

.typing-dots span:nth-child(3) { --index: 2; }

.typing-text {
  @apply text-xs text-autobot-text-muted;
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
  @apply w-2.5 h-2.5 rounded-full;
  background: var(--color-primary);
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
  @apply absolute top-0 left-0 right-0 h-1 rounded-full;
  background: linear-gradient(to right, transparent, var(--color-primary), transparent);
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
  @apply font-medium;
  color: var(--color-primary);
}

/* Message Status Container */
.message-status-container {
  @apply mt-1.5 flex justify-end;
}

/* Message Skeleton */
.message-skeleton {
  @apply mt-3;
}

/* Issue #704: Migrated to CSS design tokens */
/* Scrollbar styling */
.overflow-y-auto::-webkit-scrollbar {
  width: 6px;
}

.overflow-y-auto::-webkit-scrollbar-track {
  background: var(--bg-secondary);
}

.overflow-y-auto::-webkit-scrollbar-thumb {
  background: var(--border-default);
  border-radius: var(--radius-sm);
}

.overflow-y-auto::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary);
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
  @apply mt-3 p-4 rounded-lg border-2;
  background: var(--color-warning-bg);
  border-color: rgba(245, 158, 11, 0.4);
}

/* Pre-approved State - Blue theme (auto-approved by security policy) */
.approval-confirmed.approval-pre-approved {
  @apply mt-3 p-4 rounded-lg border-2;
  background: var(--color-info-bg);
  border-color: rgba(59, 130, 246, 0.4);
}

.approval-confirmed.approval-pre-approved .approval-header {
  @apply flex items-center gap-2 mb-3 font-semibold;
  color: var(--color-info);
}

/* User Approved State - Green theme (manually approved by user) */
.approval-confirmed.approval-approved {
  @apply mt-3 p-4 rounded-lg border-2;
  background: var(--color-success-bg);
  border-color: rgba(34, 197, 94, 0.4);
}

.approval-confirmed.approval-approved .approval-header {
  @apply flex items-center gap-2 mb-3 font-semibold;
  color: var(--color-success);
}

/* Denied State - Red theme (manually denied by user) */
.approval-confirmed.approval-denied {
  @apply mt-3 p-4 rounded-lg border-2;
  background: var(--color-error-bg);
  border-color: rgba(239, 68, 68, 0.4);
}

.approval-confirmed.approval-denied .approval-header {
  @apply flex items-center gap-2 mb-3 font-semibold;
  color: var(--color-error);
}

.approval-header {
  @apply flex items-center gap-2 mb-3 font-semibold;
  color: var(--color-warning);
}

.approval-details {
  @apply space-y-2 mb-3;
}

.approval-detail-item {
  @apply flex items-start gap-2 text-sm;
}

.detail-label {
  @apply font-medium text-autobot-text-secondary min-w-24;
}

.detail-value {
  @apply flex-1 text-autobot-text-primary;
}

.detail-value code {
  @apply bg-autobot-bg-tertiary px-2 py-1 rounded text-xs font-mono;
}

/* Interactive Command Warning Styles (Issue #33) */
.interactive-warning {
  @apply flex-col p-3 rounded-lg mt-2;
  background: var(--color-info-bg);
  border: 1px solid rgba(59, 130, 246, 0.3);
}

.interactive-header {
  @apply flex items-center gap-2 mb-2;
}

.interactive-info {
  @apply ml-6;
}

.interactive-reasons {
  @apply mt-2 p-2 bg-autobot-bg-secondary rounded border border-autobot-border;
}

.approval-actions {
  @apply flex gap-2;
}

/* Button styling handled by BaseButton component */

.approval-processing {
  @apply flex items-center gap-2 mt-2 text-sm text-autobot-text-secondary;
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
  @apply mt-3 mb-3 p-3 bg-autobot-bg-card border border-autobot-border rounded-lg;
}

.comment-textarea {
  @apply w-full px-3 py-2 border border-autobot-border rounded-md resize-none focus:outline-none focus:ring-2;
  --tw-ring-color: var(--color-primary);
}

.comment-actions {
  @apply flex gap-2 mt-2;
}

/* Button styling handled by BaseButton component */

/* Auto-approve checkbox section */
.auto-approve-section {
  @apply mt-3 mb-3 p-3 rounded-lg;
  background: var(--color-info-bg);
  border: 1px solid rgba(59, 130, 246, 0.3);
}

.auto-approve-checkbox {
  @apply flex items-center gap-2 cursor-pointer;
}

.checkbox-input {
  @apply w-4 h-4 rounded border-autobot-border cursor-pointer;
  accent-color: var(--color-primary);
}

.checkbox-label {
  @apply flex items-center gap-2 text-sm font-medium text-autobot-text-secondary cursor-pointer select-none;
}

.checkbox-label i {
  color: var(--color-primary);
}

.auto-approve-hint {
  @apply mt-2 pl-6 flex items-start gap-2 text-xs;
  color: var(--color-info);
}

.auto-approve-hint i {
  @apply mt-0.5;
}

/* Permission v2: Remember for project checkbox section */
.remember-project-section {
  @apply mt-3 mb-3 p-3 rounded-lg;
  background: var(--color-success-bg);
  border: 1px solid rgba(34, 197, 94, 0.3);
}

.remember-project-checkbox {
  @apply flex items-center gap-2 cursor-pointer;
}

.remember-project-checkbox .checkbox-label i {
  color: var(--color-success);
}

.remember-project-hint {
  @apply mt-2 pl-6 flex items-start gap-2 text-xs;
  color: var(--color-success);
}

.remember-project-hint i {
  @apply mt-0.5;
}

/* Issue #249: Knowledge Citations Styles */
.knowledge-citations {
  @apply mt-3 border border-autobot-border rounded-lg overflow-hidden bg-autobot-bg-tertiary;
}

.citations-header {
  @apply flex items-center justify-between px-3 py-2 cursor-pointer transition-colors;
}

.citations-header:hover {
  @apply bg-autobot-bg-secondary;
}

.citations-header-left {
  @apply flex items-center gap-2;
}

.citations-label {
  @apply text-sm font-medium text-autobot-primary;
}

.citations-count {
  @apply px-1.5 py-0.5 text-xs font-semibold bg-autobot-primary text-white rounded-full;
}

.citations-list {
  @apply border-t border-autobot-border bg-autobot-bg-card;
}

.citation-item {
  @apply flex gap-2 px-3 py-2 border-b border-autobot-border last:border-b-0;
}

.citation-rank {
  @apply text-sm font-mono font-semibold text-autobot-primary flex-shrink-0;
}

.citation-content {
  @apply flex-1 min-w-0;
}

.citation-text {
  @apply text-sm text-autobot-text-secondary leading-snug mb-1;
}

.citation-meta {
  @apply flex flex-wrap gap-3 text-xs text-autobot-text-muted;
}

.citation-score {
  @apply flex items-center gap-1 font-medium;
}

.citation-score.score-excellent {
  color: var(--color-success);
}

.citation-score.score-good {
  color: var(--color-primary);
}

.citation-score.score-acceptable {
  color: var(--color-warning);
}

.citation-score.score-low {
  @apply text-autobot-text-muted;
}

.citation-source {
  @apply flex items-center gap-1 text-autobot-text-muted;
}

/* Citation slide transition */
.slide-fade-enter-active {
  transition: all var(--duration-200) var(--ease-out);
}

.slide-fade-leave-active {
  transition: all var(--duration-150) var(--ease-in);
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
