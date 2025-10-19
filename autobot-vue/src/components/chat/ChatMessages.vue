<template>
  <div
    class="p-4"
    ref="messagesContainer"
    v-bind="$attrs"
  >
    <div v-if="store.currentMessages.length === 0" class="empty-state">
      <div class="text-center py-12">
        <i class="fas fa-comments text-4xl text-gray-400 mb-4"></i>
        <h3 class="text-lg font-medium text-gray-900 mb-2">Start a conversation</h3>
        <p class="text-gray-500">Send a message to begin chatting with the AI assistant.</p>
      </div>
    </div>

    <div v-else class="space-y-1">
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
              <i :class="getSenderIcon(message.sender)"></i>
            </div>
            <div class="message-info">
              <span class="sender-name">{{ getSenderName(message.sender) }}</span>
              <span class="message-time">{{ formatTime(message.timestamp) }}</span>
            </div>
          </div>

          <div class="message-actions">
            <button
              v-if="message.sender === 'user'"
              @click="editMessage(message)"
              class="action-btn"
              title="Edit message"
            >
              <i class="fas fa-edit"></i>
            </button>
            <button
              @click="copyMessage(message)"
              class="action-btn"
              title="Copy message"
            >
              <i class="fas fa-copy"></i>
            </button>
            <button
              @click="deleteMessage(message)"
              class="action-btn danger"
              title="Delete message"
            >
              <i class="fas fa-trash"></i>
            </button>
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

        <!-- Message Content -->
        <div class="message-content" :class="getContentClass(message)">
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
                <i class="fas fa-robot"></i>
                {{ message.metadata.model }}
              </span>
              <span v-if="message.metadata.tokens" class="metadata-item">
                <i class="fas fa-coins"></i>
                {{ message.metadata.tokens }} tokens
              </span>
              <span v-if="message.metadata.duration" class="metadata-item">
                <i class="fas fa-clock"></i>
                {{ message.metadata.duration }}ms
              </span>
            </div>
          </div>

          <!-- Attachments -->
          <div v-if="message.attachments && message.attachments.length > 0" class="message-attachments">
            <div class="attachment-header">
              <i class="fas fa-paperclip"></i>
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
              <i class="fas fa-shield-check text-blue-600"></i>
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
              <i class="fas fa-check-circle text-green-600"></i>
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
              <i class="fas fa-times-circle text-red-600"></i>
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
          <div v-else-if="message.metadata?.requires_approval" class="approval-request">
            <div class="approval-header">
              <i class="fas fa-exclamation-triangle text-yellow-600"></i>
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
                <button
                  @click="cancelComment"
                  class="cancel-comment-btn"
                >
                  <i class="fas fa-times"></i>
                  <span>Cancel</span>
                </button>
                <button
                  @click="submitApprovalWithComment(message.metadata.terminal_session_id, pendingApprovalDecision)"
                  class="submit-comment-btn"
                  :disabled="!approvalComment.trim()"
                >
                  <i class="fas fa-check"></i>
                  <span>Submit {{ pendingApprovalDecision ? 'Approval' : 'Denial' }}</span>
                </button>
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
                  <i class="fas fa-shield-check"></i>
                  Automatically approve similar commands in the future
                </span>
              </label>
              <div v-if="autoApproveFuture" class="auto-approve-hint">
                <i class="fas fa-info-circle"></i>
                <span>Commands with the same pattern and risk level will be auto-approved</span>
              </div>
            </div>

            <div class="approval-actions">
              <button
                @click="approveCommand(message.metadata.terminal_session_id, true)"
                class="approve-btn"
                :disabled="processingApproval || showCommentInput"
              >
                <i class="fas fa-check"></i>
                <span>Approve</span>
              </button>
              <button
                @click="promptForComment(message.metadata.terminal_session_id)"
                class="comment-btn"
                :disabled="processingApproval || showCommentInput"
              >
                <i class="fas fa-comment"></i>
                <span>Comment</span>
              </button>
              <button
                @click="approveCommand(message.metadata.terminal_session_id, false)"
                class="deny-btn"
                :disabled="processingApproval || showCommentInput"
              >
                <i class="fas fa-times"></i>
                <span>Deny</span>
              </button>
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
  <div v-if="showEditModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
    <div class="bg-white rounded-lg p-6 w-96 max-w-90vw max-h-80vh overflow-hidden flex flex-col">
      <h3 class="text-lg font-semibold mb-4">Edit Message</h3>
      <textarea
        v-model="editingContent"
        class="flex-1 w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
        placeholder="Enter your message..."
        @keydown.ctrl.enter="saveEditedMessage"
        @keydown.meta.enter="saveEditedMessage"
        ref="editTextarea"
      ></textarea>
      <div class="flex justify-end gap-2 mt-4">
        <button
          class="px-4 py-2 text-gray-600 hover:text-gray-800"
          @click="cancelEdit"
        >
          Cancel
        </button>
        <button
          class="px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700"
          @click="saveEditedMessage"
          :disabled="!editingContent.trim()"
        >
          Save
        </button>
      </div>
      <div class="text-xs text-gray-500 mt-2">
        Press Ctrl+Enter (Cmd+Enter on Mac) to save
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, watch, onMounted, onUnmounted } from 'vue'
import { useChatStore } from '@/stores/useChatStore'
import { useChatController } from '@/models/controllers'
import { useDisplaySettings } from '@/composables/useDisplaySettings'
import type { ChatMessage } from '@/stores/useChatStore'
import MessageStatus from '@/components/ui/MessageStatus.vue'
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue'
import SkeletonLoader from '@/components/ui/SkeletonLoader.vue'

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

