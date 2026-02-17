<template>
  <div class="chat-input-container">
    <!-- File Upload Progress -->
    <div v-if="uploadProgress.length > 0" class="upload-progress mb-4">
      <div
        v-for="upload in uploadProgress"
        :key="upload.id"
        class="upload-item"
      >
        <div class="upload-info">
          <div class="upload-filename">{{ upload.filename }}</div>
          <div class="upload-status">{{ upload.status }}</div>
        </div>
        <ProgressBar
          :progress="upload.progress"
          :variant="upload.error ? 'error' : 'info'"
          :current="upload.current"
          :total="upload.total"
          :eta="upload.eta"
          size="sm"
          :show-details="true"
        />
        <BaseButton
          v-if="upload.error"
          variant="danger"
          size="xs"
          @click="retryUpload(upload.id)"
          class="retry-upload-btn"
          aria-label="Retry upload"
        >
          <i class="fas fa-redo" aria-hidden="true"></i>
        </BaseButton>
      </div>
    </div>

    <!-- Attached Files Display -->
    <div v-if="attachedFiles.length > 0" class="attached-files mb-4">
      <div class="attached-files-header">
        <h4 class="text-sm font-medium text-autobot-text-secondary">
          <i class="fas fa-paperclip mr-1" aria-hidden="true"></i>
          {{ attachedFiles.length }} file{{ attachedFiles.length > 1 ? 's' : '' }} attached
        </h4>
        <BaseButton variant="ghost" size="sm" @click="clearAllFiles" class="text-red-600 hover:text-red-800">
          Clear all
        </BaseButton>
      </div>

      <div class="attached-files-list">
        <div
          v-for="(file, index) in attachedFiles"
          :key="index"
          class="attached-file-item"
        >
          <div class="file-icon">
            <i :class="getFileIcon(file.type)"></i>
          </div>
          <div class="file-info">
            <span class="file-name">{{ file.name }}</span>
            <span class="file-size">{{ formatFileSize(file.size) }}</span>
          </div>
          <BaseButton
            variant="ghost"
            size="xs"
            @click="removeFile(index)"
            class="remove-file-btn"
            aria-label="Remove file"
          >
            <i class="fas fa-times" aria-hidden="true"></i>
          </BaseButton>
        </div>
      </div>
    </div>

    <!-- Main Input Area -->
    <div class="input-wrapper">
      <div class="input-container">
        <!-- File Input (Hidden) -->
        <input
          ref="fileInput"
          type="file"
          multiple
          accept=".txt,.md,.pdf,.doc,.docx,.json,.csv,.png,.jpg,.jpeg,.gif"
          @change="handleFileSelect"
          style="display: none"
        />

        <!-- Message Input -->
        <div
          class="message-input-wrapper"
          :class="{ 'focused': isInputFocused }"
        >
          <label for="chat-message-input" class="sr-only">Chat message</label>
          <textarea
            id="chat-message-input"
            ref="messageInput"
            v-model="messageText"
            :placeholder="inputPlaceholder"
            class="message-input"
            :disabled="isDisabled"
            aria-label="Type your chat message here. Press Enter to send, Shift+Enter for new line"
            aria-describedby="chat-input-help"
            @keydown="handleKeydown"
            @focus="isInputFocused = true"
            @blur="isInputFocused = false"
            @input="handleInput"
            rows="1"
          ></textarea>
          <span id="chat-input-help" class="sr-only">
            Press Enter to send your message. Press Shift+Enter to create a new line.
          </span>

          <!-- Input Actions -->
          <div class="input-actions">
            <!-- Issue #249: Knowledge Base Toggle -->
            <label class="knowledge-toggle" :class="{ 'active': useKnowledge }" title="Use Knowledge Base for enhanced answers">
              <input
                type="checkbox"
                v-model="useKnowledge"
                class="knowledge-checkbox sr-only"
                :disabled="isDisabled"
              />
              <i class="fas fa-brain" aria-hidden="true"></i>
              <span class="toggle-label">KB</span>
            </label>

            <!-- Issue #690: Overseer Mode Toggle -->
            <label
              class="overseer-toggle"
              :class="{ 'active': overseerEnabled }"
              title="Overseer Mode: Break down tasks into steps with command explanations"
              @click.prevent="toggleOverseer"
            >
              <i class="fas fa-sitemap" aria-hidden="true"></i>
              <span class="toggle-label">Explain</span>
            </label>

            <!-- Vertical Divider after toggles -->
            <div class="action-divider"></div>

            <!-- File Attach Button -->
            <BaseButton
              variant="ghost"
              size="xs"
              @click="attachFile"
              class="action-btn"
              :disabled="isDisabled"
              aria-label="Attach file"
            >
              <i class="fas fa-paperclip" aria-hidden="true"></i>
            </BaseButton>

            <!-- Voice Input Button -->
            <BaseButton
              variant="ghost"
              size="xs"
              @click="toggleVoiceInput"
              class="action-btn"
              :class="{ 'active': isVoiceRecording }"
              :disabled="isDisabled"
              aria-label="Voice input"
            >
              <i :class="isVoiceRecording ? 'fas fa-stop' : 'fas fa-microphone'" aria-hidden="true"></i>
            </BaseButton>

            <!-- Emoji Button -->
            <BaseButton
              variant="ghost"
              size="xs"
              @click="toggleEmojiPicker"
              class="action-btn"
              :disabled="isDisabled"
              aria-label="Add emoji"
            >
              <i class="fas fa-smile" aria-hidden="true"></i>
            </BaseButton>

            <!-- Vertical Divider -->
            <div class="action-divider"></div>

            <!-- Quick Actions -->
            <BaseButton
              v-for="action in quickActions"
              :key="action.id"
              variant="ghost"
              size="sm"
              @click="useQuickAction(action)"
              class="action-btn quick-action-btn"
              :disabled="isDisabled"
              :aria-label="action.description"
            >
              <i :class="action.icon"></i>
              <span class="action-label">{{ action.label }}</span>
            </BaseButton>
          </div>
        </div>

        <!-- Send Button -->
        <BaseButton
          variant="primary"
          @click="sendMessage"
          class="send-button"
          :disabled="!canSend"
          :loading="isSending"
          :class="{ 'pulse': messageQueueLength > 0 }"
          :aria-label="isSending ? 'Sending...' : canSend ? 'Send message (Enter)' : 'Enter a message to send'"
        >
          <div v-if="!isSending && messageQueueLength > 0" class="queue-indicator">
            <i class="fas fa-paper-plane" aria-hidden="true"></i>
            <span class="queue-count">{{ messageQueueLength }}</span>
          </div>
          <i v-else-if="!isSending" class="fas fa-paper-plane" aria-hidden="true"></i>
        </BaseButton>
      </div>

      <!-- Input Status Bar -->
      <div class="input-status-bar">
        <div class="status-left">
          <span v-if="isTypingIndicatorVisible" class="typing-indicator">
            <i class="fas fa-keyboard" aria-hidden="true"></i>
            Typing...
          </span>
          <span v-if="characterCount > 0" class="character-count" :class="{ 'warning': isNearLimit }">
            {{ characterCount }}/{{ maxCharacters }}
          </span>
        </div>

        <div class="status-right">
          <span v-if="isVoiceRecording" class="voice-status">
            <i class="fas fa-circle text-red-500 animate-pulse" aria-hidden="true"></i>
            Recording...
          </span>
          <span class="keyboard-hint">Enter to send • Shift+Enter for new line</span>
        </div>
      </div>
    </div>

    <!-- Emoji Picker -->
    <div v-if="showEmojiPicker" class="emoji-picker" ref="emojiPicker">
      <div class="emoji-header">
        <span class="emoji-title">Add Emoji</span>
        <BaseButton variant="ghost" size="xs" @click="showEmojiPicker = false" class="close-emoji-btn" aria-label="Close emoji picker">
          <i class="fas fa-times" aria-hidden="true"></i>
        </BaseButton>
      </div>
      <div class="emoji-grid">
        <BaseButton
          v-for="emoji in commonEmojis"
          :key="emoji.code"
          variant="ghost"
          size="sm"
          @click="insertEmoji(emoji)"
          class="emoji-btn"
          :aria-label="emoji.name"
        >
          {{ emoji.emoji }}
        </BaseButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted, inject, type Ref, type ComputedRef } from 'vue'
