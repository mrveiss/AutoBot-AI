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
        <button
          v-if="upload.error"
          @click="retryUpload(upload.id)"
          class="retry-upload-btn"
        >
          <i class="fas fa-redo"></i>
        </button>
      </div>
    </div>

    <!-- Attached Files Display -->
    <div v-if="attachedFiles.length > 0" class="attached-files mb-4">
      <div class="attached-files-header">
        <h4 class="text-sm font-medium text-gray-700">
          <i class="fas fa-paperclip mr-1"></i>
          {{ attachedFiles.length }} file{{ attachedFiles.length > 1 ? 's' : '' }} attached
        </h4>
        <button @click="clearAllFiles" class="text-sm text-red-600 hover:text-red-800">
          Clear all
        </button>
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
          <button
            @click="removeFile(index)"
            class="remove-file-btn"
            title="Remove file"
          >
            <i class="fas fa-times"></i>
          </button>
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
          <textarea
            ref="messageInput"
            v-model="messageText"
            :placeholder="inputPlaceholder"
            class="message-input"
            :disabled="isDisabled"
            @keydown="handleKeydown"
            @focus="isInputFocused = true"
            @blur="isInputFocused = false"
            @input="handleInput"
            rows="1"
          ></textarea>

          <!-- Input Actions -->
          <div class="input-actions">
            <!-- File Attach Button -->
            <button
              @click="attachFile"
              class="action-btn"
              title="Attach file"
              :disabled="isDisabled"
            >
              <i class="fas fa-paperclip"></i>
            </button>

            <!-- Voice Input Button -->
            <button
              @click="toggleVoiceInput"
              class="action-btn"
              :class="{ 'active': isVoiceRecording }"
              title="Voice input"
              :disabled="isDisabled"
            >
              <i :class="isVoiceRecording ? 'fas fa-stop' : 'fas fa-microphone'"></i>
            </button>

            <!-- Emoji Button -->
            <button
              @click="toggleEmojiPicker"
              class="action-btn"
              title="Add emoji"
              :disabled="isDisabled"
            >
              <i class="fas fa-smile"></i>
            </button>

            <!-- Vertical Divider -->
            <div class="action-divider"></div>

            <!-- Quick Actions -->
            <button
              v-for="action in quickActions"
              :key="action.id"
              @click="useQuickAction(action)"
              class="action-btn quick-action-btn"
              :title="action.description"
              :disabled="isDisabled"
            >
              <i :class="action.icon"></i>
              <span class="action-label">{{ action.label }}</span>
            </button>
          </div>
        </div>

        <!-- Send Button -->
        <button
          @click="sendMessage"
          class="send-button"
          :disabled="!canSend"
          :class="{ 'sending': isSending, 'pulse': messageQueueLength > 0 }"
          :title="isSending ? 'Sending...' : canSend ? 'Send message (Enter)' : 'Enter a message to send'"
        >
          <LoadingSpinner
            v-if="isSending"
            variant="dots"
            size="xs"
            color="white"
          />
          <div v-else-if="messageQueueLength > 0" class="queue-indicator">
            <i class="fas fa-paper-plane"></i>
            <span class="queue-count">{{ messageQueueLength }}</span>
          </div>
          <i v-else class="fas fa-paper-plane"></i>
        </button>
      </div>

      <!-- Input Status Bar -->
      <div class="input-status-bar">
        <div class="status-left">
          <span v-if="isTypingIndicatorVisible" class="typing-indicator">
            <i class="fas fa-keyboard"></i>
            Typing...
          </span>
          <span v-if="characterCount > 0" class="character-count" :class="{ 'warning': isNearLimit }">
            {{ characterCount }}/{{ maxCharacters }}
          </span>
        </div>

        <div class="status-right">
          <span v-if="isVoiceRecording" class="voice-status">
            <i class="fas fa-circle text-red-500 animate-pulse"></i>
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
        <button @click="showEmojiPicker = false" class="close-emoji-btn">
          <i class="fas fa-times"></i>
        </button>
      </div>
      <div class="emoji-grid">
        <button
          v-for="emoji in commonEmojis"
          :key="emoji.code"
          @click="insertEmoji(emoji)"
          class="emoji-btn"
          :title="emoji.name"
        >
          {{ emoji.emoji }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import { useChatStore } from '@/stores/useChatStore'
import { useChatController } from '@/models/controllers'
import globalWebSocketService from '@/services/GlobalWebSocketService'
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue'
import ProgressBar from '@/components/ui/ProgressBar.vue'

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
const uploadProgress = ref<Array<{
  id: string
  filename: string
  progress: number
  status: string
  current: number
  total: number
  eta?: number
  error?: string
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
    // Send message with attachments
    await controller.sendMessage(message, {
      attachments: files.length > 0 ? files.map(f => ({
        id: generateId(),
        name: f.name,
        type: f.type,
        size: f.size,
        data: f // In real implementation, would upload file first
      })) : undefined
    })

  } catch (error) {
    console.error('Failed to send message:', error)
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

  // Process files with upload progress
  for (const file of validFiles) {
    const uploadId = generateId()
    const upload = {
      id: uploadId,
      filename: file.name,
      progress: 0,
      status: 'Preparing...',
      current: 0,
      total: file.size
    }

    uploadProgress.value.push(upload)

    try {
      // Simulate upload progress (replace with actual upload logic)
      await simulateUpload(upload, file)
      attachedFiles.value.push(file)
    } catch (error) {
      upload.error = error instanceof Error ? error.message : 'Upload failed'
      upload.status = 'Failed'
    }
  }

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
    console.log('Voice recording started')
  } catch (error) {
    console.error('Failed to start voice recording:', error)
    alert('Voice recording is not supported in your browser')
  }
}