// Refs
const messagesContainer = ref<HTMLElement>()
const editTextarea = ref<HTMLTextAreaElement>()

// Edit modal state
const showEditModal = ref(false)
const editingContent = ref('')
const editingMessage = ref<ChatMessage | null>(null)

// Enhanced typing indicator state
const typingStartTime = ref<number | null>(null)
const estimatedResponseTime = ref<number | null>(null)

// Approval state
const processingApproval = ref(false)

// Comment functionality state
const showCommentInput = ref(false)
const activeCommentSessionId = ref<string | null>(null)
const approvalComment = ref('')
const pendingApprovalDecision = ref<boolean | null>(null)

// Auto-approve functionality state
const autoApproveFuture = ref(false)

// Computed
const filteredMessages = computed(() => {
  return store.currentMessages.filter(message => {
    // Filter messages based on display settings and message type
    // Show Utility Messages - controls tool usage messages
    if (message.type === 'utility' && !displaySettings.value.showUtility) return false

    // Show Thoughts - controls LLM thought messages
    if (message.type === 'thought' && !displaySettings.value.showThoughts) return false

    // Show Planning Messages - controls LLM planning process messages
    if (message.type === 'planning' && !displaySettings.value.showPlanning) return false

    // Show Debug Messages - controls debug output
    if (message.type === 'debug' && !displaySettings.value.showDebug) return false

    // Show Sources - controls source reference messages
    if (message.type === 'sources' && !displaySettings.value.showSources) return false

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

  if (message.status === 'error') classes.push('error')
  if (message.status === 'sending') classes.push('sending')

  return classes.join(' ')
}

const getAvatarClass = (sender: string): string => {
  return `message-avatar ${sender}`
}

const getSenderIcon = (sender: string): string => {
  const icons = {
    user: 'fas fa-user',
    assistant: 'fas fa-robot',
    system: 'fas fa-cog',
    error: 'fas fa-exclamation-triangle',
    thought: 'fas fa-brain',
    'tool-code': 'fas fa-code',
    'tool-output': 'fas fa-terminal'
  }

  return icons[sender as keyof typeof icons] || 'fas fa-comment'
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

const formatTime = (timestamp: Date | string): string => {
  const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp
  if (!date || !(date instanceof Date) || isNaN(date.getTime())) {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

const formatMessageContent = (content: string): string => {
  // Basic markdown-like formatting
  let formatted = content
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')

  // Code blocks
  formatted = formatted.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
    return `<pre class="code-block${lang ? ` language-${lang}` : ''}"><code>${code.trim()}</code></pre>`
  })

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
  return displaySettings.value.showJson &&
         message.sender === 'assistant' &&
         message.metadata &&
         Object.keys(message.metadata).length > 0
}

const hasCodeBlocks = (content: string): boolean => {
  return /```[\s\S]*?```/.test(content)
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

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 Bytes'
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

const viewAttachment = (attachment: any) => {
  // Handle attachment viewing
  if (attachment.url) {
    window.open(attachment.url, '_blank')
  }
}

const retryMessage = async (messageId: string) => {
  try {
    await controller.retryMessage(messageId)
  } catch (error) {
    console.error('Failed to retry message:', error)
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

      console.log('🔧 TOOL_CALL detected:', { command: params.command, host: params.host, purpose: description })

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
            console.log('[TOOL_CALL] Found terminal_session_id in message metadata:', terminal_session_id)
            break
          }
        }

        if (!terminal_session_id) {
          console.warn('[TOOL_CALL] No terminal_session_id found in recent messages')
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
      console.error('Failed to parse TOOL_CALL:', error)
    }
  }
}

// Command Approval - Use HTTP POST to agent-terminal API
const approveCommand = async (terminal_session_id: string, approved: boolean, comment?: string) => {
  if (!terminal_session_id) {
    console.error('No terminal_session_id provided for approval')
    return
  }

  processingApproval.value = true
  console.log(`${approved ? 'Approving' : 'Denying'} command for session:`, terminal_session_id)
  if (comment) {
    console.log('With comment:', comment)
  }
  if (autoApproveFuture.value) {
    console.log('Auto-approve similar commands in future:', autoApproveFuture.value)
  }

  try {
    // Use HTTP POST to agent-terminal approval endpoint
    const backendUrl = `http://172.16.168.20:8001/api/agent-terminal/sessions/${terminal_session_id}/approve`

    const response = await fetch(backendUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        approved,
        user_id: 'web_user',
        comment: comment || null,
        auto_approve_future: autoApproveFuture.value  // Send auto-approve preference
      })
    })

    const result = await response.json()
    console.log('Approval response:', result)

    if (result.status === 'approved' || result.status === 'denied') {
      console.log(`Command ${approved ? 'approved' : 'denied'} successfully`)

      // Update the message metadata to reflect approval status
      const targetMessage = store.currentMessages.find(
        msg => msg.metadata?.terminal_session_id === terminal_session_id &&
               msg.metadata?.requires_approval === true
      )

      if (targetMessage && targetMessage.metadata) {
        targetMessage.metadata.approval_status = result.status
        targetMessage.metadata.approval_comment = comment || result.comment
        console.log('Updated message approval status:', targetMessage.metadata)
      } else {
        console.warn('Could not find message to update approval status')
      }

      // Reset auto-approve checkbox after submission
      autoApproveFuture.value = false
    } else if (result.status === 'error') {
      console.error('Approval error:', result.error)
    }

    processingApproval.value = false
  } catch (error) {
    console.error('Error sending approval:', error)
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
    console.warn('Cannot submit approval with empty comment')
    return
  }

  // Determine approval decision
  const finalDecision = approved !== null ? approved : pendingApprovalDecision.value

  if (finalDecision === null) {
    console.error('No approval decision provided')
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

// Scroll to bottom on mount
onMounted(() => {
  nextTick(scrollToBottom)
})
</script>

<style scoped>
.empty-state {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.message-wrapper {
  @apply rounded-lg shadow-sm border transition-all duration-200;
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

.message-time {
  @apply text-xs leading-tight;
}

.message-actions {
  @apply flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity;
}

.action-btn {
  @apply w-6 h-6 flex items-center justify-center rounded transition-colors text-xs;
}

/* User message actions - light colored for visibility on blue background */
.user-message .action-btn {
  @apply text-blue-200 hover:text-white;
}

/* Assistant message actions - darker for visibility on light background */
.assistant-message .action-btn {
  @apply text-gray-400 hover:text-gray-600;
}

.action-btn.danger:hover {
  @apply text-red-500;
}

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

.approval-actions {
  @apply flex gap-2;
}

.approve-btn,
.deny-btn {
  @apply flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed;
}

.approve-btn {
  @apply bg-green-600 text-white hover:bg-green-700 active:bg-green-800;
}

.deny-btn {
  @apply bg-red-600 text-white hover:bg-red-700 active:bg-red-800;
}

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

  .action-btn {
    @apply w-5 h-5 text-xs;
  }

  .approval-actions {
    @apply flex-col;
  }

  .approve-btn,
  .deny-btn {
    @apply w-full justify-center;
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

.cancel-comment-btn {
  @apply flex items-center gap-2 px-4 py-2 rounded-lg font-medium bg-gray-300 text-gray-700 hover:bg-gray-400 transition-all;
}

.submit-comment-btn {
  @apply flex items-center gap-2 px-4 py-2 rounded-lg font-medium bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800 disabled:opacity-50 disabled:cursor-not-allowed transition-all;
}

.comment-btn {
  @apply flex items-center gap-2 px-4 py-2 rounded-lg font-medium bg-yellow-600 text-white hover:bg-yellow-700 active:bg-yellow-800 disabled:opacity-50 disabled:cursor-not-allowed transition-all;
}

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
</style>