import { useChatStore } from '@/stores/useChatStore'
import { useChatController } from '@/models/controllers'
import globalWebSocketService from '@/services/GlobalWebSocketService'
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue'
import ProgressBar from '@/components/ui/ProgressBar.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { formatFileSize } from '@/utils/formatHelpers'
import { getFileIconByMimeType } from '@/utils/iconMappings'
import { createLogger } from '@/utils/debugUtils'
import type { UseOverseerAgentOptions } from '@/composables/useOverseerAgent'

const logger = createLogger('ChatInput')

// Issue #690: Inject overseer state from ChatInterface
const overseerEnabled = inject<Ref<boolean>>('overseerEnabled', ref(false))
const toggleOverseer = inject<() => void>('toggleOverseer', () => {})
const submitOverseerQuery = inject<(query: string) => Promise<boolean>>('submitOverseerQuery', async () => false)

const store = useChatStore()
const controller = useChatController()

// Refs
const messageInput = ref<HTMLTextAreaElement>()
const fileInput = ref<HTMLInputElement>()
const emojiPicker = ref<HTMLElement>()

// State
const messageText = ref('')
const attachedFiles = ref<File[]>([])
const isInputFocused = ref(false)
const isVoiceRecording = ref(false)
const isSending = ref(false)
const showEmojiPicker = ref(false)
const showQuickActions = ref(true)

