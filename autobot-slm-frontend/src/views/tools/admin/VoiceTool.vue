// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
import { formatFleetTime } from '@/composables/useTimezone'
import { BaseAlert } from '@autobot/ui'
/**
 * VoiceTool - Voice Interface
 *
 * Voice input/output interface for AI interactions.
 * Migrated from main AutoBot frontend - Issue #729.
 */

import { ref, onMounted, onUnmounted } from 'vue'
import { useAutobotApi } from '@/composables/useAutobotApi'

const api = useAutobotApi()

// State
const loading = ref(false)
const error = ref<string | null>(null)
const isListening = ref(false)
const isSpeaking = ref(false)
const transcript = ref('')
const aiResponse = ref('')

interface VoiceSettings {
  language: string
  voice: string
  speed: number
  pitch: number
  autoListen: boolean
}

const settings = ref<VoiceSettings>({
  language: 'en-US',
  voice: 'default',
  speed: 1.0,
  pitch: 1.0,
  autoListen: false
})

const availableVoices = ref<string[]>(['default'])
const conversationHistory = ref<{ role: 'user' | 'assistant'; text: string; timestamp: Date }[]>([])

// Speech Recognition browser API types
interface SpeechRecognitionResult {
  readonly isFinal: boolean
  readonly [index: number]: { readonly transcript: string }
}

interface SpeechRecognitionResultList {
  readonly length: number
  readonly [index: number]: SpeechRecognitionResult
}

interface SpeechRecognitionEvent {
  readonly resultIndex: number
  readonly results: SpeechRecognitionResultList
}

interface SpeechRecognitionErrorEvent {
  readonly error: string
}

interface SpeechRecognitionInstance {
  continuous: boolean
  interimResults: boolean
  lang: string
  onstart: (() => void) | null
  onresult: ((event: SpeechRecognitionEvent) => void) | null
  onend: (() => void) | null
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null
  start(): void
  stop(): void
  abort(): void
}

let recognition: SpeechRecognitionInstance | null = null

function initSpeechRecognition(): void {
  if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
    error.value = 'Speech recognition is not supported in this browser'
    return
  }

  const SpeechRecognitionCtor = (window as unknown as Record<string, new () => SpeechRecognitionInstance>).SpeechRecognition
    || (window as unknown as Record<string, new () => SpeechRecognitionInstance>).webkitSpeechRecognition
  recognition = new SpeechRecognitionCtor()

  recognition.continuous = false
  recognition.interimResults = true
  recognition.lang = settings.value.language

  recognition.onstart = () => {
    isListening.value = true
    transcript.value = ''
    error.value = null
  }

  recognition.onresult = (event: SpeechRecognitionEvent) => {
    let interimTranscript = ''
    let finalTranscript = ''

    for (let i = event.resultIndex; i < event.results.length; i++) {
      const transcriptPart = event.results[i][0].transcript
      if (event.results[i].isFinal) {
        finalTranscript += transcriptPart
      } else {
        interimTranscript += transcriptPart
      }
    }

    transcript.value = finalTranscript || interimTranscript
  }

  recognition.onend = () => {
    isListening.value = false
    if (transcript.value) {
      processVoiceInput()
    }
  }

  recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
    isListening.value = false
    error.value = `Speech recognition error: ${event.error}`
  }
}

function startListening(): void {
  if (!recognition) {
    initSpeechRecognition()
  }
  if (recognition) {
    recognition.start()
  }
}

function stopListening(): void {
  if (recognition) {
    recognition.stop()
  }
}

function toggleListening(): void {
  if (isListening.value) {
    stopListening()
  } else {
    startListening()
  }
}

