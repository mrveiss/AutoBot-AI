<template>
  <div class="voice-panel h-full flex flex-col bg-autobot-bg-card border-l border-autobot-border">
    <!-- Header -->
    <div class="flex items-center justify-between p-3 border-b border-autobot-border flex-shrink-0">
      <div class="flex items-center gap-2">
        <div class="voice-panel__icon">
          <i class="fas fa-headset"></i>
        </div>
        <div>
          <h3 class="text-sm font-semibold text-autobot-text-primary">{{ $t('chat.voice.title') }}</h3>
          <p class="text-xs text-autobot-text-muted">
            {{ voiceConversation.stateLabel.value }}
          </p>
        </div>
      </div>
      <div class="flex items-center gap-1">
        <!-- Mode Selector -->
        <select
          :value="voiceConversation.mode.value"
          @change="handleModeChange"
          class="voice-panel__mode-select"
          :aria-label="$t('chat.voice.conversationMode')"
        >
          <option value="walkie-talkie">{{ $t('chat.voice.walkieTalkie') }}</option>
          <option value="hands-free">{{ $t('chat.voice.handsFree') }}</option>
          <option value="full-duplex">{{ $t('chat.voice.fullDuplex') }}</option>
        </select>

        <!-- Language indicator (#1334) -->
        <div
          class="voice-panel__lang-badge"
          :title="$t('chat.voice.languageLabel')"
        >
          <i class="fas fa-globe"></i>
          {{ voiceConversation.currentLanguage.value.toUpperCase() }}
        </div>

        <!-- WS indicator (full-duplex) -->
        <div
          v-if="voiceConversation.mode.value === 'full-duplex'"
          class="voice-panel__ws-dot"
          :class="{ 'voice-panel__ws-dot--connected': voiceConversation.wsConnected.value }"
          :title="voiceConversation.wsConnected.value ? $t('chat.voice.connected') : $t('chat.voice.disconnected')"
        ></div>

        <!-- Close -->
        <button @click="close" class="action-btn" :title="$t('chat.voice.closeVoicePanel')">
          <i class="fas fa-times text-xs"></i>
        </button>
      </div>
    </div>

    <!-- State + Transcript area -->
    <div class="flex-1 flex flex-col items-center justify-center p-4 gap-4 overflow-y-auto">
      <!-- State indicator -->
      <div class="voice-panel__state-ring" :class="stateClass">
        <i :class="stateIcon" class="text-lg"></i>
      </div>

      <p class="text-sm font-medium" :class="stateTextClass">
        {{ voiceConversation.stateLabel.value }}
      </p>

      <!-- Live transcript -->
      <div
        v-if="voiceConversation.currentTranscript.value"
        class="voice-panel__transcript"
      >
        <i class="fas fa-ellipsis-h animate-pulse mr-1 text-xs"></i>
        {{ voiceConversation.currentTranscript.value }}
      </div>
    </div>

    <!-- Error banner -->
    <div
      v-if="voiceConversation.errorMessage.value"
      class="voice-panel__error"
    >
      <i class="fas fa-exclamation-triangle mr-1"></i>
      {{ voiceConversation.errorMessage.value }}
    </div>

    <!-- Insecure context warning -->
    <div
      v-if="showInsecureContextWarning"
      class="voice-panel__cert-warning"
    >
      <p class="font-semibold text-xs">
        <i class="fas fa-lock-open mr-1"></i>{{ $t('chat.voice.micBlocked') }}
      </p>
      <p class="text-xs opacity-80">
        {{ $t('chat.voice.certRequiredShort') }}
      </p>
    </div>

    <!-- Hands-free controls -->
    <div
      v-if="voiceConversation.mode.value === 'hands-free'"
      class="voice-panel__hf-controls"
    >
      <div class="voice-panel__amplitude">
        <div
          class="voice-panel__amplitude-bar"
          :style="{ width: `${voiceConversation.audioLevel.value * 100}%` }"
        ></div>
      </div>
      <div class="flex items-center gap-2">
        <label class="text-xs text-autobot-text-muted whitespace-nowrap">{{ $t('chat.voice.silence') }}</label>
        <input
          type="range"
          min="500"
          max="3000"
          step="100"
          :value="voiceConversation.silenceThreshold.value"
          @input="voiceConversation.silenceThreshold.value = Number(($event.target as HTMLInputElement).value)"
          class="voice-panel__slider flex-1"
        />
        <span class="text-xs text-autobot-text-secondary tabular-nums min-w-[2rem] text-right">
          {{ (voiceConversation.silenceThreshold.value / 1000).toFixed(1) }}s
        </span>
      </div>
    </div>

    <!-- Mic control -->
    <div class="voice-panel__controls">
      <div class="voice-panel__mic-container">
        <div
          v-if="voiceConversation.state.value === 'listening'"
          class="voice-panel__pulse voice-panel__pulse--1"
        ></div>
        <div
          v-if="voiceConversation.state.value === 'listening'"
          class="voice-panel__pulse voice-panel__pulse--2"
        ></div>

        <button
          @click="handleMicClick"
          class="voice-panel__mic-btn"
          :class="{
            'voice-panel__mic-btn--listening': voiceConversation.state.value === 'listening',
            'voice-panel__mic-btn--processing': voiceConversation.state.value === 'processing',
            'voice-panel__mic-btn--speaking': voiceConversation.state.value === 'speaking',
          }"
          :disabled="
            voiceConversation.state.value === 'processing' ||
            (voiceConversation.state.value === 'speaking' && !isFullDuplex)
          "
          :aria-label="voiceConversation.stateLabel.value"
        >
          <i :class="micIcon" class="text-base"></i>
        </button>
      </div>

      <p class="text-xs text-autobot-text-muted text-center mt-1">
        {{ micHint }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { useVoiceConversation } from '@/composables/useVoiceConversation'

const emit = defineEmits<{
  (e: 'close'): void
}>()

const { t } = useI18n()
const voiceConversation = useVoiceConversation()

const isFullDuplex = computed(
  () => voiceConversation.mode.value === 'full-duplex',
)
const isHandsFree = computed(
  () => voiceConversation.mode.value === 'hands-free',
)
const isAutoMode = computed(
  () => isFullDuplex.value || isHandsFree.value,
)

const showInsecureContextWarning = computed(
  () => isAutoMode.value && !voiceConversation.micAccessAvailable.value,
)

const stateClass = computed(() => ({
  'voice-panel__state-ring--idle': voiceConversation.state.value === 'idle',
  'voice-panel__state-ring--listening': voiceConversation.state.value === 'listening',
  'voice-panel__state-ring--processing': voiceConversation.state.value === 'processing',
  'voice-panel__state-ring--speaking': voiceConversation.state.value === 'speaking',
}))

const stateTextClass = computed(() => {
  switch (voiceConversation.state.value) {
    case 'listening': return 'text-red-400'
    case 'processing': return 'text-blue-400'
    case 'speaking': return 'text-emerald-400'
    default: return 'text-autobot-text-secondary'
  }
})

const stateIcon = computed(() => {
  switch (voiceConversation.state.value) {
    case 'listening': return 'fas fa-microphone'
    case 'processing': return 'fas fa-spinner fa-spin'
    case 'speaking': return 'fas fa-volume-up'
    default: return 'fas fa-microphone-slash'
  }
})

const micIcon = computed(() => {
  switch (voiceConversation.state.value) {
    case 'listening':
      return isAutoMode.value ? 'fas fa-microphone' : 'fas fa-stop'
    case 'processing': return 'fas fa-spinner fa-spin'
    case 'speaking':
      return isFullDuplex.value ? 'fas fa-hand-paper' : 'fas fa-volume-up'
    default: return 'fas fa-microphone'
  }
})

const micHint = computed(() => {
  switch (voiceConversation.state.value) {
    case 'listening':
      return isAutoMode.value
        ? t('chat.voice.hintAutoDetects')
        : t('chat.voice.hintTapToStop')
    case 'processing':
      return isHandsFree.value
        ? t('chat.voice.hintTranscribing')
        : t('chat.voice.hintProcessing')
    case 'speaking':
      return isFullDuplex.value
        ? t('chat.voice.hintInterrupt')
        : t('chat.voice.hintRespondingShort')
    default:
      return isAutoMode.value
        ? t('chat.voice.hintAutoStart')
        : t('chat.voice.hintTapToSpeak')
  }
})

function handleMicClick(): void {
  voiceConversation.toggleListening()
}

function handleModeChange(event: Event): void {
  const target = event.target as HTMLSelectElement
  voiceConversation.setMode(
    target.value as 'walkie-talkie' | 'hands-free' | 'full-duplex',
  )
}

function close(): void {
  voiceConversation.deactivate()
  emit('close')
}

onBeforeUnmount(() => {
  voiceConversation.cleanup()
})
</script>

<style scoped>
.voice-panel {
  width: 280px;
  max-width: 280px;
  min-width: 280px;
}

.voice-panel__icon {
  width: 1.75rem;
  height: 1.75rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 0.375rem;
  background: rgba(37, 99, 235, 0.15);
  color: #60a5fa;
  font-size: 0.75rem;
}

.voice-panel__mode-select {
  appearance: none;
  padding: 0.2rem 1.5rem 0.2rem 0.4rem;
  border-radius: 0.25rem;
  border: 1px solid var(--border-subtle, rgba(148, 163, 184, 0.15));
  background: var(--bg-tertiary, #1e293b)
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2394a3b8' d='M3 4.5L6 8l3-3.5H3z'/%3E%3C/svg%3E")
    no-repeat right 0.35rem center;
  color: var(--text-secondary, #94a3b8);
  font-size: 0.6875rem;
  cursor: pointer;
}

.voice-panel__lang-badge {
  display: flex;
  align-items: center;
  gap: 0.2rem;
  padding: 0.1rem 0.4rem;
  border-radius: 0.25rem;
  background: rgba(37, 99, 235, 0.1);
  border: 1px solid rgba(37, 99, 235, 0.2);
  color: #93c5fd;
  font-size: 0.625rem;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.voice-panel__lang-badge i {
  font-size: 0.5625rem;
  opacity: 0.7;
}

.voice-panel__ws-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(239, 68, 68, 0.6);
  transition: background 0.2s;
}

.voice-panel__ws-dot--connected {
  background: rgba(34, 197, 94, 0.8);
}

.action-btn {
  @apply w-6 h-6 flex items-center justify-center rounded transition-colors text-autobot-text-muted hover:text-autobot-text-secondary hover:bg-autobot-bg-secondary;
}

/* State indicator ring */
.voice-panel__state-ring {
  width: 4rem;
  height: 4rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  border: 2px solid var(--border-subtle, rgba(148, 163, 184, 0.15));
  color: var(--text-muted, #64748b);
  transition: all 0.3s ease;
}

.voice-panel__state-ring--listening {
  border-color: rgba(239, 68, 68, 0.5);
  color: #f87171;
  box-shadow: 0 0 20px -4px rgba(239, 68, 68, 0.25);
  animation: ring-glow-red 1.5s ease-in-out infinite alternate;
}

.voice-panel__state-ring--processing {
  border-color: rgba(37, 99, 235, 0.3);
  color: #93c5fd;
}

.voice-panel__state-ring--speaking {
  border-color: rgba(16, 185, 129, 0.4);
  color: #34d399;
  box-shadow: 0 0 20px -4px rgba(16, 185, 129, 0.2);
  animation: ring-glow-green 1s ease-in-out infinite alternate;
}

@keyframes ring-glow-red {
  0% { box-shadow: 0 0 16px -4px rgba(239, 68, 68, 0.15); }
  100% { box-shadow: 0 0 28px -4px rgba(239, 68, 68, 0.35); }
}

@keyframes ring-glow-green {
  0% { box-shadow: 0 0 16px -4px rgba(16, 185, 129, 0.1); }
  100% { box-shadow: 0 0 28px -4px rgba(16, 185, 129, 0.3); }
}

/* Live transcript */
.voice-panel__transcript {
  width: 100%;
  padding: 0.5rem 0.75rem;
  border-radius: 0.375rem;
  background: rgba(37, 99, 235, 0.06);
  border: 1px dashed rgba(37, 99, 235, 0.2);
  color: #93c5fd;
  font-size: 0.75rem;
  font-style: italic;
  word-break: break-word;
}

/* Error */
.voice-panel__error {
  margin: 0 0.75rem;
  padding: 0.375rem 0.5rem;
  border-radius: 0.375rem;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
  color: #fca5a5;
  font-size: 0.75rem;
}

/* Cert warning */
.voice-panel__cert-warning {
  margin: 0 0.75rem;
  padding: 0.5rem 0.625rem;
  border-radius: 0.375rem;
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.25);
  color: #fcd34d;
  font-size: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

/* Hands-free controls */
.voice-panel__hf-controls {
  padding: 0.5rem 0.75rem 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.voice-panel__amplitude {
  height: 3px;
  border-radius: 1.5px;
  background: rgba(148, 163, 184, 0.1);
  overflow: hidden;
}

.voice-panel__amplitude-bar {
  height: 100%;
  border-radius: 1.5px;
  background: linear-gradient(90deg, #60a5fa, #818cf8);
  transition: width 0.1s ease-out;
  min-width: 0;
}

.voice-panel__slider {
  height: 3px;
  appearance: none;
  background: rgba(148, 163, 184, 0.15);
  border-radius: 1.5px;
  outline: none;
  cursor: pointer;
}

.voice-panel__slider::-webkit-slider-thumb {
  appearance: none;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #60a5fa;
  border: 2px solid var(--bg-card, #0f172a);
  cursor: pointer;
}

.voice-panel__slider::-moz-range-thumb {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #60a5fa;
  border: 2px solid var(--bg-card, #0f172a);
  cursor: pointer;
}

/* Mic controls */
.voice-panel__controls {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 1rem 0.75rem 1.25rem;
  border-top: 1px solid var(--border-subtle, rgba(148, 163, 184, 0.08));
}

.voice-panel__mic-container {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
}

/* Pulse rings */
.voice-panel__pulse {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2px solid rgba(37, 99, 235, 0.3);
  animation: panel-pulse 2s ease-out infinite;
}

.voice-panel__pulse--2 {
  animation-delay: 0.6s;
}

@keyframes panel-pulse {
  0% { transform: scale(0.7); opacity: 0.8; }
  100% { transform: scale(1.3); opacity: 0; }
}

/* Mic button */
.voice-panel__mic-btn {
  position: relative;
  z-index: 1;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid rgba(37, 99, 235, 0.3);
  background: rgba(37, 99, 235, 0.1);
  color: #60a5fa;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 0 16px -4px rgba(37, 99, 235, 0.2);
}

.voice-panel__mic-btn:hover:not(:disabled) {
  background: rgba(37, 99, 235, 0.2);
  border-color: rgba(37, 99, 235, 0.5);
  transform: scale(1.05);
}

.voice-panel__mic-btn:active:not(:disabled) {
  transform: scale(0.97);
}

.voice-panel__mic-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.voice-panel__mic-btn--listening {
  background: rgba(239, 68, 68, 0.15);
  border-color: rgba(239, 68, 68, 0.5);
  color: #f87171;
  box-shadow: 0 0 24px -4px rgba(239, 68, 68, 0.3);
  animation: mic-glow-red 1.5s ease-in-out infinite alternate;
}

@keyframes mic-glow-red {
  0% { box-shadow: 0 0 16px -4px rgba(239, 68, 68, 0.2); }
  100% { box-shadow: 0 0 28px -4px rgba(239, 68, 68, 0.4); }
}

.voice-panel__mic-btn--processing {
  background: rgba(37, 99, 235, 0.08);
  border-color: rgba(37, 99, 235, 0.2);
  color: #93c5fd;
}

.voice-panel__mic-btn--speaking {
  background: rgba(16, 185, 129, 0.12);
  border-color: rgba(16, 185, 129, 0.4);
  color: #34d399;
  box-shadow: 0 0 24px -4px rgba(16, 185, 129, 0.25);
  animation: mic-glow-green 1s ease-in-out infinite alternate;
}

@keyframes mic-glow-green {
  0% { box-shadow: 0 0 16px -4px rgba(16, 185, 129, 0.15); }
  100% { box-shadow: 0 0 28px -4px rgba(16, 185, 129, 0.35); }
}

/* Scrollbar */
.overflow-y-auto::-webkit-scrollbar {
  width: 4px;
}

.overflow-y-auto::-webkit-scrollbar-track {
  background: transparent;
}

.overflow-y-auto::-webkit-scrollbar-thumb {
  background: var(--border-default, rgba(148, 163, 184, 0.15));
  border-radius: 2px;
}
</style>