// Issue #249: Knowledge-Enhanced Chat (RAG) toggle
const useKnowledge = ref(true) // Default enabled
const uploadProgress = ref<Array<{
  id: string
  filename: string
  progress: number
  status: string
  current: number
  total: number
  eta?: number
  error?: string
  file?: File  // Store original File object for retry functionality
}>>([])
const messageQueueLength = ref(0)
const isTypingStartTime = ref<number | null>(null)
const typingDebounceTimer = ref<number | null>(null)

// Constants
const maxCharacters = 4000
const maxFileSize = 10 * 1024 * 1024 // 10MB

// Quick actions
const quickActions = [
  { id: 'help', label: 'Help', icon: 'fas fa-question-circle', description: 'Get help with using the assistant' },
  { id: 'summarize', label: 'Summarize', icon: 'fas fa-compress', description: 'Summarize the conversation' },
  { id: 'translate', label: 'Translate', icon: 'fas fa-language', description: 'Translate text' },
  { id: 'explain', label: 'Explain', icon: 'fas fa-lightbulb', description: 'Get an explanation' }
]

// Common emojis
const commonEmojis = [
  { emoji: '😀', name: 'grinning face', code: '1f600' },
  { emoji: '😂', name: 'face with tears of joy', code: '1f602' },
  { emoji: '😊', name: 'smiling face with smiling eyes', code: '1f60a' },
  { emoji: '😍', name: 'smiling face with heart-eyes', code: '1f60d' },
  { emoji: '🤔', name: 'thinking face', code: '1f914' },
  { emoji: '👍', name: 'thumbs up', code: '1f44d' },
  { emoji: '👎', name: 'thumbs down', code: '1f44e' },
  { emoji: '❤️', name: 'red heart', code: '2764' },
  { emoji: '🔥', name: 'fire', code: '1f525' },
  { emoji: '⭐', name: 'star', code: '2b50' },
  { emoji: '💡', name: 'light bulb', code: '1f4a1' },
  { emoji: '✅', name: 'check mark button', code: '2705' }
]

// Computed
const inputPlaceholder = computed(() => {
  if (isVoiceRecording.value) return 'Listening...'
  if (isSending.value) return 'Sending message...'
  if (store.isTyping) return 'AI is responding...'
  return 'Type your message...'
})

const isDisabled = computed(() => {
  return isSending.value || isVoiceRecording.value
})

const canSend = computed(() => {
  return messageText.value.trim().length > 0 && !isSending.value && !isVoiceRecording.value
})

const characterCount = computed(() => messageText.value.length)

