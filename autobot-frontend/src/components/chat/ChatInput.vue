<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ChatInput -- the chat composer (#18243). A thin orchestrator: it owns the draft text and the open state of its
  panels, and composes the parts and composables that hold the behaviour: uploads (`useComposerUploads`,
  ChatComposerUploads), the text box and slash commands (`useComposerInput`, SlashCommandDropdown), send and the
  Overseer route (`useComposerSend`), dictation (`useComposerVoice`), the option chips (ChatComposerToggles), the
  icon row (ChatComposerActions), the image dialog and the status bar. Layout and tokens follow the Chat mockup.
-->
<template>
  <div class="relative border-t border-[var(--aui-color-border)] bg-[var(--aui-color-surface)] px-4 py-3">
    <div
      class="flex flex-col gap-2 rounded-[var(--aui-radius-lg)] border bg-[var(--aui-color-surface)] p-3 transition-colors"
      :class="isInputFocused ? 'border-[var(--aui-color-border-strong)] ring-1 ring-[var(--aui-color-focus-ring)]' : 'border-[var(--aui-color-border)]'"
    >
      <label for="chat-message-input" class="sr-only">{{ $t('chat.input.chatMessage') }}</label>
      <textarea
        id="chat-message-input"
        ref="messageInput"
        v-model="messageText"
        :placeholder="inputPlaceholder"
        class="max-h-[9.5rem] min-h-11 w-full resize-none border-0 bg-transparent p-0 text-base leading-normal text-[var(--aui-color-text)] outline-hidden disabled:text-[var(--aui-color-text-muted)]"
        :disabled="isDisabled"
        :aria-label="$t('chat.input.ariaLabel')"
        aria-describedby="chat-input-help"
        rows="1"
        @keydown="handleKeydown"
        @focus="isInputFocused = true"
        @blur="isInputFocused = false"
        @input="handleInput"
      ></textarea>
      <span id="chat-input-help" class="sr-only">{{ $t('chat.input.helpText') }}</span>

      <ChatComposerUploads
        :uploads="uploadProgress"
        :files="attachedFiles"
        :is-cancellable="isCancellable"
        @cancel="cancelUpload"
        @retry="retryUpload"
        @remove="removeFile"
        @clear-all="clearAllFiles"
      />

      <div class="flex flex-wrap items-center gap-2 max-sm:flex-nowrap max-sm:overflow-x-auto max-sm:[scrollbar-width:none]">
        <input ref="fileInput" type="file" multiple hidden :accept="ACCEPTED_FILE_TYPES" @change="handleFileSelect" />
        <ChatComposerActions
          :disabled="isDisabled"
          :voice-recording="isVoiceRecording"
          :image-generating="imageGenerating"
          :emoji-open="showEmojiPicker"
          :quick-actions="quickActions"
          @attach="fileInput?.click()"
          @voice="toggleVoiceInput"
          @vision="showVisionModal = true"
          @presets="showPresetsModal = true"
          @image="showImageGenModal = true"
          @emoji="showEmojiPicker = !showEmojiPicker"
          @prompt-insert="handlePromptInsert"
          @quick-action="runQuickAction"
        />
        <ChatComposerToggles
          v-model:knowledge="useKnowledge"
          :overseer="overseerEnabled"
          :thinking="thinkingEnabled"
          :budget="thinkingBudget"
          :disabled="isDisabled"
          @toggle-overseer="toggleOverseer"
          @toggle-thinking="toggleThinking"
          @set-budget="setThinkingBudget"
        />
        <span class="grow" aria-hidden="true"></span>
        <ChatComposerModelPicker v-model="selectedModel" :models="pickerModels" :disabled="isDisabled" />
        <ChatComposerSendButton :can-send="canSend" :sending="isSending" :queue-length="messageQueueLength" @send="sendMessage" />
      </div>
    </div>

    <ChatInputStatusBar
      :typing-visible="isTypingIndicatorVisible"
      :character-count="characterCount"
      :max-characters="MAX_CHARACTERS"
      :near-limit="isNearLimit"
      :voice-recording="isVoiceRecording"
    />

    <div v-if="showEmojiPicker" ref="emojiPicker">
      <ChatComposerEmojiPicker @pick="onEmojiPick" @close="showEmojiPicker = false" />
    </div>

    <TranslationShortcutPanel
      v-if="showTranslatePanel"
      :initial-text="messageText"
      @close="showTranslatePanel = false"
      @translation-result="handleTranslationResult"
    />
    <VisionAnalysisModal v-if="showVisionModal" @close="showVisionModal = false" @send-to-chat="handleVisionSendToChat" />
    <SlashCommandDropdown
      :show="showSlashDropdown"
      :suggestions="slashSuggestions"
      :selected-index="slashSelectedIndex"
      :anchor-el="messageInput ?? null"
      @select="applySlashPreset"
      @update:selected-index="setSlashIndex"
    />
    <PresetManagementModal v-model="showPresetsModal" @close="showPresetsModal = false" />
    <ChatImageGenDialog
      v-model:open="showImageGenModal"
      v-model:prompt="imagePrompt"
      v-model:provider="imageProvider"
      :generating="imageGenerating"
      @submit="submitImageGeneration"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, inject, onMounted, onUnmounted, ref, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useChatStore } from '@/stores/useChatStore'