const stopVoiceRecording = () => {
  isVoiceRecording.value = false
  console.log('Voice recording stopped')
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

// Utility functions
const getFileIcon = (type: string): string => {
  if (type.startsWith('image/')) return 'fas fa-image text-green-600'
  if (type.startsWith('video/')) return 'fas fa-video text-blue-600'
  if (type.startsWith('audio/')) return 'fas fa-music text-purple-600'
  if (type.includes('pdf')) return 'fas fa-file-pdf text-red-600'
  if (type.includes('word')) return 'fas fa-file-word text-blue-600'
  if (type.includes('excel')) return 'fas fa-file-excel text-green-600'
  if (type.includes('text')) return 'fas fa-file-alt text-gray-600'
  return 'fas fa-file text-gray-600'
}

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 Bytes'
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

const generateId = (): string => {
  return Date.now().toString(36) + Math.random().toString(36).substr(2)
}

// Enhanced UX methods
const simulateUpload = async (upload: any, file: File): Promise<void> => {
  const chunkSize = Math.max(file.size / 10, 1024) // 10 chunks minimum
  let uploaded = 0
  const startTime = Date.now()

  upload.status = 'Uploading...'

  while (uploaded < file.size) {
    await new Promise(resolve => setTimeout(resolve, 100)) // Simulate network delay

    uploaded = Math.min(uploaded + chunkSize, file.size)
    upload.current = uploaded
    upload.progress = (uploaded / file.size) * 100

    // Calculate ETA
    const elapsed = Date.now() - startTime
    const rate = uploaded / elapsed
    const remaining = (file.size - uploaded) / rate / 1000
    upload.eta = remaining > 1 ? remaining : undefined

    // Update status
    if (upload.progress >= 100) {
      upload.status = 'Processing...'
      await new Promise(resolve => setTimeout(resolve, 500))
      upload.status = 'Complete'

      // Remove from progress after delay
      setTimeout(() => {
        const index = uploadProgress.value.findIndex(u => u.id === upload.id)
        if (index !== -1) uploadProgress.value.splice(index, 1)
      }, 2000)
    }
  }
}

const retryUpload = async (uploadId: string) => {
  const upload = uploadProgress.value.find(u => u.id === uploadId)
  if (!upload) return

  upload.error = undefined
  upload.progress = 0
  upload.current = 0
  upload.status = 'Retrying...'

  // Find corresponding file and retry upload
  // This is a simplified retry - in production, you'd need to track the original file
  await new Promise(resolve => setTimeout(resolve, 1000))
  upload.status = 'Complete'
  upload.progress = 100

  setTimeout(() => {
    const index = uploadProgress.value.findIndex(u => u.id === uploadId)
    if (index !== -1) uploadProgress.value.splice(index, 1)
  }, 2000)
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

.retry-upload-btn {
  @apply w-8 h-8 flex items-center justify-center text-red-600 hover:text-red-800 hover:bg-red-100 rounded transition-colors;
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

.remove-file-btn {
  @apply w-6 h-6 flex items-center justify-center text-gray-400 hover:text-red-600 rounded transition-colors;
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

.action-btn {
  @apply flex items-center justify-center text-gray-500 hover:text-gray-700 rounded transition-colors;
  min-width: 2rem;
  min-height: 2rem;
}

.action-btn:not(.quick-action-btn) {
  @apply w-8 h-8;
}

.action-btn.active {
  @apply text-red-600 bg-red-50;
}

.action-btn:disabled {
  @apply opacity-50 cursor-not-allowed;
}

.action-divider {
  @apply w-px h-6 bg-gray-300 mx-2;
  flex-shrink: 0;
}

.quick-action-btn {
  @apply gap-1.5 px-2 py-1 text-sm;
  white-space: nowrap;
}

.action-label {
  @apply hidden sm:inline text-xs;
}

.send-button {
  @apply w-12 h-12 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 flex items-center justify-center;
}

.send-button.sending {
  @apply bg-indigo-500;
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

.quick-action-btn {
  @apply flex items-center gap-2 px-3 py-1.5 text-sm text-gray-600 bg-gray-100 rounded-full hover:bg-gray-200 transition-colors;
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

.close-emoji-btn {
  @apply w-6 h-6 flex items-center justify-center text-gray-400 hover:text-gray-600 rounded;
}

.emoji-grid {
  @apply grid grid-cols-6 gap-1 p-3 max-h-48 overflow-y-auto;
}

.emoji-btn {
  @apply w-10 h-10 flex items-center justify-center text-xl hover:bg-gray-100 rounded transition-colors;
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

/* Focus states for accessibility */
.action-btn:focus,
.quick-action-btn:focus,
.emoji-btn:focus {
  @apply outline-none ring-2 ring-indigo-500 ring-offset-2;
}

.send-button:focus {
  @apply outline-none ring-2 ring-indigo-500 ring-offset-2;
}
</style>