const isNearLimit = computed(() => characterCount.value > maxCharacters * 0.9)

const isTypingIndicatorVisible = computed(() => {
  return messageText.value.length > 0 && isInputFocused.value
})

// Methods
const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Enter' && canSend.value) {
    // Shift+Enter creates new line, Enter sends message
    if (!event.shiftKey) {
      event.preventDefault()
      sendMessage()
      return
    }
  }

  // Auto-resize textarea
  const target = event.target as HTMLTextAreaElement
  target.style.height = 'auto'
  target.style.height = Math.min(target.scrollHeight, 150) + 'px'
}

const handleInput = (event: Event) => {
  const target = event.target as HTMLTextAreaElement

  // Limit character count
  if (target.value.length > maxCharacters) {
    target.value = target.value.slice(0, maxCharacters)
    messageText.value = target.value
  }

  // Auto-resize
  target.style.height = 'auto'
  target.style.height = Math.min(target.scrollHeight, 150) + 'px'

  // Update typing indicator
  updateTypingIndicator()
}

const sendMessage = async () => {
  if (!canSend.value) return

  const message = messageText.value.trim()
  const files = [...attachedFiles.value]

  // Clear input immediately for better UX
  messageText.value = ''
  attachedFiles.value = []
  resetTextareaHeight()

  isSending.value = true

  try {
    // Issue #690: Use Overseer Agent when enabled
    if (overseerEnabled.value) {
      logger.info('[ChatInput] Sending via Overseer Agent:', message.substring(0, 50))

      // Add user message to chat store directly (appears immediately)
      // The overseer will handle the response via WebSocket
      store.addMessage({
        content: message,
        sender: 'user',
        status: 'sent',
        type: 'message'
      })

      // Submit to overseer for task decomposition
      const success = await submitOverseerQuery(message)
      if (!success) {
        logger.warn('[ChatInput] Overseer submission failed, falling back to normal flow')
        // Fallback: send as normal message
        await controller.sendMessage(message, {
          use_knowledge: useKnowledge.value
        })
      }
    } else {
      // Normal message flow (Issue #249)
      await controller.sendMessage(message, {
        attachments: files.length > 0 ? files.map(f => ({
          id: generateId(),
          name: f.name,
          type: f.type,
          size: f.size,
          data: f // In real implementation, would upload file first
        })) : undefined,
        use_knowledge: useKnowledge.value  // Issue #249: RAG toggle
      })
    }

  } catch (error) {
    logger.error('Failed to send message:', error)
    // Restore message on error
    messageText.value = message
    attachedFiles.value = files
  } finally {
    isSending.value = false
  }
}

const attachFile = () => {
  fileInput.value?.click()
}

const handleFileSelect = async (event: Event) => {
  const target = event.target as HTMLInputElement
  const files = Array.from(target.files || [])

  // Validate files
  const validFiles = files.filter(file => {
    if (file.size > maxFileSize) {
      alert(`File "${file.name}" is too large (max ${formatFileSize(maxFileSize)})`)
      return false
    }
    return true
  })

  // Create upload tracking objects for all files first
  const uploads = validFiles.map(file => {
    const uploadId = generateId()
    const upload: {
      id: string;
      filename: string;
      progress: number;
      status: string;
      current: number;
      total: number;
      file: File;
      fileId?: string;
      uploadId?: string;
      error?: string;
      eta?: number;
    } = {
      id: uploadId,
      filename: file.name,
      progress: 0,
      status: 'Preparing...',
      current: 0,
      total: file.size,
      file: file
    }
    uploadProgress.value.push(upload)
    return { upload, file }
  })

  // Upload all files in parallel - eliminates N+1 sequential uploads
  const results = await Promise.allSettled(
    uploads.map(async ({ upload, file }) => {
      await uploadFile(upload, file)
      return file
    })
  )

  // Process results and track successful uploads
  results.forEach((result, index) => {
    if (result.status === 'fulfilled') {
      attachedFiles.value.push(result.value)
    } else {
      const upload = uploads[index].upload
      upload.error = result.reason instanceof Error ? result.reason.message : 'Upload failed'
      upload.status = 'Failed'
    }
  })

  // Clear input
  target.value = ''
}

