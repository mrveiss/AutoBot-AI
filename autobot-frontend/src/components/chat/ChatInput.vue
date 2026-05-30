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
          variant="error"
          size="xs"
          @click="retryUpload(upload.id)"
          class="retry-upload-btn"
          :aria-label="$t('chat.input.retryUpload')"
        >
          <Icon name="redo" />
        </BaseButton>
      </div>
    </div>

    <!-- Attached Files Display -->
    <div v-if="attachedFiles.length > 0" class="attached-files mb-4">
      <div class="attached-files-header">
        <h4 class="text-sm font-medium text-autobot-text-secondary">
          <Icon name="paperclip" class="me-1" />
          {{ $t('chat.input.filesAttached', { count: attachedFiles.length }) }}
        </h4>
        <BaseButton variant="ghost" size="sm" @click="clearAllFiles" class="text-red-600 hover:text-red-800">
          {{ $t('chat.input.clearAll') }}
        </BaseButton>
      </div>

      <div class="attached-files-list">
        <div
          v-for="(file, index) in attachedFiles"
          :key="index"
          class="attached-file-item"
        >
          <div class="file-icon">
            <Icon :name="getFileIcon(file.type)" />
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
            :aria-label="$t('chat.input.removeFile')"
          >
            <Icon name="times" />
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
          <label for="chat-message-input" class="sr-only">{{ $t('chat.input.chatMessage') }}</label>
          <textarea
            id="chat-message-input"
            ref="messageInput"
            v-model="messageText"
            :placeholder="inputPlaceholder"
            class="message-input"
            :disabled="isDisabled"
            :aria-label="$t('chat.input.ariaLabel')"
            aria-describedby="chat-input-help"
            @keydown="handleKeydown"
            @focus="isInputFocused = true"
            @blur="isInputFocused = false"
            @input="handleInput"
            rows="1"
          ></textarea>
          <span id="chat-input-help" class="sr-only">
            {{ $t('chat.input.helpText') }}
          </span>

          <!-- Input Actions -->
          <div class="input-actions">
            <!-- Issue #249: Knowledge Base Toggle -->
            <label class="knowledge-toggle" :class="{ 'active': useKnowledge }" :title="$t('chat.input.useKnowledge')">
              <input
                type="checkbox"
                v-model="useKnowledge"
                class="knowledge-checkbox sr-only"
                :disabled="isDisabled"
              />
              <Icon name="brain" />
              <span class="toggle-label">KB</span>
            </label>

            <!-- Issue #690: Overseer Mode Toggle -->
            <label
              class="overseer-toggle"
              :class="{ 'active': overseerEnabled }"
              :title="$t('chat.input.overseerMode')"
              @click.prevent="toggleOverseer"
            >
              <Icon name="sitemap" />
              <span class="toggle-label">{{ $t('chat.input.overseerLabel') }}</span>
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
              :aria-label="$t('chat.input.attachFile')"
            >
              <Icon name="paperclip" />
            </BaseButton>

            <!-- Vision Analysis Button (#1242) -->
            <BaseButton
              variant="ghost"
              size="xs"
              @click="showVisionModal = true"
              class="action-btn"
              :disabled="isDisabled"
              :aria-label="$t('chat.input.analyzeImage')"
            >
              <Icon name="eye" />
            </BaseButton>

            <!-- Preset Management Button (#8596) -->
            <BaseButton
              variant="ghost"
              size="xs"
              @click="showPresetsModal = true"
              class="action-btn"
              :disabled="isDisabled"
              :aria-label="$t('chat.input.managePresets')"
            >
              <Icon name="bookmark" />
            </BaseButton>

            <!-- Voice Input Button -->
            <BaseButton
              variant="ghost"
              size="xs"
              @click="toggleVoiceInput"
              class="action-btn"
              :class="{ 'active': isVoiceRecording }"
              :disabled="isDisabled"
              :aria-label="$t('chat.input.voiceInput')"
            >
              <Icon :name="isVoiceRecording ? 'stop' : 'microphone'" />
            </BaseButton>

            <!-- GH#9015: Image Generation Button -->
            <BaseButton
              variant="ghost"
              size="xs"
              @click="showImageGenModal = true"
              class="action-btn"
              :disabled="isDisabled || imageGenerating"
              :aria-label="$t('chat.input.generateImage', 'Generate image')"
              :title="$t('chat.input.generateImage', 'Generate image')"
            >
              <Icon :name="imageGenerating ? 'spinner' : 'image'" />
            </BaseButton>

            <!-- Emoji Button -->
            <BaseButton
              variant="ghost"
              size="xs"
              @click="toggleEmojiPicker"
              class="action-btn"
              :disabled="isDisabled"
              :aria-label="$t('chat.input.addEmoji')"
            >
              <Icon name="user" />
            </BaseButton>

            <!-- Vertical Divider + Quick Actions Toggle (#1569) -->
            <div class="action-divider"></div>
            <BaseButton
              variant="ghost"
              size="sm"
              class="action-btn"
              :aria-label="showQuickActions ? 'Hide quick actions' : 'Show quick actions'"
              @click="showQuickActions = !showQuickActions"
            >
              <Icon name="ellipsis-h" />
            </BaseButton>

            <!-- Quick Actions (#1569: togglable) -->
            <template v-if="showQuickActions">
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
                <Icon :name="action.icon" />
                <span class="action-label">{{ action.label }}</span>
              </BaseButton>
            </template>
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
          :aria-label="isSending ? $t('chat.input.sending') : canSend ? $t('chat.input.sendMessage') : $t('chat.input.enterMessage')"
        >
          <div v-if="!isSending && messageQueueLength > 0" class="queue-indicator">
            <Icon name="paper-plane" />
            <span class="queue-count">{{ messageQueueLength }}</span>
          </div>
          <Icon name="paper-plane" v-else-if="!isSending"  aria-hidden="true" />
        </BaseButton>
      </div>

      <!-- Input Status Bar -->
      <div class="input-status-bar">
        <div class="status-left">
          <span v-if="isTypingIndicatorVisible" class="typing-indicator">
            <Icon name="keyboard" />
            {{ $t('chat.input.typing') }}
          </span>
          <span v-if="characterCount > 0" class="character-count" :class="{ 'warning': isNearLimit }">
            {{ characterCount }}/{{ maxCharacters }}
          </span>
        </div>

        <div class="status-right">
          <span v-if="isVoiceRecording" class="voice-status">
            <Icon name="circle" class="text-red-500 animate-pulse" />
            {{ $t('chat.input.recording') }}
          </span>
          <span class="keyboard-hint">{{ $t('chat.input.keyboardHint') }}</span>
        </div>
      </div>
    </div>

    <!-- Emoji Picker -->
    <div v-if="showEmojiPicker" class="emoji-picker" ref="emojiPicker">
      <div class="emoji-header">
        <span class="emoji-title">{{ $t('chat.input.addEmoji') }}</span>
        <BaseButton variant="ghost" size="xs" @click="showEmojiPicker = false" class="close-emoji-btn" :aria-label="$t('chat.input.closeEmojiPicker')">
          <Icon name="times" />
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

    <!-- Issue #1328: Translation Shortcut Panel -->
    <TranslationShortcutPanel
      v-if="showTranslatePanel"
      :initial-text="messageText"
      @close="showTranslatePanel = false"
      @translation-result="handleTranslationResult"
    />

    <!-- Vision Analysis Modal (#1242) -->
    <VisionAnalysisModal
      v-if="showVisionModal"
      @close="showVisionModal = false"
      @send-to-chat="handleVisionSendToChat"
    />

    <!-- GH#4449: Slash command preset autocomplete dropdown -->
    <SlashCommandDropdown
      :show="showSlashDropdown"
      :suggestions="slashSuggestions"
      :selected-index="slashSelectedIndex"
      :anchor-el="messageInput ?? null"
      @select="applySlashPreset"
      @update:selected-index="setSlashIndex"
    />

    <!-- Preset Management Modal (#8596) -->
    <PresetManagementModal
      v-model="showPresetsModal"
      @close="showPresetsModal = false"
    />

    <!-- GH#9015: Image Generation Modal -->
    <Teleport to="body">
      <div
        v-if="showImageGenModal"
        class="image-gen-overlay"
        @click.self="showImageGenModal = false"
        role="dialog"
        aria-modal="true"
        aria-label="Generate image"
      >
        <div class="image-gen-dialog">
          <h3 class="image-gen-title">
            <Icon name="image" />
            {{ $t('chat.input.generateImageTitle', 'Generate Image') }}
          </h3>
          <label class="image-gen-label" for="image-gen-prompt">
            {{ $t('chat.input.imagePromptLabel', 'Describe the image') }}
          </label>
          <textarea
            id="image-gen-prompt"
            v-model="imagePrompt"
            class="image-gen-prompt"
            :placeholder="$t('chat.input.imagePromptPlaceholder', 'A futuristic city at sunset with neon lights...')"
            rows="3"
            autofocus
            @keydown.ctrl.enter="submitImageGeneration"
          />
          <div class="image-gen-provider">
            <label class="image-gen-label">{{ $t('chat.input.imageProvider', 'Provider') }}</label>
            <div class="provider-options">
              <label v-for="p in (['dalle', 'flux', 'stable_diffusion'] as const)" :key="p" class="provider-option">
                <input type="radio" :value="p" v-model="imageProvider" />
                <span>{{ { dalle: 'DALL·E 3', flux: 'Flux', stable_diffusion: 'Stable Diffusion' }[p] }}</span>
              </label>
            </div>
          </div>
          <div class="image-gen-actions">
            <button class="image-gen-cancel" @click="showImageGenModal = false">
              {{ $t('common.cancel', 'Cancel') }}
            </button>
            <button
              class="image-gen-submit"
              @click="submitImageGeneration"
              :disabled="!imagePrompt.trim() || imageGenerating"
            >
              <Icon :name="imageGenerating ? 'spinner' : 'magic'" />
              {{ imageGenerating ? $t('chat.input.generating', 'Generating…') : $t('chat.input.generate', 'Generate') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, nextTick, onMounted, onUnmounted, inject, watch, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/stores/useChatStore'
import { useChatController } from '@/models/controllers'
import ProgressBar from '@/components/ui/ProgressBar.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import VisionAnalysisModal from './VisionAnalysisModal.vue'
import PresetManagementModal from './PresetManagementModal.vue'
import TranslationShortcutPanel from './TranslationShortcutPanel.vue'
import SlashCommandDropdown from './SlashCommandDropdown.vue'
import { formatFileSize } from '@/utils/formatHelpers'
import { getFileIconByMimeType } from '@/utils/iconMappings'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'
import type { MultiModalResponse } from '@/utils/VisionMultimodalApiClient'
import { useVoiceOutput } from '@/composables/useVoiceOutput'
import { useSlashCommands } from '@/composables/useSlashCommands'
import type { SlashCommandPreset } from '@/types/api'
import { useImageGeneration } from '@/composables/useImageGeneration'

const { t } = useI18n()
const logger = createLogger('ChatInput')
// Issue #1146: unlock AudioContext on first user gesture so TTS can play even
// when voice output was re-enabled from a previous session via localStorage.
const { unlockAudio } = useVoiceOutput()

// Issue #690: Inject overseer state from ChatInterface
const overseerEnabled = inject<Ref<boolean>>('overseerEnabled', ref(false))
const toggleOverseer = inject<() => void>('toggleOverseer', () => {})
const submitOverseerQuery = inject<(query: string) => Promise<boolean>>('submitOverseerQuery', async () => false)

const store = useChatStore()
const controller = useChatController()

const messageText = ref('')

// GH#4449: Slash command preset autocomplete
const {
  suggestions: slashSuggestions,
  showDropdown: showSlashDropdown,
  selectedIndex: slashSelectedIndex,
  onInput: onSlashInput,
  moveUp: slashMoveUp,
  moveDown: slashMoveDown,
  applyPreset,
  confirmSelection,
  setSelectedIndex,
  close: closeSlashDropdown,
  fetchPresets,
} = useSlashCommands(messageText)

const applySlashPreset = (preset: SlashCommandPreset) => {
  messageText.value = applyPreset(preset)
  closeSlashDropdown()
}

const setSlashIndex = (idx: number) => {
  setSelectedIndex(idx)
}

// Refs
const messageInput = ref<HTMLTextAreaElement>()
const fileInput = ref<HTMLInputElement>()
const emojiPicker = ref<HTMLElement>()

// State
const attachedFiles = ref<File[]>([])
const isInputFocused = ref(false)
const isVoiceRecording = ref(false)
const isSending = ref(false)
const showEmojiPicker = ref(false)
const showVisionModal = ref(false)
const showTranslatePanel = ref(false)
const showPresetsModal = ref(false)

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

// GH#9015: Image generation
const { generating: imageGenerating, generateImage } = useImageGeneration()
const showImageGenModal = ref(false)
const imagePrompt = ref('')
const imageProvider = ref<'dalle' | 'flux' | 'stable_diffusion'>('dalle')

const submitImageGeneration = async () => {
  if (!imagePrompt.value.trim()) return
  showImageGenModal.value = false
  const result = await generateImage({ prompt: imagePrompt.value.trim(), provider: imageProvider.value })
  imagePrompt.value = ''
  if (result) {
    store.addMessage({
      content: result.success ? '' : (result.error ?? 'Image generation failed'),
      sender: 'assistant',
      status: 'sent',
      type: 'image',
      metadata: result.success
        ? {
            display_type: 'image',
            image_payload: {
              images: result.images,
              provider: result.provider,
              model: result.model,
              prompt: result.prompt,
              size: result.size,
            },
          }
        : {},
    })
  }
}

// Issue #1569: Quick actions visibility toggle with localStorage persistence
const showQuickActions = ref(localStorage.getItem('autobot_showQuickActions') !== 'false')
watch(showQuickActions, (val) => localStorage.setItem('autobot_showQuickActions', String(val)))

// Quick actions
const quickActions = computed(() => [
  { id: 'help', label: t('chat.input.help'), icon: 'question-circle', description: t('chat.input.helpDesc') },
  { id: 'summarize', label: t('chat.input.summarize'), icon: 'compress', description: t('chat.input.summarizeDesc') },
  { id: 'translate', label: t('agent.translate'), icon: 'language', description: t('chat.input.translateDesc') },
  { id: 'explain', label: t('chat.input.explain'), icon: 'lightbulb', description: t('chat.input.explainDesc') },
])

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
  if (isVoiceRecording.value) return t('voice.listening')
  if (isSending.value) return t('chat.input.sendingMessage')
  if (store.isTyping) return t('chat.input.aiResponding')
  return t('chat.input.typeMessage')
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
  // GH#4449: Slash command dropdown keyboard navigation
  if (showSlashDropdown.value) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      slashMoveDown()
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      slashMoveUp()
      return
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      closeSlashDropdown()
      return
    }
    if (event.key === 'Tab' || (event.key === 'Enter' && !event.shiftKey)) {
      const preset = confirmSelection()
      if (preset) {
        event.preventDefault()
        messageText.value = applyPreset(preset)
        closeSlashDropdown()
        return
      }
    }
  }

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

  // GH#4449: slash command autocomplete
  onSlashInput()
}

const sendMessage = async () => {
  if (!canSend.value) return

  // Issue #1146: ensure AudioContext is unlocked from this user-gesture so TTS
  // can play even if voice output was enabled from localStorage (no prior click).
  unlockAudio()

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

// Module-level recognition instance (not reactive — just internal state)
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let _recognition: any = null

const startVoiceRecording = async () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const w = window as any
  const SpeechRecognitionCtor = w.SpeechRecognition ?? w.webkitSpeechRecognition

  if (!SpeechRecognitionCtor) {
    // Browser doesn't support Web Speech API — still trigger mic permission prompt
    // so the user sees the browser dialog rather than a silent failure.
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      stream.getTracks().forEach((t: MediaStreamTrack) => t.stop())
    } catch (err) {
      logger.error('Microphone access denied:', err)
    }
    alert('Voice input requires Chrome, Edge, or Safari 15+. Transcription is not available in this browser.')
    return
  }

  _recognition = new SpeechRecognitionCtor()
  _recognition.continuous = false
  _recognition.interimResults = true
  _recognition.lang = 'en-US'

  _recognition.onstart = () => {
    isVoiceRecording.value = true
    logger.debug('Voice recognition started')
  }

  _recognition.onresult = (event: any) => {
    const transcript = Array.from(event.results as any[])
      .map((r: any) => r[0].transcript as string)
      .join('')
    messageText.value = transcript
  }

  _recognition.onend = () => {
    isVoiceRecording.value = false
    _recognition = null
    logger.debug('Voice recognition ended')
  }

  _recognition.onerror = (event: any) => {
    logger.error('Voice recognition error:', event.error)
    isVoiceRecording.value = false
    _recognition = null
    if (event.error === 'not-allowed') {
      alert('Microphone access was denied. Please allow microphone access in your browser settings.')
    }
  }

  _recognition.start()
}

const stopVoiceRecording = () => {
  if (_recognition) {
    _recognition.stop()
  }
  isVoiceRecording.value = false
  logger.debug('Voice recording stopped')
}

const toggleEmojiPicker = () => {
  showEmojiPicker.value = !showEmojiPicker.value
}

// Issue #1242: Vision analysis modal emit
const emit = defineEmits<{
  (e: 'vision-send-to-chat', payload: {
    filename: string
    intent: string
    question?: string
    result: MultiModalResponse
  }): void
}>()

const handleVisionSendToChat = (payload: {
  filename: string
  intent: string
  question?: string
  result: MultiModalResponse
}) => {
  showVisionModal.value = false
  emit('vision-send-to-chat', payload)
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

const useQuickAction = (action: { id: string; label: string; icon: string; description: string }) => {
  // Issue #1328: Translate opens the translation panel
  if (action.id === 'translate') {
    showTranslatePanel.value = !showTranslatePanel.value
    return
  }

  const actionTexts: Record<string, string> = {
    help: 'Can you help me with ',
    summarize: 'Please summarize our conversation',
    explain: 'Can you explain ',
  }

  const text = actionTexts[action.id] || ''
  messageText.value = text

  nextTick(() => {
    messageInput.value?.focus()
    const textarea = messageInput.value!
    textarea.setSelectionRange(text.length, text.length)
  })
}

// Issue #1328: Handle translation result — display in chat
const handleTranslationResult = (payload: {
  originalText: string
  translatedText: string
  targetLanguage: string
}) => {
  showTranslatePanel.value = false
  store.addMessage({
    content: `**${payload.targetLanguage}:**\n${payload.translatedText}`,
    sender: 'assistant',
    status: 'sent',
    type: 'message',
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
    'image': 'text-green-600',
    'video': 'text-blue-600',
    'music': 'text-purple-600',
    'file-pdf': 'text-red-600',
    'file-word': 'text-blue-600',
    'file-excel': 'text-green-600',
    'file-alt': 'text-autobot-text-secondary'
  }

  const color = colorMap[icon] || 'text-autobot-text-secondary'
  return `${icon} ${color}`
}

// NOTE: formatFileSize removed - now using shared utility from @/utils/formatHelpers

const generateId = (): string => {
  return crypto.randomUUID()
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
      xhr.open('POST', `${getApiBase()}/conversation-files/conversation/${sessionId}/upload`)
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

  // GH#4449: preload presets for instant autocomplete
  fetchPresets()
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>

<style scoped>
@reference "../../assets/tailwind.css";
/* Pinned as a shrink-0 flex sibling of the messages scroll container */
.chat-input-container {
  @apply relative bg-autobot-bg-card border-t border-autobot-border p-4;
  background-color: var(--autobot-bg-card, white);
  box-shadow: var(--shadow-sm);
}

/* Upload Progress */
.upload-progress {
  @apply space-y-3 max-h-48 overflow-y-auto;
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
  @apply border border-autobot-border rounded-lg p-3;
}

.attached-files-header {
  @apply flex items-center justify-between mb-2;
}

.attached-files-list {
  @apply space-y-2 max-h-48 overflow-y-auto;
}

.attached-file-item {
  @apply flex items-center gap-3 p-2 bg-autobot-bg-tertiary rounded-lg;
}

.file-icon {
  @apply w-8 h-8 flex items-center justify-center;
}

.file-info {
  @apply flex-1 min-w-0;
}

.file-name {
  @apply block text-sm font-medium text-autobot-text-primary truncate;
}

.file-size {
  @apply block text-xs text-autobot-text-muted;
}

/* Input Wrapper */
.input-wrapper {
  @apply space-y-2;
}

.input-container {
  @apply flex items-end gap-2;
}

.message-input-wrapper {
  @apply flex-1 border border-autobot-border rounded-lg overflow-hidden transition-all duration-200;
  position: relative;
  z-index: 1;
}

.message-input-wrapper.focused {
  @apply border-autobot-primary ring-1 ring-autobot-primary;
}

.message-input {
  @apply w-full px-4 py-3 resize-none border-none outline-hidden min-h-[44px] max-h-[150px];
  line-height: 1.5;
}

.message-input:disabled {
  @apply bg-autobot-bg-tertiary text-autobot-text-muted;
}

.input-actions {
  @apply flex items-center gap-1 px-2 py-2 border-t border-autobot-border bg-autobot-bg-tertiary;
}

.action-divider {
  @apply w-px h-6 bg-autobot-border mx-2;
  flex-shrink: 0;
}

/* Issue #249: Knowledge Base Toggle Styles */
.knowledge-toggle {
  @apply flex items-center gap-1 px-2 py-1 rounded cursor-pointer transition-all duration-200 text-autobot-text-muted;
}

.knowledge-toggle:hover {
  @apply bg-autobot-bg-tertiary text-autobot-text-secondary;
}

.knowledge-toggle.active {
  @apply bg-autobot-bg-tertiary text-autobot-primary;
}

.knowledge-toggle.active i {
  @apply text-autobot-primary;
}

.knowledge-toggle .toggle-label {
  @apply text-xs font-medium;
}

/* Issue #690: Overseer Toggle Styles */
.overseer-toggle {
  @apply flex items-center gap-1 px-2 py-1 rounded cursor-pointer transition-all duration-200 text-autobot-text-muted;
}

.overseer-toggle:hover {
  @apply bg-autobot-bg-tertiary text-autobot-text-secondary;
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
  @apply flex items-center justify-between text-xs text-autobot-text-muted;
}

.status-left {
  @apply flex items-center gap-3;
}

.status-right {
  @apply flex items-center gap-3;
}

.typing-indicator {
  @apply flex items-center gap-1 text-autobot-primary;
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
  @apply flex flex-wrap gap-2 pt-3 border-t border-autobot-border;
}

/* Emoji Picker */
.emoji-picker {
  @apply absolute bottom-full right-0 mb-2 w-80 bg-autobot-bg-card border border-autobot-border rounded-lg shadow-lg z-50;
}

.emoji-header {
  @apply flex items-center justify-between p-3 border-b border-autobot-border;
}

.emoji-title {
  @apply font-medium text-autobot-text-primary;
}

.emoji-grid {
  @apply grid grid-cols-6 gap-1 p-3 max-h-48 overflow-y-auto;
}

/* Responsive (#1804) */
@media (max-width: 640px) {
  .input-container {
    @apply items-stretch;
  }

  .send-button {
    /* 44px minimum touch target on mobile */
    min-width: 44px;
    min-height: 44px;
    @apply w-11 h-auto;
  }

  /* Horizontally scroll the action bar on mobile to prevent wrapping */
  .input-actions {
    overflow-x: auto;
    flex-wrap: nowrap;
    scrollbar-width: none;
    -webkit-overflow-scrolling: touch;
  }

  .input-actions::-webkit-scrollbar {
    display: none;
  }

  /* 44px tap targets for action buttons on mobile */
  .knowledge-toggle,
  .overseer-toggle {
    min-height: 44px;
    min-width: 44px;
    @apply px-3;
  }

  .quick-actions {
    @apply overflow-x-auto;
    scrollbar-width: none;
  }

  .quick-actions::-webkit-scrollbar {
    display: none;
  }

  /* Limit status bar on mobile */
  .input-status-bar {
    @apply hidden;
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

/* GH#9015: Image generation modal */
.image-gen-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
}

.image-gen-dialog {
  background: var(--color-surface, #fff);
  border-radius: 0.75rem;
  padding: 1.5rem;
  width: 100%;
  max-width: 480px;
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.2);
}

.image-gen-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text, #111827);
  margin: 0;
}

.image-gen-label {
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--color-text-muted, #6b7280);
}

.image-gen-prompt {
  width: 100%;
  padding: 0.625rem 0.75rem;
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 0.5rem;
  font-size: 0.875rem;
  resize: none;
  font-family: inherit;
  color: var(--color-text, #111827);
  background: var(--color-surface, #fff);
}

.image-gen-prompt:focus {
  outline: 2px solid var(--color-primary, #3b82f6);
  outline-offset: 1px;
}

.provider-options {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  margin-top: 0.25rem;
}

.provider-option {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.8125rem;
  cursor: pointer;
  color: var(--color-text, #111827);
}

.image-gen-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 0.25rem;
}

.image-gen-cancel {
  padding: 0.5rem 1rem;
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 0.5rem;
  background: transparent;
  font-size: 0.875rem;
  cursor: pointer;
  color: var(--color-text-muted, #6b7280);
}

.image-gen-submit {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 1.25rem;
  background: var(--color-primary, #3b82f6);
  color: white;
  border: none;
  border-radius: 0.5rem;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
}

.image-gen-submit:hover:not(:disabled) {
  background: var(--color-primary-dark, #2563eb);
}

.image-gen-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
