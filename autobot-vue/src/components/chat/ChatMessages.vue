<template>
  <div class="flex-1 overflow-y-auto p-4" ref="messagesContainer">
    <div v-if="store.currentMessages.length === 0" class="empty-state">
      <div class="text-center py-12">
        <i class="fas fa-comments text-4xl text-gray-400 mb-4"></i>
        <h3 class="text-lg font-medium text-gray-900 mb-2">Start a conversation</h3>
        <p class="text-gray-500">Send a message to begin chatting with the AI assistant.</p>
      </div>
    </div>

    <div v-else class="space-y-4">
      <div
        v-for="message in filteredMessages"
        :key="message.id"
        class="message-wrapper"
        :class="getMessageWrapperClass(message)"
      >
        <!-- Message Header -->
        <div class="message-header">
          <div class="flex items-center gap-2">
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

        <!-- Message Status -->
        <div v-if="message.status && message.status !== 'sent'" class="message-status">
          <i
            class="fas"
            :class="{
              'fa-clock text-yellow-500': message.status === 'sending',
              'fa-exclamation-triangle text-red-500': message.status === 'error'
            }"
          ></i>
          <span class="text-sm">
            {{ getStatusText(message.status) }}
          </span>
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
        </div>
      </div>

      <!-- Loading indicator for AI response -->
      <div v-if="store.isTyping" class="message-wrapper assistant-message">
        <div class="message-header">
          <div class="flex items-center gap-2">
            <div class="message-avatar assistant">
              <i class="fas fa-robot"></i>
            </div>
            <div class="message-info">
              <span class="sender-name">AI Assistant</span>
              <span class="message-time">Thinking...</span>
            </div>
          </div>
        </div>
        <div class="message-content">
          <div class="typing-indicator large">
            <div class="typing-dots">
              <span></span>
              <span></span>
              <span></span>
            </div>
            <span class="typing-text">AI is thinking...</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Auto-scroll anchor -->
    <div ref="scrollAnchor"></div>
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
import type { ChatMessage } from '@/stores/useChatStore'

const store = useChatStore()
const controller = useChatController()

// Refs
const messagesContainer = ref<HTMLElement>()
const scrollAnchor = ref<HTMLElement>()
const editTextarea = ref<HTMLTextAreaElement>()

// Edit modal state
const showEditModal = ref(false)
const editingContent = ref('')
const editingMessage = ref<ChatMessage | null>(null)

// Display settings (would come from user preferences)
const displaySettings = ref({
  showThoughts: true,
  showJson: false,
  showUtility: true,
  showPlanning: true,
  showDebug: false,
  showSources: true,
  showMetadata: true
})

// Computed
const filteredMessages = computed(() => {
  return store.currentMessages.filter(message => {
    // Filter messages based on display settings
    if (message.sender === 'system' && !displaySettings.value.showUtility) return false
    if (message.content.startsWith('[THOUGHT]') && !displaySettings.value.showThoughts) return false
    if (message.content.startsWith('[DEBUG]') && !displaySettings.value.showDebug) return false
    if (message.content.startsWith('[PLANNING]') && !displaySettings.value.showPlanning) return false

    return true
  })
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
  return displaySettings.value.showMetadata &&
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

const scrollToBottom = () => {
  if (store.settings.autoSave && scrollAnchor.value) { // Using autoSave as proxy for auto-scroll
    scrollAnchor.value.scrollIntoView({ behavior: 'smooth' })
  }
}

// Auto-scroll when new messages arrive
watch(() => store.currentMessages.length, () => {
  nextTick(scrollToBottom)
})

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
  @apply bg-white rounded-lg shadow-sm border border-gray-200 p-4 transition-all duration-200;
}

.message-wrapper:hover {
  @apply shadow-md;
}

.message-wrapper.user-message {
  @apply bg-indigo-50 border-indigo-200 ml-12;
}

.message-wrapper.assistant-message {
  @apply bg-blue-50 border-blue-200 mr-12;
}

.message-wrapper.system-message {
  @apply bg-gray-50 border-gray-200 mx-8;
}

.message-wrapper.error {
  @apply bg-red-50 border-red-200;
}

.message-wrapper.sending {
  @apply opacity-70;
}

.message-header {
  @apply flex items-start justify-between mb-2;
}

.message-avatar {
  @apply w-8 h-8 rounded-full flex items-center justify-center text-white text-sm;
}

.message-avatar.user {
  @apply bg-indigo-600;
}

.message-avatar.assistant {
  @apply bg-blue-600;
}

.message-avatar.system {
  @apply bg-gray-600;
}

.message-info {
  @apply flex flex-col ml-2;
}

.sender-name {
  @apply font-semibold text-gray-900 text-sm;
}

.message-time {
  @apply text-xs text-gray-500;
}

.message-actions {
  @apply flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity;
}

.action-btn {
  @apply w-8 h-8 flex items-center justify-center text-gray-400 hover:text-gray-600 rounded transition-colors;
}

.action-btn.danger:hover {
  @apply text-red-600;
}

.message-status {
  @apply flex items-center gap-2 mb-2 text-sm;
}

.message-content {
  @apply text-gray-800 leading-relaxed;
}

.message-text {
  @apply break-words;
}

.message-text :deep(code) {
  @apply bg-gray-100 px-1 py-0.5 rounded text-sm font-mono;
}

.message-text :deep(pre) {
  @apply bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto my-2;
}

.message-text :deep(a) {
  @apply text-indigo-600 hover:text-indigo-800 underline;
}

.message-metadata {
  @apply mt-3 pt-2 border-t border-gray-200;
}

.metadata-items {
  @apply flex flex-wrap gap-3 text-xs text-gray-500;
}

.metadata-item {
  @apply flex items-center gap-1;
}

.message-attachments {
  @apply mt-3 pt-2 border-t border-gray-200;
}

.attachment-header {
  @apply flex items-center gap-2 text-sm text-gray-600 mb-2;
}

.attachment-list {
  @apply space-y-1;
}

.attachment-item {
  @apply flex items-center gap-2 p-2 bg-gray-50 rounded cursor-pointer hover:bg-gray-100 transition-colors;
}

.attachment-name {
  @apply flex-1 text-sm text-gray-700 truncate;
}

.attachment-size {
  @apply text-xs text-gray-500;
}

.typing-indicator {
  @apply flex items-center gap-2;
}

.typing-indicator.large {
  @apply py-4;
}

.typing-dots {
  @apply flex gap-1;
}

.typing-dots span {
  @apply w-2 h-2 bg-gray-400 rounded-full animate-pulse;
  animation-delay: calc(var(--index) * 0.2s);
}

.typing-dots span:nth-child(1) { --index: 0; }
.typing-dots span:nth-child(2) { --index: 1; }
.typing-dots span:nth-child(3) { --index: 2; }

.typing-text {
  @apply text-sm text-gray-500;
}

.streaming-content {
  @apply space-y-2;
}

/* Scrollbar styling */
.overflow-y-auto::-webkit-scrollbar {
  width: 8px;
}

.overflow-y-auto::-webkit-scrollbar-track {
  background: #f8fafc;
}

.overflow-y-auto::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 4px;
}

.overflow-y-auto::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}

/* Animation for new messages */
@keyframes slideInFromBottom {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.message-wrapper {
  animation: slideInFromBottom 0.3s ease-out;
}

/* Responsive adjustments */
@media (max-width: 768px) {
  .message-wrapper.user-message {
    @apply ml-4;
  }

  .message-wrapper.assistant-message {
    @apply mr-4;
  }

  .message-wrapper.system-message {
    @apply mx-2;
  }
}
</style>
