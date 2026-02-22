// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * NoVNCTool - noVNC Remote Desktop Viewer
 *
 * Remote desktop access via noVNC WebSocket connection.
 * Supports both static SSOT hosts and dynamic SLM-managed VNC endpoints.
 * Related to Issue #725, #729.
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { getVNCHosts } from '@/config/ssot-config'
import { useSlmApi } from '@/composables/useSlmApi'
import { useVncControls } from '@/composables/useVncControls'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('NoVNCTool')
const api = useSlmApi()

// VNC controls (Issue #74)
const vncControls = useVncControls()
const showScreenshotModal = ref(false)
const screenshotData = ref<string | null>(null)
const textToType = ref('')
const showTypeDialog = ref(false)

// State
const loading = ref(false)
const loadingEndpoints = ref(false)
const error = ref<string | null>(null)
const isConnected = ref(false)
const isFullscreen = ref(false)

interface VNCHost {
  id: string
  name: string
  host: string
  port: number
  description: string
  source: 'static' | 'dynamic'
}

// Start with static SSOT hosts
const staticHosts = getVNCHosts().map(h => ({ ...h, source: 'static' as const }))
const dynamicHosts = ref<VNCHost[]>([])

// Combined hosts (static + dynamic from SLM API)
const hosts = computed(() => [...staticHosts, ...dynamicHosts.value])

const selectedHost = ref<string>(staticHosts[0]?.id || '')
const currentHost = computed(() => hosts.value.find(h => h.id === selectedHost.value))

// VNC URL
// Issue #1002: nginx proxies /tools/novnc/ → http://backend:6080/ for the main host.
// Using the proxy path avoids mixed-content blocking (HTTP iframe in HTTPS page).
// Dynamic/non-main hosts fall back to a new-tab link since no proxy exists for them.
const vncUrl = computed(() => {
  if (!currentHost.value) return ''
  if (currentHost.value.id === 'main') {
    return `/tools/novnc/vnc.html?autoconnect=true&resize=scale`
  }
  return `http://${currentHost.value.host}:${currentHost.value.port}/vnc.html?autoconnect=true&resize=scale`
})

// Whether the current host can be embedded (proxied) vs needs a new tab
const canEmbedHost = computed(() => currentHost.value?.id === 'main')

async function fetchDynamicEndpoints(): Promise<void> {
  loadingEndpoints.value = true
  try {
    const response = await api.getVncEndpoints()
    dynamicHosts.value = response.endpoints.map(ep => ({
      id: `slm-${ep.credential_id}`,
      name: ep.name || `${ep.hostname} (${ep.vnc_type})`,
      host: ep.ip_address,
      port: ep.port,
      description: `SLM-managed VNC on ${ep.hostname}`,
      source: 'dynamic' as const,
    }))
  } catch (e) {
    // API not available - continue with static hosts only
    logger.warn('VNC endpoints API not available:', e)
  } finally {
    loadingEndpoints.value = false
  }
}

function connect(): void {
  if (!currentHost.value) {
    error.value = 'Please select a host'
    return
  }

  loading.value = true
  error.value = null

  // VNC connection is handled by iframe
  setTimeout(() => {
    isConnected.value = true
    loading.value = false
  }, 1000)
}

function disconnect(): void {
  isConnected.value = false
}

function toggleFullscreen(): void {
  const iframe = document.getElementById('vnc-frame') as HTMLIFrameElement
  if (!iframe) return

  if (!document.fullscreenElement) {
    iframe.requestFullscreen()
    isFullscreen.value = true
  } else {
    document.exitFullscreen()
    isFullscreen.value = false
  }
}

function handleFullscreenChange(): void {
  isFullscreen.value = !!document.fullscreenElement
}

// Desktop interaction actions (Issue #74)
async function takeScreenshot(): Promise<void> {
  const result = await vncControls.captureScreenshot()
  if (result.status === 'success' && result.image_data) {
    screenshotData.value = `data:image/png;base64,${result.image_data}`
    showScreenshotModal.value = true
  } else {
    logger.error('Screenshot failed:', result.message)
    error.value = result.message
  }
}

async function handleTypeText(): Promise<void> {
  if (!textToType.value.trim()) return

  const result = await vncControls.keyboardType(textToType.value)
  if (result.status === 'success') {
    textToType.value = ''
    showTypeDialog.value = false
  } else {
    logger.error('Type text failed:', result.message)
    error.value = result.message
  }
}

async function sendCtrlAltDel(): Promise<void> {
  const result = await vncControls.sendCtrlAltDel()
  if (result.status !== 'success') {
    logger.error('Ctrl+Alt+Del failed:', result.message)
    error.value = result.message
  }
}

async function pasteFromClipboard(): Promise<void> {
  try {
    const text = await navigator.clipboard.readText()
    const result = await vncControls.syncClipboard(text)
    if (result.status !== 'success') {
      logger.error('Clipboard sync failed:', result.message)
      error.value = result.message
    }
  } catch (err) {
    logger.error('Clipboard read failed:', err)
    error.value = 'Failed to read clipboard'
  }
}

