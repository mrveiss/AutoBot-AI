// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('BrowserTool')
/**
 * BrowserTool - Browser Automation Interface
 *
 * Control the Playwright-based browser automation system.
 * Migrated from main AutoBot frontend - Issue #729.
 */

import { ref, onMounted } from 'vue'
import { useAutobotApi } from '@/composables/useAutobotApi'

const api = useAutobotApi()

// State
const loading = ref(false)
const error = ref<string | null>(null)
const url = ref('https://www.google.com')
const screenshot = ref<string | null>(null)
const browserStatus = ref<'disconnected' | 'connecting' | 'connected'>('disconnected')
const consoleOutput = ref<{ type: string; text: string }[]>([])

interface BrowserSession {
  id: string
  status: string
  url: string
  title: string
  created_at: string
}

const sessions = ref<BrowserSession[]>([])
const activeSession = ref<string | null>(null)

async function loadSessions(): Promise<void> {
  try {
    const data = await api.get('/browser/sessions')
    sessions.value = data.sessions || []
  } catch (e) {
    logger.error('Failed to load sessions:', e)
  }
}

async function createSession(): Promise<void> {
  loading.value = true
  error.value = null
  browserStatus.value = 'connecting'

  try {
    const data = await api.post('/browser/sessions', { url: url.value })
    activeSession.value = data.session_id
    browserStatus.value = 'connected'
    await loadSessions()
    await takeScreenshot()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to create session'
    browserStatus.value = 'disconnected'
  } finally {
    loading.value = false
  }
}

async function closeSession(): Promise<void> {
  if (!activeSession.value) return

  loading.value = true
  try {
    await api.delete(`/browser/sessions/${activeSession.value}`)
    activeSession.value = null
    screenshot.value = null
    browserStatus.value = 'disconnected'
    await loadSessions()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to close session'
  } finally {
    loading.value = false
  }
}

async function navigate(): Promise<void> {
  if (!activeSession.value || !url.value) return

  loading.value = true
  error.value = null

  try {
    await api.post(`/browser/sessions/${activeSession.value}/navigate`, { url: url.value })
    await takeScreenshot()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Navigation failed'
  } finally {
    loading.value = false
  }
}

async function takeScreenshot(): Promise<void> {
  if (!activeSession.value) return

  try {
    const data = await api.get(`/browser/sessions/${activeSession.value}/screenshot`)
    screenshot.value = data.screenshot || null
  } catch (e) {
    logger.error('Failed to take screenshot:', e)
  }
}

async function goBack(): Promise<void> {
  if (!activeSession.value) return
  try {
    await api.post(`/browser/sessions/${activeSession.value}/back`)
    await takeScreenshot()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to go back'
  }
}

async function goForward(): Promise<void> {
  if (!activeSession.value) return
  try {
    await api.post(`/browser/sessions/${activeSession.value}/forward`)
    await takeScreenshot()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to go forward'
  }
}

async function refresh(): Promise<void> {
  if (!activeSession.value) return
  try {
    await api.post(`/browser/sessions/${activeSession.value}/refresh`)
    await takeScreenshot()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Failed to refresh'
  }
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter') {
    navigate()
  }
}

onMounted(() => {
  loadSessions()
})
</script>