import type { MultiModalResponse } from '@/utils/VisionMultimodalApiClient'
import { useThinkingMode } from '@/composables/useThinkingMode'
import { useChatModelSelection } from '@/composables/chat/useChatModelSelection'
import { useChatKnowledge } from '@/composables/chat/useChatKnowledge'
import { useComposerUploads } from '@/composables/chat/useComposerUploads'
import { useComposerVoice } from '@/composables/chat/useComposerVoice'
import { useComposerSend } from '@/composables/chat/useComposerSend'
import { MAX_CHARACTERS, resetTextareaHeight, useComposerInput } from '@/composables/chat/useComposerInput'
import { useComposerImageGen } from '@/composables/chat/useComposerImageGen'
import { useComposerQuickActions } from '@/composables/chat/useComposerQuickActions'
import VisionAnalysisModal from './VisionAnalysisModal.vue'
import PresetManagementModal from './PresetManagementModal.vue'
import TranslationShortcutPanel from './TranslationShortcutPanel.vue'
import ChatInputStatusBar from './ChatInputStatusBar.vue'
import SlashCommandDropdown from './SlashCommandDropdown.vue'
import ChatComposerUploads from './ChatComposerUploads.vue'
import ChatComposerActions from './ChatComposerActions.vue'
import ChatComposerToggles from './ChatComposerToggles.vue'
import ChatComposerModelPicker from './ChatComposerModelPicker.vue'
import ChatComposerSendButton from './ChatComposerSendButton.vue'
import ChatComposerEmojiPicker from './ChatComposerEmojiPicker.vue'
import ChatImageGenDialog from './ChatImageGenDialog.vue'

interface VisionSendPayload {
  filename: string
  intent: string
  question?: string
  result: MultiModalResponse
}

const emit = defineEmits<{ (e: 'vision-send-to-chat', payload: VisionSendPayload): void }>()

const ACCEPTED_FILE_TYPES = '.txt,.md,.pdf,.doc,.docx,.json,.csv,.png,.jpg,.jpeg,.gif'

const { t } = useI18n()
const store = useChatStore()
// Issue #690: Overseer state is provided by ChatInterface
const overseerEnabled = inject<Ref<boolean>>('overseerEnabled', ref(false))
const toggleOverseer = inject<() => void>('toggleOverseer', () => {})

const messageText = ref('')
const messageInput = ref<HTMLTextAreaElement>()
const fileInput = ref<HTMLInputElement>()
const emojiPicker = ref<HTMLElement>()
const showEmojiPicker = ref(false)
const showVisionModal = ref(false)
const showPresetsModal = ref(false)
const messageQueueLength = ref(0) // no producer yet: nothing queues chat messages

const { enabled: useKnowledge } = useChatKnowledge()
const { attachedFiles, uploadProgress, isCancellable, cancelUpload, serverFileIds, handleFileSelect, retryUpload, removeFile, clearAllFiles } =
  useComposerUploads()
const { isVoiceRecording, toggleVoiceInput } = useComposerVoice(messageText)
const thinking = useThinkingMode(() => store.currentSessionId)
const { enabled: thinkingEnabled, budgetTokens: thinkingBudget, toggle: toggleThinking, setBudget: setThinkingBudget } = thinking
const { selectedModel, pickerModels, overrideFields, fetchModels } = useChatModelSelection()
const { isSending, canSend, sendMessage } = useComposerSend({
  messageText, attachedFiles, serverFileIds, isVoiceRecording, thinking, overrideFields,
  resetTextareaHeight: () => resetTextareaHeight(messageInput),
})
const {
  isInputFocused, characterCount, isNearLimit, isTypingIndicatorVisible, slashSuggestions, showSlashDropdown,
  slashSelectedIndex, setSlashIndex, fetchPresets, applySlashPreset, handleKeydown, handleInput, focusInput,
} = useComposerInput({ messageText, messageInput, canSend, sendMessage })
const { imageGenerating, showImageGenModal, imagePrompt, imageProvider, submitImageGeneration } = useComposerImageGen()
const { quickActions, showTranslatePanel, runQuickAction, insertAtCaret, handlePromptInsert, handleTranslationResult } =
  useComposerQuickActions(messageText, messageInput)

const isDisabled = computed(() => isSending.value || isVoiceRecording.value)

const inputPlaceholder = computed(() => {
  if (isVoiceRecording.value) return t('voice.listening')
  if (isSending.value) return t('chat.input.sendingMessage')
  if (store.isTyping) return t('chat.input.aiResponding')
  return t('chat.input.typeMessage')
})

function onEmojiPick(emoji: string): void {
  insertAtCaret(emoji)
  showEmojiPicker.value = false
}

function handleVisionSendToChat(payload: VisionSendPayload): void {
  showVisionModal.value = false
  emit('vision-send-to-chat', payload)
}

/** A click outside the picker closes it; the emoji button toggles it itself, so it is not "outside". */
function handleClickOutside(event: Event): void {
  const target = event.target as Element
  if (!showEmojiPicker.value || !emojiPicker.value || emojiPicker.value.contains(target)) return
  if (target.closest?.('[data-emoji-trigger]')) return
  showEmojiPicker.value = false
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
  focusInput()
  fetchPresets() // GH#4449: preload for instant autocomplete
  thinking.load() // GH#8993: thinking preferences of the current session
  fetchModels() // #11585: the live model list for the picker
})

onUnmounted(() => document.removeEventListener('click', handleClickOutside))
</script>
