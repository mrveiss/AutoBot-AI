// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * VisionTool - Vision & Multimodal Interface
 *
 * AI-powered vision and multimodal processing.
 * Migrated from main AutoBot frontend - Issue #729.
 */

import { ref, computed } from 'vue'
import { useAutobotApi } from '@/composables/useAutobotApi'

const api = useAutobotApi()

// State
const loading = ref(false)
const error = ref<string | null>(null)
const activeTab = ref<'capture' | 'analyze' | 'history'>('capture')

// Image capture
const imageSource = ref<'upload' | 'camera' | 'screen'>('upload')
const capturedImage = ref<string | null>(null)
const analysisResult = ref<string | null>(null)
const analysisPrompt = ref('Describe this image in detail.')

interface AnalysisHistory {
  id: string
  timestamp: Date
  image: string
  prompt: string
  result: string
}

const history = ref<AnalysisHistory[]>([])

// File upload
const fileInput = ref<HTMLInputElement | null>(null)

function triggerFileUpload(): void {
  fileInput.value?.click()
}

function handleFileUpload(event: Event): void {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return

  const reader = new FileReader()
  reader.onload = (e) => {
    capturedImage.value = e.target?.result as string
  }
  reader.readAsDataURL(file)
}

async function captureScreen(): Promise<void> {
  loading.value = true
  error.value = null

  try {
    const data = await api.get('/vision/capture-screen')
    capturedImage.value = `data:image/png;base64,${data.screenshot}`
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to capture screen'
  } finally {
    loading.value = false
  }
}

async function captureCamera(): Promise<void> {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true })
    const video = document.createElement('video')
    video.srcObject = stream

    await video.play()

    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    const ctx = canvas.getContext('2d')
    ctx?.drawImage(video, 0, 0)

    capturedImage.value = canvas.toDataURL('image/png')

    stream.getTracks().forEach(track => track.stop())
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to access camera'
  }
}