<template>
  <div class="p-6 h-full flex flex-col">
    <!-- Browser Container -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 flex-1 flex flex-col overflow-hidden">
      <!-- Browser Chrome -->
      <div class="bg-gray-100 border-b border-gray-200 px-4 py-2">
        <!-- Status Bar -->
        <div class="flex items-center gap-4 mb-2">
          <div class="flex items-center gap-2">
            <div
              class="w-2 h-2 rounded-full"
              :class="{
                'bg-green-500': browserStatus === 'connected',
                'bg-yellow-500 animate-pulse': browserStatus === 'connecting',
                'bg-red-500': browserStatus === 'disconnected'
              }"
            ></div>
            <span class="text-xs text-gray-600">{{ browserStatus }}</span>
          </div>

          <button
            v-if="browserStatus === 'disconnected'"
            @click="createSession"
            :disabled="loading"
            class="px-3 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700 transition-colors disabled:opacity-50"
          >
            Start Browser
          </button>
          <button
            v-else
            @click="closeSession"
            :disabled="loading"
            class="px-3 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700 transition-colors disabled:opacity-50"
          >
            Close Browser
          </button>
        </div>

        <!-- Navigation Bar -->
        <div class="flex items-center gap-2">
          <!-- Navigation Buttons -->
          <div class="flex items-center gap-1">
            <button
              @click="goBack"
              :disabled="!activeSession || loading"
              class="p-2 text-gray-600 hover:bg-gray-200 rounded-lg transition-colors disabled:opacity-50"
              title="Back"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <button
              @click="goForward"
              :disabled="!activeSession || loading"
              class="p-2 text-gray-600 hover:bg-gray-200 rounded-lg transition-colors disabled:opacity-50"
              title="Forward"
            >
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
              </svg>
            </button>
            <button
              @click="refresh"
              :disabled="!activeSession || loading"
              class="p-2 text-gray-600 hover:bg-gray-200 rounded-lg transition-colors disabled:opacity-50"
              title="Refresh"
            >
              <svg class="w-4 h-4" :class="{ 'animate-spin': loading }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
          </div>

          <!-- URL Bar -->
          <div class="flex-1 flex items-center gap-2">
            <div class="relative flex-1">
              <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
              </svg>
              <input
                v-model="url"
                @keydown="handleKeydown"
                type="text"
                class="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-full focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
                placeholder="Enter URL..."
              />
            </div>
            <button
              @click="navigate"
              :disabled="!activeSession || loading"
              class="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 text-sm"
            >
              Go
            </button>
          </div>

          <!-- Screenshot -->
          <button
            @click="takeScreenshot"
            :disabled="!activeSession || loading"
            class="p-2 text-gray-600 hover:bg-gray-200 rounded-lg transition-colors disabled:opacity-50"
            title="Take Screenshot"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </button>
        </div>
      </div>

      <!-- Error Message -->
      <div v-if="error" class="m-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
        {{ error }}
      </div>

      <!-- Browser Viewport -->
      <div class="flex-1 bg-gray-900 overflow-auto flex items-center justify-center">
        <div v-if="loading && !screenshot" class="text-center">
          <svg class="animate-spin w-8 h-8 mx-auto text-white" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <p class="mt-4 text-gray-400">Loading...</p>
        </div>

        <div v-else-if="!activeSession" class="text-center p-8">
          <svg class="w-16 h-16 mx-auto text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
          </svg>
          <h3 class="mt-4 text-lg font-medium text-gray-300">Browser Automation</h3>
          <p class="mt-2 text-gray-500">Click "Start Browser" to begin a new browser session</p>
        </div>

        <img
          v-else-if="screenshot"
          :src="`data:image/png;base64,${screenshot}`"
          alt="Browser Screenshot"
          class="max-w-full max-h-full object-contain"
        />

        <div v-else class="text-center p-8">
          <p class="text-gray-400">No screenshot available</p>
          <button
            @click="takeScreenshot"
            class="mt-4 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm"
          >
            Take Screenshot
          </button>
        </div>
      </div>
    </div>

    <!-- Sessions Panel -->
    <div v-if="sessions.length > 0" class="mt-4 bg-white rounded-lg shadow-sm border border-gray-200 p-4">
      <h3 class="text-sm font-medium text-gray-900 mb-3">Active Sessions</h3>
      <div class="flex flex-wrap gap-2">
        <div
          v-for="session in sessions"
          :key="session.id"
          :class="[
            'px-3 py-2 rounded-lg text-sm',
            session.id === activeSession
              ? 'bg-primary-100 text-primary-800 border border-primary-300'
              : 'bg-gray-100 text-gray-700'
          ]"
        >
          <span class="font-mono text-xs">{{ session.id.slice(0, 8) }}</span>
          <span class="mx-2">-</span>
          <span>{{ session.title || session.url }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