function downloadScreenshot(): void {
  if (!screenshotData.value) return

  const link = document.createElement('a')
  link.href = screenshotData.value
  link.download = `desktop-screenshot-${Date.now()}.png`
  link.click()
}

onMounted(() => {
  document.addEventListener('fullscreenchange', handleFullscreenChange)
  fetchDynamicEndpoints()
})

onUnmounted(() => {
  document.removeEventListener('fullscreenchange', handleFullscreenChange)
})
</script>

<template>
  <div class="p-6 h-full flex flex-col">
    <!-- VNC Container -->
    <div class="bg-white rounded-lg shadow-sm border border-gray-200 flex-1 flex flex-col overflow-hidden">
      <!-- Header -->
      <div class="bg-gray-100 border-b border-gray-200 px-4 py-3 flex items-center justify-between">
        <div class="flex items-center gap-4">
          <div class="flex items-center gap-2">
            <svg class="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
            <span class="font-medium text-gray-900">noVNC Remote Desktop</span>
          </div>

          <!-- Host Selector -->
          <select
            v-model="selectedHost"
            :disabled="isConnected || loadingEndpoints"
            class="text-sm px-3 py-1.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 disabled:opacity-50"
          >
            <optgroup v-if="staticHosts.length > 0" label="Static Hosts">
              <option v-for="host in staticHosts" :key="host.id" :value="host.id">
                {{ host.name }} ({{ host.host }}:{{ host.port }})
              </option>
            </optgroup>
            <optgroup v-if="dynamicHosts.length > 0" label="SLM-Managed">
              <option v-for="host in dynamicHosts" :key="host.id" :value="host.id">
                {{ host.name }} ({{ host.host }}:{{ host.port }})
              </option>
            </optgroup>
          </select>

          <!-- Refresh Button -->
          <button
            @click="fetchDynamicEndpoints"
            :disabled="loadingEndpoints || isConnected"
            class="p-1.5 text-gray-500 hover:bg-gray-200 rounded transition-colors disabled:opacity-50"
            title="Refresh VNC endpoints"
          >
            <svg
              class="w-4 h-4"
              :class="{ 'animate-spin': loadingEndpoints }"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>

          <!-- Connection Status -->
          <div class="flex items-center gap-2">
            <div
              class="w-2 h-2 rounded-full"
              :class="isConnected ? 'bg-green-500' : 'bg-red-500'"
            ></div>
            <span class="text-xs text-gray-600">{{ isConnected ? 'Connected' : 'Disconnected' }}</span>
          </div>

          <!-- Dynamic Badge -->
          <span
            v-if="currentHost?.source === 'dynamic'"
            class="px-2 py-0.5 text-xs font-medium bg-blue-100 text-blue-700 rounded"
          >
            SLM
          </span>
        </div>

        <div class="flex items-center gap-2">
          <!-- Connect/Disconnect -->
          <button
            @click="isConnected ? disconnect() : connect()"
            :disabled="loading || !selectedHost"
            :class="[
              'px-4 py-1.5 text-sm font-medium rounded-lg transition-colors',
              isConnected
                ? 'bg-red-100 text-red-700 hover:bg-red-200'
                : 'bg-green-100 text-green-700 hover:bg-green-200'
            ]"
          >
            <span v-if="loading">Connecting...</span>
            <span v-else>{{ isConnected ? 'Disconnect' : 'Connect' }}</span>
          </button>

          <!-- Fullscreen -->
          <button
            @click="toggleFullscreen"
            :disabled="!isConnected"
            class="p-2 text-gray-600 hover:bg-gray-200 rounded-lg transition-colors disabled:opacity-50"
            title="Toggle Fullscreen"
          >
            <svg v-if="!isFullscreen" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
            </svg>
            <svg v-else class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      <!-- Error Message -->
      <div v-if="error" class="m-4 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
        {{ error }}
      </div>

      <!-- VNC Viewport -->
      <div class="flex-1 bg-gray-900 overflow-hidden">
        <div v-if="loading" class="h-full flex items-center justify-center">
          <div class="text-center">
            <svg class="animate-spin w-8 h-8 mx-auto text-white" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <p class="mt-4 text-gray-400">Connecting to {{ currentHost?.name }}...</p>
          </div>
        </div>

        <div v-else-if="!isConnected" class="h-full flex items-center justify-center">
          <div class="text-center p-8">
            <svg class="w-16 h-16 mx-auto text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
            <h3 class="mt-4 text-lg font-medium text-gray-300">noVNC Remote Desktop</h3>
            <p class="mt-2 text-gray-500">Select a host and click Connect to start a VNC session</p>
            <div v-if="currentHost" class="mt-4 p-4 bg-gray-800 rounded-lg">
              <p class="text-sm text-gray-400">{{ currentHost.description }}</p>
              <p class="text-xs text-gray-500 mt-2 font-mono">{{ currentHost.host }}:{{ currentHost.port }}</p>
            </div>
            <div v-if="dynamicHosts.length > 0" class="mt-4 text-xs text-gray-500">
              {{ dynamicHosts.length }} SLM-managed VNC endpoint(s) available
            </div>
          </div>
        </div>

        <!-- Issue #1002: Embedded iframe for proxied main host; new-tab link for others -->
        <iframe
          v-else-if="canEmbedHost"
          id="vnc-frame"
          :src="vncUrl"
          class="w-full h-full border-0"
          allow="fullscreen"
        ></iframe>
        <div v-else class="h-full flex items-center justify-center">
          <div class="text-center p-8">
            <svg class="w-12 h-12 mx-auto text-gray-500 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
            <p class="text-gray-300 mb-4">This host requires a direct connection</p>
            <a
              :href="vncUrl"
              target="_blank"
              rel="noopener"
              class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              Open noVNC in New Tab
            </a>
          </div>
        </div>
      </div>
    </div>

    <!-- Info Panel -->
    <div class="mt-4 p-4 bg-gray-100 rounded-lg">
      <h3 class="text-sm font-medium text-gray-900 mb-2">Connection Info</h3>
      <div class="grid grid-cols-2 gap-4 text-sm">
        <div>
          <span class="text-gray-500">Host:</span>
          <span class="ml-2 text-gray-900 font-mono">{{ currentHost?.host || 'Not selected' }}</span>
        </div>
        <div>
          <span class="text-gray-500">Port:</span>
          <span class="ml-2 text-gray-900 font-mono">{{ currentHost?.port || '-' }}</span>
        </div>
        <div>
          <span class="text-gray-500">Status:</span>
          <span :class="isConnected ? 'text-green-600' : 'text-red-600'" class="ml-2">
            {{ isConnected ? 'Connected' : 'Disconnected' }}
          </span>
        </div>
        <div>
          <span class="text-gray-500">Source:</span>
          <span class="ml-2 text-gray-900">
            {{ currentHost?.source === 'dynamic' ? 'SLM-Managed' : 'Static Config' }}
          </span>
        </div>
      </div>
    </div>

    <!-- Desktop Actions Toolbar (Issue #74) -->
    <div v-if="isConnected" class="mt-4 p-4 bg-gray-50 rounded-lg border border-gray-200">
      <h3 class="text-sm font-medium text-gray-900 mb-3">Desktop Actions</h3>
      <div class="flex items-center gap-2 flex-wrap">
        <button @click="takeScreenshot" class="action-btn" title="Take Screenshot">
          📷 Screenshot
        </button>
        <button @click="showTypeDialog = true" class="action-btn" title="Type Text">
          ⌨️ Type Text
        </button>
        <button @click="sendCtrlAltDel" class="action-btn" title="Send Ctrl+Alt+Del">
          🔴 Ctrl+Alt+Del
        </button>
        <button @click="pasteFromClipboard" class="action-btn" title="Paste Clipboard">
          📋 Paste
        </button>
      </div>
    </div>

    <!-- Screenshot Modal (Issue #74) -->
    <Teleport to="body">
      <div v-if="showScreenshotModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-75" @click="showScreenshotModal = false">
        <div class="bg-white rounded-lg shadow-xl max-w-4xl max-h-[90vh] flex flex-col" @click.stop>
          <div class="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
            <h3 class="text-lg font-semibold text-gray-900">Desktop Screenshot</h3>
            <button @click="showScreenshotModal = false" class="text-2xl text-gray-500 hover:text-gray-700 transition-colors">×</button>
          </div>
          <div class="p-6 overflow-auto flex-1">
            <img v-if="screenshotData" :src="screenshotData" alt="Desktop Screenshot" class="max-w-full h-auto rounded-lg shadow-lg" />
          </div>
          <div class="px-6 py-4 border-t border-gray-200 flex items-center justify-end gap-2">
            <button @click="downloadScreenshot" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded transition-colors">
              💾 Download
            </button>
            <button @click="showScreenshotModal = false" class="px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-700 rounded transition-colors">
              Close
            </button>
          </div>
        </div>
      </div>

      <!-- Type Text Dialog (Issue #74) -->
      <div v-if="showTypeDialog" class="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" @click="showTypeDialog = false">
        <div class="bg-white rounded-lg shadow-xl w-full max-w-md" @click.stop>
          <div class="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
            <h3 class="text-lg font-semibold text-gray-900">Type Text on Desktop</h3>
            <button @click="showTypeDialog = false" class="text-2xl text-gray-500 hover:text-gray-700 transition-colors">×</button>
          </div>
          <div class="p-6">
            <textarea
              v-model="textToType"
              placeholder="Enter text to type on the desktop..."
              class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
              rows="4"
            ></textarea>
          </div>
          <div class="px-6 py-4 border-t border-gray-200 flex items-center justify-end gap-2">
            <button @click="handleTypeText" :disabled="!textToType.trim()" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
              ⌨️ Type
            </button>
            <button @click="showTypeDialog = false" class="px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-700 rounded transition-colors">
              Cancel
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.action-btn {
  @apply px-3 py-1.5 text-sm bg-blue-100 hover:bg-blue-200 text-blue-700 rounded border border-blue-300 transition-colors;
}
</style>