async function analyzeImage(): Promise<void> {
  if (!capturedImage.value) {
    error.value = 'Please capture or upload an image first'
    return
  }

  loading.value = true
  error.value = null
  analysisResult.value = null

  try {
    const base64 = capturedImage.value.split(',')[1] || capturedImage.value
    const data = await api.post('/vision/analyze', {
      image: base64,
      prompt: analysisPrompt.value
    })

    analysisResult.value = data.analysis || data.description || 'No analysis available'

    // Add to history
    history.value.unshift({
      id: `analysis-${Date.now()}`,
      timestamp: new Date(),
      image: capturedImage.value,
      prompt: analysisPrompt.value,
      result: analysisResult.value
    })

    // Keep only last 10 items
    if (history.value.length > 10) {
      history.value = history.value.slice(0, 10)
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Analysis failed'
  } finally {
    loading.value = false
  }
}

function clearImage(): void {
  capturedImage.value = null
  analysisResult.value = null
}

function loadFromHistory(item: AnalysisHistory): void {
  capturedImage.value = item.image
  analysisPrompt.value = item.prompt
  analysisResult.value = item.result
  activeTab.value = 'analyze'
}
</script>

<template>
  <div class="p-6 h-full flex flex-col">
    <div class="flex gap-6 flex-1 overflow-hidden">
      <!-- Main Panel -->
      <div class="flex-1 bg-white rounded-lg shadow-sm border border-gray-200 flex flex-col overflow-hidden">
        <!-- Tabs -->
        <div class="border-b border-gray-200">
          <nav class="flex">
            <button
              @click="activeTab = 'capture'"
              :class="[
                'px-6 py-4 text-sm font-medium border-b-2 transition-colors',
                activeTab === 'capture'
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              ]"
            >
              <svg class="w-4 h-4 inline mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
              </svg>
              Capture
            </button>
            <button
              @click="activeTab = 'analyze'"
              :class="[
                'px-6 py-4 text-sm font-medium border-b-2 transition-colors',
                activeTab === 'analyze'
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              ]"
            >
              <svg class="w-4 h-4 inline mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              </svg>
              Analyze
            </button>
            <button
              @click="activeTab = 'history'"
              :class="[
                'px-6 py-4 text-sm font-medium border-b-2 transition-colors',
                activeTab === 'history'
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              ]"
            >
              <svg class="w-4 h-4 inline mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              History
            </button>
          </nav>
        </div>

        <!-- Error Message -->
        <div v-if="error" class="mx-6 mt-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {{ error }}
        </div>

        <!-- Capture Tab -->
        <div v-if="activeTab === 'capture'" class="flex-1 p-6 overflow-auto">
          <div class="max-w-2xl mx-auto">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Capture Image</h3>

            <!-- Source Selection -->
            <div class="flex gap-4 mb-6">
              <button
                @click="imageSource = 'upload'"
                :class="[
                  'flex-1 p-4 rounded-lg border-2 transition-colors',
                  imageSource === 'upload'
                    ? 'border-primary-500 bg-primary-50'
                    : 'border-gray-200 hover:border-gray-300'
                ]"
              >
                <svg class="w-8 h-8 mx-auto mb-2 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                <p class="text-sm font-medium text-gray-900">Upload File</p>
              </button>

              <button
                @click="imageSource = 'camera'"
                :class="[
                  'flex-1 p-4 rounded-lg border-2 transition-colors',
                  imageSource === 'camera'
                    ? 'border-primary-500 bg-primary-50'
                    : 'border-gray-200 hover:border-gray-300'
                ]"
              >
                <svg class="w-8 h-8 mx-auto mb-2 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                </svg>
                <p class="text-sm font-medium text-gray-900">Camera</p>
              </button>

              <button
                @click="imageSource = 'screen'"
                :class="[
                  'flex-1 p-4 rounded-lg border-2 transition-colors',
                  imageSource === 'screen'
                    ? 'border-primary-500 bg-primary-50'
                    : 'border-gray-200 hover:border-gray-300'
                ]"
              >
                <svg class="w-8 h-8 mx-auto mb-2 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
                <p class="text-sm font-medium text-gray-900">Screen Capture</p>
              </button>
            </div>

            <!-- Action Buttons -->
            <div class="flex gap-4 mb-6">
              <input
                ref="fileInput"
                type="file"
                accept="image/*"
                @change="handleFileUpload"
                class="hidden"
              />

              <button
                v-if="imageSource === 'upload'"
                @click="triggerFileUpload"
                class="flex-1 px-6 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
              >
                Select Image File
              </button>

              <button
                v-if="imageSource === 'camera'"
                @click="captureCamera"
                :disabled="loading"
                class="flex-1 px-6 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50"
              >
                {{ loading ? 'Capturing...' : 'Capture from Camera' }}
              </button>

              <button
                v-if="imageSource === 'screen'"
                @click="captureScreen"
                :disabled="loading"
                class="flex-1 px-6 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50"
              >
                {{ loading ? 'Capturing...' : 'Capture Screen' }}
              </button>
            </div>

            <!-- Preview -->
            <div v-if="capturedImage" class="border border-gray-200 rounded-lg p-4">
              <div class="flex items-center justify-between mb-4">
                <h4 class="font-medium text-gray-900">Preview</h4>
                <div class="flex gap-2">
                  <button
                    @click="clearImage"
                    class="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800"
                  >
                    Clear
                  </button>
                  <button
                    @click="activeTab = 'analyze'"
                    class="px-3 py-1.5 text-sm bg-primary-600 text-white rounded hover:bg-primary-700"
                  >
                    Analyze
                  </button>
                </div>
              </div>
              <img :src="capturedImage" alt="Captured" class="max-w-full rounded-lg" />
            </div>
          </div>
        </div>

        <!-- Analyze Tab -->
        <div v-if="activeTab === 'analyze'" class="flex-1 p-6 overflow-auto">
          <div class="max-w-3xl mx-auto">
            <h3 class="text-lg font-semibold text-gray-900 mb-4">Analyze Image</h3>

            <div v-if="!capturedImage" class="text-center py-12 bg-gray-50 rounded-lg">
              <svg class="w-12 h-12 mx-auto text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              <p class="mt-4 text-gray-600">No image captured. Go to Capture tab first.</p>
            </div>

            <div v-else class="space-y-6">
              <!-- Image Display -->
              <div class="border border-gray-200 rounded-lg p-4">
                <img :src="capturedImage" alt="Analysis target" class="max-w-full max-h-64 mx-auto rounded-lg" />
              </div>

              <!-- Analysis Prompt -->
              <div>
                <label class="block text-sm font-medium text-gray-700 mb-2">Analysis Prompt</label>
                <textarea
                  v-model="analysisPrompt"
                  rows="3"
                  class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                  placeholder="Enter your analysis prompt..."
                ></textarea>
              </div>

              <!-- Analyze Button -->
              <button
                @click="analyzeImage"
                :disabled="loading"
                class="w-full px-6 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
              >
                <svg v-if="loading" class="animate-spin w-5 h-5" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                {{ loading ? 'Analyzing...' : 'Analyze Image' }}
              </button>

              <!-- Analysis Result -->
              <div v-if="analysisResult" class="bg-primary-50 border border-primary-200 rounded-lg p-6">
                <h4 class="font-medium text-primary-900 mb-2">Analysis Result</h4>
                <p class="text-primary-800 whitespace-pre-wrap">{{ analysisResult }}</p>
              </div>
            </div>
          </div>
        </div>

        <!-- History Tab -->
        <div v-if="activeTab === 'history'" class="flex-1 p-6 overflow-auto">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">Analysis History</h3>

          <div v-if="history.length === 0" class="text-center py-12 bg-gray-50 rounded-lg">
            <svg class="w-12 h-12 mx-auto text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p class="mt-4 text-gray-600">No analysis history yet</p>
          </div>

          <div v-else class="space-y-4">
            <div
              v-for="item in history"
              :key="item.id"
              @click="loadFromHistory(item)"
              class="bg-white border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow cursor-pointer"
            >
              <div class="flex gap-4">
                <img :src="item.image" alt="History" class="w-24 h-24 object-cover rounded-lg" />
                <div class="flex-1">
                  <p class="text-xs text-gray-500 mb-1">{{ item.timestamp.toLocaleString() }}</p>
                  <p class="text-sm font-medium text-gray-900 mb-2">{{ item.prompt }}</p>
                  <p class="text-sm text-gray-600 line-clamp-2">{{ item.result }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