const removeFile = (index: number) => {
  attachedFiles.value.splice(index, 1)
}

const clearAllFiles = () => {
  attachedFiles.value = []
}

const toggleVoiceInput = () => {
  if (isVoiceRecording.value) {
    stopVoiceRecording()
  } else {
    startVoiceRecording()
  }
}

const startVoiceRecording = async () => {
  try {
    // Web Speech API implementation would go here
    isVoiceRecording.value = true
    logger.debug('Voice recording started')
  } catch (error) {
    logger.error('Failed to start voice recording:', error)
    alert('Voice recording is not supported in your browser')
  }
}

const stopVoiceRecording = () => {
  isVoiceRecording.value = false
  logger.debug('Voice recording stopped')
}

const toggleEmojiPicker = () => {
  showEmojiPicker.value = !showEmojiPicker.value
}

const insertEmoji = (emoji: typeof commonEmojis[0]) => {
  const textarea = messageInput.value!
  const start = textarea.selectionStart
  const end = textarea.selectionEnd

  const textBefore = messageText.value.slice(0, start)
  const textAfter = messageText.value.slice(end)

  messageText.value = textBefore + emoji.emoji + textAfter

  // Restore cursor position
  nextTick(() => {
    const newPosition = start + emoji.emoji.length
    textarea.setSelectionRange(newPosition, newPosition)
    textarea.focus()
  })

  showEmojiPicker.value = false
}

const useQuickAction = (action: typeof quickActions[0]) => {
  const actionTexts = {
    help: 'Can you help me with ',
    summarize: 'Please summarize our conversation',
    translate: 'Please translate the following text: ',
    explain: 'Can you explain '
  }

  const text = actionTexts[action.id as keyof typeof actionTexts] || ''
  messageText.value = text

  nextTick(() => {
    messageInput.value?.focus()
    const textarea = messageInput.value!
    textarea.setSelectionRange(text.length, text.length)
  })
}

const resetTextareaHeight = () => {
  nextTick(() => {
    if (messageInput.value) {
      messageInput.value.style.height = 'auto'
    }
  })
}

// Icon mapping centralized in @/utils/iconMappings
// Color classes added for visual distinction
const getFileIcon = (type: string): string => {
  const icon = getFileIconByMimeType(type)

  // Add color classes based on MIME type
  const colorMap: Record<string, string> = {
    'fas fa-image': 'text-green-600',
    'fas fa-video': 'text-blue-600',
    'fas fa-music': 'text-purple-600',
    'fas fa-file-pdf': 'text-red-600',
    'fas fa-file-word': 'text-blue-600',
    'fas fa-file-excel': 'text-green-600',
    'fas fa-file-alt': 'text-gray-600'
  }

  const color = colorMap[icon] || 'text-gray-600'
  return `${icon} ${color}`
}

// NOTE: formatFileSize removed - now using shared utility from @/utils/formatHelpers

const generateId = (): string => {
  return Date.now().toString(36) + Math.random().toString(36).substr(2)
}