async function processVoiceInput(): Promise<void> {
  if (!transcript.value.trim()) return

  // Add to history
  conversationHistory.value.push({
    role: 'user',
    text: transcript.value,
    timestamp: new Date()
  })

  loading.value = true

  try {
    // Send to AI backend - Issue #835
    const response = await api.voiceSpeak(transcript.value)

    const responseText = typeof response.response === 'string' ? response.response
      : typeof response.text === 'string' ? response.text
      : 'No response received'
    aiResponse.value = responseText

    // Add AI response to history
    conversationHistory.value.push({
      role: 'assistant',
      text: aiResponse.value,
      timestamp: new Date()
    })

    // Speak response
    speakText(aiResponse.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to process voice input'
  } finally {
    loading.value = false
  }
}

function speakText(text: string): void {
  if (!('speechSynthesis' in window)) {
    error.value = 'Speech synthesis is not supported in this browser'
    return
  }

  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = settings.value.language
  utterance.rate = settings.value.speed
  utterance.pitch = settings.value.pitch

  utterance.onstart = () => {
    isSpeaking.value = true
  }

  utterance.onend = () => {
    isSpeaking.value = false
    if (settings.value.autoListen) {
      startListening()
    }
  }

  utterance.onerror = () => {
    isSpeaking.value = false
    error.value = 'Speech synthesis failed'
  }

  speechSynthesis.speak(utterance)
}

function stopSpeaking(): void {
  speechSynthesis.cancel()
  isSpeaking.value = false
}

function clearHistory(): void {
  conversationHistory.value = []
  transcript.value = ''
  aiResponse.value = ''
}

function loadVoices(): void {
  const voices = speechSynthesis.getVoices()
  availableVoices.value = voices.map(v => v.name)
}

onMounted(() => {
  initSpeechRecognition()
  loadVoices()
  speechSynthesis.onvoiceschanged = loadVoices
})

onUnmounted(() => {
  if (recognition) {
    recognition.abort()
  }
  speechSynthesis.cancel()
})
</script>

<template>
  <div class="p-6 h-full flex flex-col">
    <div class="flex gap-6 flex-1 overflow-hidden">
      <!-- Main Panel -->
      <div class="flex-1 bg-white rounded-lg shadow-xs border border-autobot-border flex flex-col overflow-hidden">
        <!-- Header -->
        <div class="bg-autobot-bg-secondary border-b border-autobot-border px-6 py-4">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
              <div class="p-2 bg-autobot-illus-2-tint rounded-lg">
                <svg class="w-6 h-6 text-autobot-illus-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                </svg>
              </div>
              <div>
                <h2 class="text-lg font-semibold text-autobot-text-primary">{{ $t('tools.admin.voiceTool.voiceInterface') }}</h2>
                <p class="text-sm text-autobot-text-tertiary">{{ $t('tools.admin.voiceTool.speakToInteractWith') }}</p>
              </div>
            </div>

            <div class="flex items-center gap-4">
              <!-- Status Indicators -->
              <div class="flex items-center gap-4 text-sm">
                <div class="flex items-center gap-2">
                  <div
                    class="w-2 h-2 rounded-full"
                    :class="isListening ? 'bg-autobot-dot-bad animate-pulse' : 'bg-autobot-dot-idle'"
                  ></div>
                  <span class="text-autobot-text-secondary">{{ isListening ? $t('tools.admin.voiceTool.listening') : $t('tools.admin.voiceTool.notListening') }}</span>
                </div>
                <div class="flex items-center gap-2">
                  <div
                    class="w-2 h-2 rounded-full"
                    :class="isSpeaking ? 'bg-autobot-dot-ok animate-pulse' : 'bg-autobot-dot-idle'"
                  ></div>
                  <span class="text-autobot-text-secondary">{{ isSpeaking ? $t('tools.admin.voiceTool.speaking') : $t('tools.admin.voiceTool.silent') }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Error Message -->
        <BaseAlert v-if="error" variant="error" class="mx-6 mt-4" :message="error" />

        <!-- Voice Control Center -->
        <div class="flex-1 flex flex-col items-center justify-center p-6">
          <!-- Main Listen Button -->
          <button
            @click="toggleListening"
            :disabled="loading || isSpeaking"
            :class="[
              'w-32 h-32 rounded-full flex items-center justify-center transition-all transform hover:scale-105',
              isListening
                ? 'bg-autobot-dot-bad hover:bg-autobot-error-solid ring-4 ring-autobot-error'
                : 'bg-primary-600 hover:bg-primary-700'
            ]"
          >
            <svg v-if="isListening" class="w-12 h-12 text-white" fill="currentColor" viewBox="0 0 24 24">
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
            <svg v-else class="w-12 h-12 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
            </svg>
          </button>

          <p class="mt-4 text-autobot-text-secondary">
            {{ isListening ? $t('tools.admin.voiceTool.listeningClickToStop') : $t('tools.admin.voiceTool.clickToStartListening') }}
          </p>

          <!-- Transcript Display -->
          <div v-if="transcript" class="mt-6 p-4 bg-autobot-bg-tertiary rounded-lg max-w-lg w-full">
            <p class="text-sm text-autobot-text-tertiary mb-1">{{ $t('tools.admin.voiceTool.youSaid') }}</p>
            <p class="text-autobot-text-primary">{{ transcript }}</p>
          </div>

          <!-- AI Response -->
          <div v-if="aiResponse" class="mt-4 p-4 bg-primary-50 rounded-lg max-w-lg w-full">
            <div class="flex items-center justify-between mb-1">
              <p class="text-sm text-primary-600">{{ $t('tools.admin.voiceTool.aIResponse') }}</p>
              <button
                v-if="isSpeaking"
                @click="stopSpeaking"
                class="text-xs text-autobot-error hover:text-autobot-pill-bad-fg"
              >
                {{ $t('tools.admin.voiceTool.stopSpeaking') }}
              </button>
            </div>
            <p class="text-autobot-text-primary">{{ aiResponse }}</p>
          </div>

          <!-- Loading -->
          <div v-if="loading" class="mt-6 flex items-center gap-2 text-autobot-text-secondary">
            <svg class="animate-spin w-5 h-5" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span>{{ $t('tools.admin.voiceTool.processing') }}</span>
          </div>
        </div>

        <!-- Conversation History -->
        <div v-if="conversationHistory.length > 0" class="border-t border-autobot-border max-h-48 overflow-auto">
          <div class="p-4 space-y-2">
            <div class="flex items-center justify-between mb-2">
              <h3 class="text-sm font-medium text-autobot-text-secondary">{{ $t('tools.admin.voiceTool.conversationHistory') }}</h3>
              <button
                @click="clearHistory"
                class="text-xs text-autobot-text-tertiary hover:text-autobot-error"
              >
                {{ $t('tools.admin.voiceTool.clear') }}
              </button>
            </div>
            <div
              v-for="(msg, index) in conversationHistory"
              :key="index"
              :class="[
                'p-2 rounded-sm text-sm',
                msg.role === 'user' ? 'bg-autobot-bg-tertiary ml-8' : 'bg-primary-50 mr-8'
              ]"
            >
              <p class="text-xs text-autobot-text-tertiary mb-1">
                {{ msg.role === 'user' ? $t('tools.admin.voiceTool.you') : $t('tools.admin.voiceTool.aI') }} -
                {{ formatFleetTime(msg.timestamp) }}
              </p>
              <p class="text-autobot-text-primary">{{ msg.text }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Settings Panel -->
      <div class="w-80 bg-white rounded-lg shadow-xs border border-autobot-border p-6">
        <h3 class="text-lg font-semibold text-autobot-text-primary mb-4">{{ $t('tools.admin.voiceTool.voiceSettings') }}</h3>

        <div class="space-y-4">
          <!-- Language -->
          <div>
            <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('tools.admin.voiceTool.language') }}</label>
            <select
              v-model="settings.language"
              class="w-full px-3 py-2 border border-autobot-border-strong rounded-lg focus:ring-2 focus:ring-primary-500 text-sm"
            >
              <option value="en-US">{{ $t('tools.admin.voiceTool.englishUS') }}</option>
              <option value="en-GB">{{ $t('tools.admin.voiceTool.englishUK') }}</option>
              <option value="es-ES">{{ $t('tools.admin.voiceTool.spanish') }}</option>
              <option value="fr-FR">{{ $t('tools.admin.voiceTool.french') }}</option>
              <option value="de-DE">{{ $t('tools.admin.voiceTool.german') }}</option>
              <option value="it-IT">{{ $t('tools.admin.voiceTool.italian') }}</option>
              <option value="ja-JP">{{ $t('tools.admin.voiceTool.japanese') }}</option>
              <option value="zh-CN">{{ $t('tools.admin.voiceTool.chineseSimplified') }}</option>
            </select>
          </div>

          <!-- Speed -->
          <div>
            <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('tools.admin.voiceTool.speechSpeedValue0X', { value0: settings.speed.toFixed(1) }) }}</label>
            <input
              v-model.number="settings.speed"
              type="range"
              min="0.5"
              max="2"
              step="0.1"
              class="w-full"
            />
          </div>

          <!-- Pitch -->
          <div>
            <label class="block text-sm font-medium text-autobot-text-secondary mb-1">{{ $t('tools.admin.voiceTool.pitchValue0', { value0: settings.pitch.toFixed(1) }) }}</label>
            <input
              v-model.number="settings.pitch"
              type="range"
              min="0.5"
              max="2"
              step="0.1"
              class="w-full"
            />
          </div>

          <!-- Auto-listen -->
          <div class="flex items-center justify-between">
            <label class="text-sm font-medium text-autobot-text-secondary">{{ $t('tools.admin.voiceTool.autoListenAfterResponse') }}</label>
            <button
              @click="settings.autoListen = !settings.autoListen"
              :class="[
                'relative inline-flex h-6 w-11 items-center rounded-full transition-colors',
                settings.autoListen ? 'bg-primary-600' : 'bg-autobot-bg-active'
              ]"
            >
              <span
                :class="[
                  'inline-block h-4 w-4 transform rounded-full bg-white transition-transform',
                  settings.autoListen ? 'translate-x-6' : 'translate-x-1'
                ]"
              />
            </button>
          </div>
        </div>

        <!-- Tips -->
        <div class="mt-6 p-4 bg-autobot-bg-secondary rounded-lg">
          <h4 class="text-sm font-medium text-autobot-text-primary mb-2">{{ $t('tools.admin.voiceTool.tips') }}</h4>
          <ul class="text-xs text-autobot-text-secondary space-y-1">
            <li>{{ $t('tools.admin.voiceTool.speakClearlyAndAt') }}</li>
            <li>{{ $t('tools.admin.voiceTool.useAQuietEnvironment') }}</li>
            <li>{{ $t('tools.admin.voiceTool.grantMicrophonePermissionsWhen') }}</li>
            <li>{{ $t('tools.admin.voiceTool.tryDifferentLanguagesFor') }}</li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>
