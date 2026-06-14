<template>
  <Teleport to="body">
    <Transition name="voice-overlay">
      <div
        v-if="voiceConversation.isActive.value"
        class="voice-overlay"
        @keydown.escape="close"
        tabindex="-1"
        ref="overlayRef"
      >
        <!-- Backdrop grain texture -->
        <div class="voice-overlay__grain" aria-hidden="true"></div>

        <!-- Panel -->
        <div class="voice-overlay__panel">

          <!-- Header -->
          <header class="voice-overlay__header">
            <div class="flex items-center gap-3">
              <div class="voice-overlay__icon">
                <Icon name="headset" />
              </div>
              <div>
                <h2 class="text-base font-semibold text-autobot-text-primary">
                  {{ $t('chat.voice.title') }}
                </h2>
                <p class="text-xs text-autobot-text-muted">
                  {{ voiceConversation.stateLabel.value }}
                </p>
              </div>
            </div>

            <div class="flex items-center gap-2">
              <!-- Mode Selector -->
              <select
                :value="voiceConversation.mode.value"
                @change="handleModeChange"
                class="voice-overlay__mode-select"
                :aria-label="$t('chat.voice.conversationMode')"
              >
                <option value="walkie-talkie">{{ $t('chat.voice.walkieTalkie') }}</option>
                <option value="hands-free">{{ $t('chat.voice.handsFree') }}</option>
                <option value="full-duplex">{{ $t('chat.voice.fullDuplex') }}</option>
              </select>

              <!-- Language indicator (#1334) -->
              <div
                class="voice-overlay__lang-badge"
                :title="$t('chat.voice.languageLabel')"
              >
                <Icon name="globe" />
                {{ voiceConversation.currentLanguage.value.toUpperCase() }}
              </div>

              <!-- WS connection indicator (full-duplex only) -->
              <div
                v-if="voiceConversation.mode.value === 'full-duplex'"
                class="voice-overlay__ws-indicator"
                :class="{
                  'voice-overlay__ws-indicator--connected':
                    wsConnected,
                }"
                :title="wsConnected
                  ? $t('chat.voice.connected') : $t('chat.voice.disconnected')"
              ></div>

              <!-- Close -->
              <button
                @click="close"
                class="voice-overlay__close-btn"
                :aria-label="$t('chat.voice.closeVoiceChat')"
              >
                <Icon name="times" />
              </button>
            </div>
          </header>

          <!-- Conversation Bubbles -->
          <div class="voice-overlay__conversation" ref="conversationRef">
            <div
              v-if="voiceConversation.bubbles.value.length === 0"
              class="voice-overlay__empty"
            >
              <Icon name="comments" class="text-2xl opacity-20" />
              <p>{{ $t('chat.voice.tapMicToStart') }}</p>
            </div>

            <TransitionGroup name="bubble" tag="div" class="space-y-3">
              <div
                v-for="bubble in voiceConversation.bubbles.value"
                :key="bubble.id"
                class="voice-overlay__bubble"
                :class="{
                  'voice-overlay__bubble--user': bubble.sender === 'user',
                  'voice-overlay__bubble--assistant': bubble.sender === 'assistant',
                }"
              >
                <div class="voice-overlay__bubble-icon">
                  <Icon :name="bubble.sender === 'user' ? 'user' : 'robot'" />
                </div>
                <div class="voice-overlay__bubble-content">
                  <span class="voice-overlay__bubble-sender">
                    {{ bubble.sender === 'user' ? $t('chat.voice.you') : $t('chat.voice.autobot') }}
                  </span>
                  <p>{{ bubble.content }}</p>
                </div>
              </div>
            </TransitionGroup>

            <!-- Live transcript preview -->
            <Transition name="fade">
              <div
                v-if="voiceConversation.currentTranscript.value"
                class="voice-overlay__live-transcript"
              >
                <Icon name="ellipsis-h" class="animate-pulse me-2" />
                {{ voiceConversation.currentTranscript.value }}
              </div>
            </Transition>
          </div>

          <!-- Error Banner -->
          <Transition name="fade">
            <div
              v-if="voiceConversation.errorMessage.value"
              class="voice-overlay__error"
            >
              <Icon name="exclamation-triangle" class="me-2" />
              {{ voiceConversation.errorMessage.value }}
            </div>
          </Transition>

          <!-- Insecure-context warning (#1059) — shown when mic-dependent mode selected
               but browser blocks getUserMedia due to an untrusted certificate -->
          <Transition name="fade">
            <div
              v-if="showInsecureContextWarning"
              class="voice-overlay__cert-warning"
            >
              <p class="voice-overlay__cert-warning-title">
                <Icon name="lock" class="me-2" />{{ $t('chat.voice.micBlocked') }}
              </p>
              <p class="voice-overlay__cert-warning-body">
                {{ $t('chat.voice.certRequired') }}
              </p>
              <ol class="voice-overlay__cert-warning-steps">
                <li>{{ $t('chat.voice.certStep1') }}</li>
                <li>
                  {{ $t('chat.voice.certStep2Pre') }}
                  <code>chrome://flags/#unsafely-treat-insecure-origin-as-secure</code>,
                  {{ $t('chat.voice.certStep2Post', { origin: currentOrigin }) }}
                </li>
              </ol>
              <p class="voice-overlay__cert-warning-fallback">
                <Icon name="info-circle" class="me-1" />
                {{ $t('chat.voice.walkieTalkieFallback') }}
              </p>
            </div>
          </Transition>

          <!-- Hands-free controls (#1030) -->
          <div
            v-if="voiceConversation.mode.value === 'hands-free'"
            class="voice-overlay__hf-controls"
          >
            <!-- Amplitude meter -->
            <div class="voice-overlay__amplitude">
              <div
                class="voice-overlay__amplitude-bar"
                :style="{ width: `${voiceConversation.audioLevel.value * 100}%` }"
              ></div>
            </div>

            <!-- Silence threshold slider -->
            <div class="voice-overlay__threshold">
              <label class="voice-overlay__threshold-label">
                {{ $t('chat.voice.silenceTimeout') }}
              </label>
              <input
                type="range"
                min="500"
                max="3000"
                step="100"
                :value="voiceConversation.silenceThreshold.value"
                @input="voiceConversation.silenceThreshold.value = Number(($event.target as HTMLInputElement).value)"
                class="voice-overlay__threshold-slider"
              />
              <span class="voice-overlay__threshold-value">
                {{ (voiceConversation.silenceThreshold.value / 1000).toFixed(1) }}s
              </span>
            </div>
          </div>

          <!-- Mic Control Area -->
          <div class="voice-overlay__controls">
            <!-- Pulse rings (visible when listening) -->
            <div class="voice-overlay__mic-container">
              <div
                v-if="voiceConversation.state.value === 'listening'"
                class="voice-overlay__pulse-ring voice-overlay__pulse-ring--1"
              ></div>
              <div
                v-if="voiceConversation.state.value === 'listening'"
                class="voice-overlay__pulse-ring voice-overlay__pulse-ring--2"
              ></div>

              <button
                @click="handleMicClick"
                class="voice-overlay__mic-btn"
                :class="{
                  'voice-overlay__mic-btn--listening':
                    voiceConversation.state.value === 'listening',
                  'voice-overlay__mic-btn--processing':
                    voiceConversation.state.value === 'processing',
                  'voice-overlay__mic-btn--speaking':
                    voiceConversation.state.value === 'speaking',
                }"
                :disabled="
                  voiceConversation.state.value === 'processing'
                "
                :aria-label="voiceConversation.stateLabel.value"
              >
                <Icon :name="micIcon" />
              </button>
            </div>

            <p class="voice-overlay__hint">
              {{ micHint }}
            </p>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import {
  computed,
  nextTick,
  onBeforeUnmount,
  ref,
  watch,
} from 'vue'
import { useI18n } from 'vue-i18n'
import { useVoiceConversation } from '@/composables/useVoiceConversation'
import { useVoiceOutput } from '@/composables/useVoiceOutput'

const emit = defineEmits<{
  (e: 'close'): void
}>()

const { t } = useI18n()
const voiceConversation = useVoiceConversation()
const { wsConnected } = useVoiceOutput()
const overlayRef = ref<HTMLElement | null>(null)
const conversationRef = ref<HTMLElement | null>(null)

const micIcon = computed(() => {
  switch (voiceConversation.state.value) {
    case 'listening':
      return isAutoMode.value ? 'microphone' : 'stop'
    case 'processing': return 'spinner'
    case 'speaking':
      return 'stop'
    default: return 'microphone'
  }
})

const isFullDuplex = computed(
  () => voiceConversation.mode.value === 'full-duplex',
)
const isHandsFree = computed(
  () => voiceConversation.mode.value === 'hands-free',
)
const isAutoMode = computed(
  () => isFullDuplex.value || isHandsFree.value,
)

// Show insecure-context warning when a mic-dependent mode is active
// but the browser can't provide getUserMedia (#1059)
const showInsecureContextWarning = computed(
  () => isAutoMode.value && !voiceConversation.micAccessAvailable.value,
)
const currentOrigin = window.location.origin

const micHint = computed(() => {
  switch (voiceConversation.state.value) {
    case 'listening':
      return isAutoMode.value
        ? t('chat.voice.hintAutoListening')
        : t('chat.voice.hintTapToStop')
    case 'processing':
      return isHandsFree.value
        ? t('chat.voice.hintTranscribing')
        : t('chat.voice.hintWaitingResponse')
    case 'speaking':
      return t('chat.voice.hintInterrupt')
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

// Auto-scroll conversation when new bubbles arrive
watch(
  () => voiceConversation.bubbles.value.length,
  async () => {
    await nextTick()
    if (conversationRef.value) {
      conversationRef.value.scrollTop =
        conversationRef.value.scrollHeight
    }
  }
)

// Focus overlay for keyboard accessibility
watch(
  () => voiceConversation.isActive.value,
  async (active) => {
    if (active) {
      await nextTick()
      overlayRef.value?.focus()
    }
  }
)

onBeforeUnmount(() => {
  voiceConversation.cleanup()
})
</script>

<style scoped>
/* ============================================
   Voice Conversation Overlay
   Aesthetic: Dark comm-station with electric glow
   ============================================ */

.voice-overlay {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(2, 6, 23, 0.85);
  backdrop-filter: blur(12px);
  outline: none;
}

/* Subtle noise grain for depth */
.voice-overlay__grain {
  position: absolute;
  inset: 0;
  opacity: 0.03;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  pointer-events: none;
}

.voice-overlay__panel {
  position: relative;
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 480px;
  max-height: 85vh;
  margin: var(--spacing-4);
  border-radius: 1.25rem;
  background: var(--bg-card, #0f172a);
  border: 1px solid var(--border-subtle, rgba(148, 163, 184, 0.1));
  box-shadow:
    0 0 0 1px rgba(37, 99, 235, 0.08),
    0 24px 80px -12px rgba(0, 0, 0, 0.6),
    0 0 120px -40px rgba(37, 99, 235, 0.15);
  overflow: hidden;
}

/* Header */
.voice-overlay__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-4) var(--spacing-5);
  border-bottom: 1px solid var(--border-subtle, rgba(148, 163, 184, 0.1));
  background: var(--bg-elevated, rgba(15, 23, 42, 0.8));
}

.voice-overlay__icon {
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-lg);
  background: rgba(37, 99, 235, 0.15);
  color: #60a5fa;
  font-size: var(--text-sm);
}

.voice-overlay__mode-select {
  appearance: none;
  padding: var(--spacing-1) var(--spacing-7) var(--spacing-1) var(--spacing-2);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-subtle, rgba(148, 163, 184, 0.15));
  background: var(--bg-tertiary, #1e293b)
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2394a3b8' d='M3 4.5L6 8l3-3.5H3z'/%3E%3C/svg%3E")
    no-repeat right 0.5rem center;
  color: var(--text-secondary, #94a3b8);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: border-color var(--duration-150);
}

.voice-overlay__mode-select:hover {
  border-color: rgba(96, 165, 250, 0.3);
}

.voice-overlay__mode-select option:disabled {
  color: rgba(148, 163, 184, 0.4);
}

/* Language badge (#1334) */
.voice-overlay__lang-badge {
  display: flex;
  align-items: center;
  gap: var(--spacing-micro-4);
  padding: 0.15rem 0.5rem;
  border-radius: var(--radius-md);
  background: rgba(37, 99, 235, 0.1);
  border: 1px solid rgba(37, 99, 235, 0.2);
  color: #93c5fd;
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.voice-overlay__lang-badge i {
  font-size: 0.625rem;
  opacity: 0.7;
}

/* WS connection indicator (full-duplex) */
.voice-overlay__ws-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgba(239, 68, 68, 0.6);
  transition: background var(--duration-200);
}

.voice-overlay__ws-indicator--connected {
  background: rgba(34, 197, 94, 0.8);
}

.voice-overlay__close-btn {
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  color: var(--text-muted, #64748b);
  transition: all var(--duration-150);
  cursor: pointer;
  border: none;
  background: transparent;
}

.voice-overlay__close-btn:hover {
  background: var(--bg-hover, rgba(148, 163, 184, 0.1));
  color: var(--text-primary, #f1f5f9);
}

/* Conversation area */
.voice-overlay__conversation {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-5);
  min-height: 200px;
  max-height: 40vh;
  scroll-behavior: smooth;
}

.voice-overlay__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-3);
  height: 100%;
  min-height: 120px;
  color: var(--text-muted, #64748b);
  font-size: var(--text-sm);
}

/* Bubbles */
.voice-overlay__bubble {
  display: flex;
  gap: var(--spacing-2-5);
  align-items: flex-start;
}

.voice-overlay__bubble--user {
  flex-direction: row-reverse;
}

.voice-overlay__bubble-icon {
  flex-shrink: 0;
  width: 1.75rem;
  height: 1.75rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 0.7rem;
}

.voice-overlay__bubble--user .voice-overlay__bubble-icon {
  background: rgba(37, 99, 235, 0.2);
  color: #60a5fa;
}

.voice-overlay__bubble--assistant .voice-overlay__bubble-icon {
  background: rgba(16, 185, 129, 0.15);
  color: #34d399;
}

.voice-overlay__bubble-content {
  max-width: 80%;
  padding: var(--spacing-2-5) var(--spacing-3-5);
  border-radius: 0.875rem;
  font-size: var(--text-sm);
  line-height: 1.5;
  color: var(--text-primary, #e2e8f0);
}

.voice-overlay__bubble--user .voice-overlay__bubble-content {
  background: rgba(37, 99, 235, 0.12);
  border: 1px solid rgba(37, 99, 235, 0.15);
  border-bottom-right-radius: var(--radius-default);
}

.voice-overlay__bubble--assistant .voice-overlay__bubble-content {
  background: var(--bg-tertiary, rgba(30, 41, 59, 0.6));
  border: 1px solid var(--border-subtle, rgba(148, 163, 184, 0.08));
  border-bottom-left-radius: var(--radius-default);
}

.voice-overlay__bubble-sender {
  display: block;
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: var(--spacing-0-5);
  opacity: 0.6;
}

/* Live transcript */
.voice-overlay__live-transcript {
  margin-top: var(--spacing-3);
  padding: var(--spacing-2) var(--spacing-3);
  border-radius: var(--radius-lg);
  background: rgba(37, 99, 235, 0.06);
  border: 1px dashed rgba(37, 99, 235, 0.2);
  color: #93c5fd;
  font-size: 0.8125rem;
  font-style: italic;
}

/* Error banner */
.voice-overlay__error {
  margin: var(--spacing-0) var(--spacing-5);
  padding: var(--spacing-2) var(--spacing-3);
  border-radius: var(--radius-lg);
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
  color: #fca5a5;
  font-size: 0.8125rem;
}

/* Insecure-context cert warning (#1059) */
.voice-overlay__cert-warning {
  margin: var(--spacing-0) var(--spacing-5);
  padding: var(--spacing-3) var(--spacing-4);
  border-radius: var(--radius-lg);
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.25);
  color: #fcd34d;
  font-size: 0.8125rem;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-micro-5);
}

.voice-overlay__cert-warning-title {
  font-weight: 600;
  font-size: var(--text-sm);
}

.voice-overlay__cert-warning-body {
  color: #fde68a;
}

.voice-overlay__cert-warning-steps {
  padding-left: var(--spacing-5);
  list-style: decimal;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.voice-overlay__cert-warning-steps code {
  background: rgba(0, 0, 0, 0.3);
  padding: 0.1rem 0.3rem;
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  word-break: break-all;
}

.voice-overlay__cert-warning-fallback {
  color: #94a3b8;
  font-size: var(--text-xs);
  margin-top: var(--spacing-1);
}

/* Controls area */
.voice-overlay__controls {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-6) var(--spacing-5) var(--spacing-8);
  border-top: 1px solid var(--border-subtle, rgba(148, 163, 184, 0.08));
  background: linear-gradient(
    to top,
    var(--bg-primary, #020617) 0%,
    transparent 100%
  );
}

/* Mic button container (holds pulse rings + button) */
.voice-overlay__mic-container {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 96px;
  height: 96px;
}

/* Pulse rings */
.voice-overlay__pulse-ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2px solid rgba(37, 99, 235, 0.3);
  animation: pulse-expand 2s ease-out infinite;
}

.voice-overlay__pulse-ring--2 {
  animation-delay: 0.6s;
}

@keyframes pulse-expand {
  0% {
    transform: scale(0.7);
    opacity: 0.8;
  }
  100% {
    transform: scale(1.4);
    opacity: 0;
  }
}

/* Mic button */
.voice-overlay__mic-btn {
  position: relative;
  z-index: 1;
  width: 64px;
  height: 64px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid rgba(37, 99, 235, 0.3);
  background: rgba(37, 99, 235, 0.1);
  color: #60a5fa;
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-out);
  box-shadow: 0 0 24px -4px rgba(37, 99, 235, 0.2);
}

.voice-overlay__mic-btn:hover:not(:disabled) {
  background: rgba(37, 99, 235, 0.2);
  border-color: rgba(37, 99, 235, 0.5);
  box-shadow: 0 0 32px -4px rgba(37, 99, 235, 0.35);
  transform: scale(1.05);
}

.voice-overlay__mic-btn:active:not(:disabled) {
  transform: scale(0.97);
}

.voice-overlay__mic-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

/* Listening state — red glow */
.voice-overlay__mic-btn--listening {
  background: rgba(239, 68, 68, 0.15);
  border-color: rgba(239, 68, 68, 0.5);
  color: #f87171;
  box-shadow: 0 0 32px -4px rgba(239, 68, 68, 0.3);
  animation: mic-glow 1.5s ease-in-out infinite alternate;
}

@keyframes mic-glow {
  0% { box-shadow: 0 0 24px -4px rgba(239, 68, 68, 0.2); }
  100% { box-shadow: 0 0 40px -4px rgba(239, 68, 68, 0.4); }
}

/* Processing state */
.voice-overlay__mic-btn--processing {
  background: rgba(37, 99, 235, 0.08);
  border-color: rgba(37, 99, 235, 0.2);
  color: #93c5fd;
}

/* Speaking state — green glow */
.voice-overlay__mic-btn--speaking {
  background: rgba(16, 185, 129, 0.12);
  border-color: rgba(16, 185, 129, 0.4);
  color: #34d399;
  box-shadow: 0 0 32px -4px rgba(16, 185, 129, 0.25);
  animation: speak-glow 1s ease-in-out infinite alternate;
}

@keyframes speak-glow {
  0% { box-shadow: 0 0 24px -4px rgba(16, 185, 129, 0.15); }
  100% { box-shadow: 0 0 40px -4px rgba(16, 185, 129, 0.35); }
}

.voice-overlay__hint {
  font-size: var(--text-xs);
  color: var(--text-muted, #64748b);
  letter-spacing: 0.02em;
}

/* ============================================
   Hands-free controls (#1030)
   ============================================ */

.voice-overlay__hf-controls {
  padding: var(--spacing-3) var(--spacing-5) var(--spacing-0);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2-5);
}

/* Amplitude meter */
.voice-overlay__amplitude {
  height: 4px;
  border-radius: var(--radius-xs);
  background: rgba(148, 163, 184, 0.1);
  overflow: hidden;
}

.voice-overlay__amplitude-bar {
  height: 100%;
  border-radius: var(--radius-xs);
  background: linear-gradient(90deg, #60a5fa, #818cf8);
  transition: width var(--duration-100) var(--ease-out);
  min-width: 0;
}

/* Silence threshold */
.voice-overlay__threshold {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.voice-overlay__threshold-label {
  font-size: 0.6875rem;
  color: var(--text-muted, #64748b);
  white-space: nowrap;
}

.voice-overlay__threshold-slider {
  flex: 1;
  height: 4px;
  appearance: none;
  background: rgba(148, 163, 184, 0.15);
  border-radius: var(--radius-xs);
  outline: none;
  cursor: pointer;
}

.voice-overlay__threshold-slider:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.voice-overlay__threshold-slider::-webkit-slider-thumb {
  appearance: none;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--color-primary);
  border: 2px solid var(--bg-card, #0f172a);
  cursor: pointer;
}

.voice-overlay__threshold-slider::-moz-range-thumb {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--color-primary);
  border: 2px solid var(--bg-card, #0f172a);
  cursor: pointer;
}

.voice-overlay__threshold-value {
  font-size: 0.6875rem;
  color: #93c5fd;
  min-width: 2rem;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

/* ============================================
   Transitions
   ============================================ */

/* Overlay enter/leave */
.voice-overlay-enter-active {
  transition: opacity var(--duration-250) var(--ease-out);
}
.voice-overlay-enter-active .voice-overlay__panel {
  transition: transform var(--duration-300) cubic-bezier(0.16, 1, 0.3, 1),
              opacity 0.25s ease;
}
.voice-overlay-leave-active {
  transition: opacity var(--duration-200) var(--ease-out);
}
.voice-overlay-leave-active .voice-overlay__panel {
  transition: transform var(--duration-200) var(--ease-out), opacity var(--duration-150) var(--ease-out);
}

.voice-overlay-enter-from {
  opacity: 0;
}
.voice-overlay-enter-from .voice-overlay__panel {
  opacity: 0;
  transform: translateY(24px) scale(0.96);
}
.voice-overlay-leave-to {
  opacity: 0;
}
.voice-overlay-leave-to .voice-overlay__panel {
  opacity: 0;
  transform: translateY(12px) scale(0.98);
}

/* Bubble enter */
.bubble-enter-active {
  transition: all var(--duration-300) cubic-bezier(0.16, 1, 0.3, 1);
}
.bubble-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

/* Fade */
.fade-enter-active,
.fade-leave-active {
  transition: opacity var(--duration-200) var(--ease-out);
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