// Real file upload implementation
const uploadFile = async (upload: any, file: File): Promise<void> => {
  const formData = new FormData()
  formData.append('file', file)

  const startTime = Date.now()
  upload.status = 'Uploading...'

  try {
    await new Promise<string>((resolve, reject) => {
      const xhr = new XMLHttpRequest()

      // Track upload progress
      xhr.upload.addEventListener('progress', (event) => {
        if (event.lengthComputable) {
          upload.current = event.loaded
          upload.total = event.total
          upload.progress = (event.loaded / event.total) * 100

          // Calculate ETA
          const elapsed = Date.now() - startTime
          if (elapsed > 0) {
            const rate = event.loaded / elapsed // bytes per millisecond
            const remaining = (event.total - event.loaded) / rate / 1000 // seconds
            upload.eta = remaining > 1 ? remaining : undefined
          }

          upload.status = `Uploading... ${Math.round(upload.progress)}%`
        }
      })

      // Handle successful completion
      xhr.addEventListener('load', () => {
        if (xhr.status === 200) {
          upload.status = 'Complete'
          upload.progress = 100

          try {
            const response = JSON.parse(xhr.responseText)
            upload.fileId = response.file_info?.file_id
            upload.uploadId = response.upload_id

            // Remove from progress after delay
            setTimeout(() => {
              const index = uploadProgress.value.findIndex(u => u.id === upload.id)
              if (index !== -1) uploadProgress.value.splice(index, 1)
            }, 2000)

            resolve(response.file_info?.file_id || '')
          } catch (e) {
            reject(new Error('Invalid response from server'))
          }
        } else {
          reject(new Error(`Upload failed with status: ${xhr.status}`))
        }
      })

      // Handle errors
      xhr.addEventListener('error', () => {
        reject(new Error('Network error during upload'))
      })

      xhr.addEventListener('abort', () => {
        reject(new Error('Upload cancelled'))
      })

      // Send request
      const sessionId = store.currentSessionId || 'default'
      xhr.open('POST', `/api/conversation-files/conversation/${sessionId}/upload`)
      xhr.send(formData)
    })
  } catch (error) {
    upload.error = error instanceof Error ? error.message : 'Upload failed'
    upload.status = 'Failed'
    upload.progress = 0
    throw error
  }
}

const retryUpload = async (uploadId: string) => {
  const upload = uploadProgress.value.find(u => u.id === uploadId)
  if (!upload || !upload.file) {
    logger.error('Cannot retry upload: Upload or file not found')
    return
  }

  // Reset upload state
  upload.error = undefined
  upload.progress = 0
  upload.current = 0
  upload.status = 'Retrying...'

  try {
    // Use real upload function
    await uploadFile(upload, upload.file)
    // Re-add to attached files if successful
    if (upload.file && !attachedFiles.value.find(f => f.name === upload.file!.name)) {
      attachedFiles.value.push(upload.file)
    }
  } catch (error) {
    upload.error = error instanceof Error ? error.message : 'Retry failed'
    upload.status = 'Failed'
  }
}

const updateTypingIndicator = () => {
  if (typingDebounceTimer.value) {
    clearTimeout(typingDebounceTimer.value)
  }

  if (!isTypingStartTime.value && messageText.value.length > 0) {
    isTypingStartTime.value = Date.now()
  }

  typingDebounceTimer.value = setTimeout(() => {
    isTypingStartTime.value = null
  }, 1000) as unknown as number
}

// Event listeners
const handleClickOutside = (event: Event) => {
  if (showEmojiPicker.value && emojiPicker.value && !emojiPicker.value.contains(event.target as Node)) {
    showEmojiPicker.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)

  // Focus input on mount
  nextTick(() => {
    messageInput.value?.focus()
  })
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>

<style scoped>
/* CRITICAL FIX: Enforce sticky positioning with !important and solid background */
.chat-input-container {
  @apply relative bg-white border-t border-gray-200 p-4;
  position: sticky !important;
  bottom: 0 !important;
  z-index: 10 !important;
  background-color: white !important;
  box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.1);
}

/* Upload Progress */
.upload-progress {
  @apply space-y-3;
}

.upload-item {
  @apply flex items-center gap-3 p-3 bg-blue-50 border border-blue-200 rounded-lg;
}

.upload-info {
  @apply flex-1 min-w-0;
}

.upload-filename {
  @apply font-medium text-blue-900 truncate;
}

.upload-status {
  @apply text-sm text-blue-600;
}

/* Attached Files */
.attached-files {
  @apply border border-gray-200 rounded-lg p-3;
}

.attached-files-header {
  @apply flex items-center justify-between mb-2;
}

.attached-files-list {
  @apply space-y-2;
}

.attached-file-item {
  @apply flex items-center gap-3 p-2 bg-gray-50 rounded-lg;
}

.file-icon {
  @apply w-8 h-8 flex items-center justify-center;
}

.file-info {
  @apply flex-1 min-w-0;
}

.file-name {
  @apply block text-sm font-medium text-gray-900 truncate;
}

.file-size {
  @apply block text-xs text-gray-500;
}

/* Input Wrapper */
.input-wrapper {
  @apply space-y-2;
}

