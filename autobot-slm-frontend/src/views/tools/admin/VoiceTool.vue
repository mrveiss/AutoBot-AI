// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * VoiceTool - Voice Interface
 *
 * Voice input/output interface for AI interactions.
 * Migrated from main AutoBot frontend - Issue #729.
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
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

// Speech Recognition
let recognition: SpeechRecognition | null = null

function initSpeechRecognition(): void {
  if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
    error.value = 'Speech recognition is not supported in this browser'
    return
  }

  const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  recognition = new SpeechRecognition()

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

    aiResponse.value = (response.response as string) || (response.text as string) || 'No response received'

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
      <div class="flex-1 bg-white rounded-lg shadow-sm border border-gray-200 flex flex-col overflow-hidden">
        <!-- Header -->
        <div class="bg-gray-50 border-b border-gray-200 px-6 py-4">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
              <div class="p-2 bg-purple-100 rounded-lg">
                <svg class="w-6 h-6 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                </svg>
              </div>
              <div>
                <h2 class="text-lg font-semibold text-gray-900">Voice Interface</h2>
                <p class="text-sm text-gray-500">Speak to interact with the AI assistant</p>
              </div>
            </div>

            <div class="flex items-center gap-4">
              <!-- Status Indicators -->
              <div class="flex items-center gap-4 text-sm">
                <div class="flex items-center gap-2">
                  <div
                    class="w-2 h-2 rounded-full"
                    :class="isListening ? 'bg-red-500 animate-pulse' : 'bg-gray-400'"
                  ></div>
                  <span class="text-gray-600">{{ isListening ? 'Listening...' : 'Not listening' }}</span>
                </div>
                <div class="flex items-center gap-2">
                  <div
                    class="w-2 h-2 rounded-full"
                    :class="isSpeaking ? 'bg-green-500 animate-pulse' : 'bg-gray-400'"
                  ></div>
                  <span class="text-gray-600">{{ isSpeaking ? 'Speaking...' : 'Silent' }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Error Message -->
        <div v-if="error" class="mx-6 mt-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {{ error }}
        </div>

        <!-- Voice Control Center -->
        <div class="flex-1 flex flex-col items-center justify-center p-6">
          <!-- Main Listen Button -->
          <button
            @click="toggleListening"
            :disabled="loading || isSpeaking"
            :class="[
              'w-32 h-32 rounded-full flex items-center justify-center transition-all transform hover:scale-105',
              isListening
                ? 'bg-red-500 hover:bg-red-600 ring-4 ring-red-200'
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

          <p class="mt-4 text-gray-600">
            {{ isListening ? 'Listening... Click to stop' : 'Click to start listening' }}
          </p>

          <!-- Transcript Display -->
          <div v-if="transcript" class="mt-6 p-4 bg-gray-100 rounded-lg max-w-lg w-full">
            <p class="text-sm text-gray-500 mb-1">You said:</p>
            <p class="text-gray-900">{{ transcript }}</p>
          </div>

          <!-- AI Response -->
          <div v-if="aiResponse" class="mt-4 p-4 bg-primary-50 rounded-lg max-w-lg w-full">
            <div class="flex items-center justify-between mb-1">
              <p class="text-sm text-primary-600">AI Response:</p>
              <button
                v-if="isSpeaking"
                @click="stopSpeaking"
                class="text-xs text-red-600 hover:text-red-700"
              >
                Stop Speaking
              </button>
            </div>
            <p class="text-gray-900">{{ aiResponse }}</p>
          </div>

          <!-- Loading -->
          <div v-if="loading" class="mt-6 flex items-center gap-2 text-gray-600">
            <svg class="animate-spin w-5 h-5" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span>Processing...</span>
          </div>
        </div>

        <!-- Conversation History -->
        <div v-if="conversationHistory.length > 0" class="border-t border-gray-200 max-h-48 overflow-auto">
          <div class="p-4 space-y-2">
            <div class="flex items-center justify-between mb-2">
              <h3 class="text-sm font-medium text-gray-700">Conversation History</h3>
              <button
                @click="clearHistory"
                class="text-xs text-gray-500 hover:text-red-600"
              >
                Clear
              </button>
            </div>
            <div
              v-for="(msg, index) in conversationHistory"
              :key="index"
              :class="[
                'p-2 rounded text-sm',
                msg.role === 'user' ? 'bg-gray-100 ml-8' : 'bg-primary-50 mr-8'
              ]"
            >
              <p class="text-xs text-gray-500 mb-1">
                {{ msg.role === 'user' ? 'You' : 'AI' }} -
                {{ msg.timestamp.toLocaleTimeString() }}
              </p>
              <p class="text-gray-800">{{ msg.text }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Settings Panel -->
      <div class="w-80 bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <h3 class="text-lg font-semibold text-gray-900 mb-4">Voice Settings</h3>

        <div class="space-y-4">
          <!-- Language -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Language</label>
            <select
              v-model="settings.language"
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 text-sm"
            >
              <option value="en-US">English (US)</option>
              <option value="en-GB">English (UK)</option>
              <option value="es-ES">Spanish</option>
              <option value="fr-FR">French</option>
              <option value="de-DE">German</option>
              <option value="it-IT">Italian</option>
              <option value="ja-JP">Japanese</option>
              <option value="zh-CN">Chinese (Simplified)</option>
            </select>
          </div>

          <!-- Speed -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Speech Speed: {{ settings.speed.toFixed(1) }}x
            </label>
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
            <label class="block text-sm font-medium text-gray-700 mb-1">
              Pitch: {{ settings.pitch.toFixed(1) }}
            </label>
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
            <label class="text-sm font-medium text-gray-700">Auto-listen after response</label>
            <button
              @click="settings.autoListen = !settings.autoListen"
              :class="[
                'relative inline-flex h-6 w-11 items-center rounded-full transition-colors',
                settings.autoListen ? 'bg-primary-600' : 'bg-gray-200'
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
        <div class="mt-6 p-4 bg-gray-50 rounded-lg">
          <h4 class="text-sm font-medium text-gray-900 mb-2">Tips</h4>
          <ul class="text-xs text-gray-600 space-y-1">
            <li>Speak clearly and at a normal pace</li>
            <li>Use a quiet environment for best results</li>
            <li>Grant microphone permissions when prompted</li>
            <li>Try different languages for multilingual support</li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>