.input-container {
  @apply flex items-end gap-2;
}

.message-input-wrapper {
  @apply flex-1 border border-gray-300 rounded-lg overflow-hidden transition-all duration-200;
  position: relative;
  z-index: 1;
}

.message-input-wrapper.focused {
  @apply border-indigo-500 ring-1 ring-indigo-500;
}

.message-input {
  @apply w-full px-4 py-3 resize-none border-none outline-none min-h-[44px] max-h-[150px];
  line-height: 1.5;
}

.message-input:disabled {
  @apply bg-gray-50 text-gray-500;
}

.input-actions {
  @apply flex items-center gap-1 px-2 py-2 border-t border-gray-200 bg-gray-50;
}

.action-divider {
  @apply w-px h-6 bg-gray-300 mx-2;
  flex-shrink: 0;
}

/* Issue #249: Knowledge Base Toggle Styles */
.knowledge-toggle {
  @apply flex items-center gap-1 px-2 py-1 rounded cursor-pointer transition-all duration-200 text-gray-500;
}

.knowledge-toggle:hover {
  @apply bg-gray-100 text-gray-700;
}

.knowledge-toggle.active {
  @apply bg-indigo-100 text-indigo-600;
}

.knowledge-toggle.active i {
  @apply text-indigo-600;
}

.knowledge-toggle .toggle-label {
  @apply text-xs font-medium;
}

/* Issue #690: Overseer Toggle Styles */
.overseer-toggle {
  @apply flex items-center gap-1 px-2 py-1 rounded cursor-pointer transition-all duration-200 text-gray-500;
}

.overseer-toggle:hover {
  @apply bg-gray-100 text-gray-700;
}

.overseer-toggle.active {
  @apply bg-purple-100 text-purple-600;
}

.overseer-toggle.active i {
  @apply text-purple-600;
}

.overseer-toggle .toggle-label {
  @apply text-xs font-medium;
}

.action-label {
  @apply hidden sm:inline text-xs;
}

.send-button {
  @apply w-12 h-12;
}

.send-button.pulse {
  animation: buttonPulse 2s infinite;
}

@keyframes buttonPulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.05); }
}

.queue-indicator {
  @apply relative;
}

.queue-count {
  @apply absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full w-4 h-4 flex items-center justify-center text-xs font-bold;
}

/* Status Bar */
.input-status-bar {
  @apply flex items-center justify-between text-xs text-gray-500;
}

.status-left {
  @apply flex items-center gap-3;
}

.status-right {
  @apply flex items-center gap-3;
}

.typing-indicator {
  @apply flex items-center gap-1 text-indigo-600;
}

.character-count {
  @apply transition-colors;
}

.character-count.warning {
  @apply text-orange-600 font-medium;
}

.voice-status {
  @apply flex items-center gap-1 text-red-600;
}

.keyboard-hint {
  @apply hidden sm:block;
}

/* Quick Actions */
.quick-actions {
  @apply flex flex-wrap gap-2 pt-3 border-t border-gray-100;
}

/* Emoji Picker */
.emoji-picker {
  @apply absolute bottom-full right-0 mb-2 w-80 bg-white border border-gray-200 rounded-lg shadow-lg z-50;
}

.emoji-header {
  @apply flex items-center justify-between p-3 border-b border-gray-200;
}

.emoji-title {
  @apply font-medium text-gray-900;
}

.emoji-grid {
  @apply grid grid-cols-6 gap-1 p-3 max-h-48 overflow-y-auto;
}

/* Responsive */
@media (max-width: 640px) {
  .input-container {
    @apply items-stretch;
  }

  .send-button {
    @apply w-10 h-auto;
  }

  .quick-actions {
    @apply overflow-x-auto;
    scrollbar-width: none;
  }

  .quick-actions::-webkit-scrollbar {
    display: none;
  }

  .emoji-picker {
    @apply w-full right-0;
  }

  .keyboard-hint {
    @apply hidden;
  }
}

/* Animations */
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.animate-pulse {
  animation: pulse 2s infinite;
}

/* Focus states for accessibility handled by BaseButton */
</style>
