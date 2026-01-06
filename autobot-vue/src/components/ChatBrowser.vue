<template>
  <div class="chat-browser-container">
    <!-- Browser Header with Session Info -->
    <div class="browser-header">
      <div class="flex items-center space-x-3">
        <div class="flex space-x-1">
          <div class="w-3 h-3 bg-red-500 rounded-full"></div>
          <div class="w-3 h-3 bg-yellow-500 rounded-full"></div>
          <div class="w-3 h-3 bg-green-500 rounded-full"></div>
        </div>

        <div class="flex items-center space-x-2 text-sm">
          <i class="fas fa-globe" :class="iconClass"></i>
          <span class="font-medium">Chat Browser</span>

          <!-- Session State Badge -->
          <div class="session-badge" :class="sessionBadgeClass">
            <i :class="sessionIcon"></i>
            <span class="text-xs font-semibold">{{ sessionStateText }}</span>
          </div>
        </div>

        <div class="text-xs text-gray-500">
          Chat: {{ chatSessionId?.slice(-8) || 'None' }} | Browser: {{ browserSessionId?.slice(-8) || 'Not Connected' }}
        </div>
      </div>

      <div class="flex items-center space-x-2">
        <!-- Connection Status -->
        <div class="flex items-center space-x-1">
          <div
            class="w-2 h-2 rounded-full"
            :class="connectionStatusClass"
          ></div>
          <span class="text-xs text-gray-600">{{ connectionStatusText }}</span>
        </div>

        <!-- Refresh Session Button -->
        <button
          @click="refreshSession"
          class="browser-btn"
          title="Refresh Browser Session"
          :disabled="isConnecting"
        >
          <i class="fas fa-sync" :class="{ 'fa-spin': isConnecting }"></i>
        </button>
      </div>
    </div>

    <!-- Browser Body -->
    <div class="browser-body">
      <PopoutChromiumBrowser
        v-if="browserSessionId"
        :key="browserSessionId"
        :session-id="browserSessionId"
        :chat-context="true"
        class="flex-1"
      />
      <div v-else class="flex-1 flex items-center justify-center bg-gray-100">
        <div class="text-center">
          <i class="fas fa-spinner fa-spin text-4xl text-gray-400 mb-4"></i>
          <p class="text-gray-500">{{ isConnecting ? 'Connecting to browser session...' : 'No chat session' }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import PopoutChromiumBrowser from '@/components/PopoutChromiumBrowser.vue'
import apiClient from '@/utils/ApiClient.js'

const logger = createLogger('ChatBrowser')

// Props
interface Props {
  chatSessionId: string | null
  autoConnect?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  autoConnect: true
})

// Browser session response type for type assertions
interface BrowserSessionResponse {
  session_id?: string
  current_url?: string | null
  interaction_required?: boolean
  browser_status?: string
  status?: string
}

// Refs
const browserSessionId = ref<string | null>(null)
const browserStatus = ref<string>('disconnected') // disconnected, connecting, connected, error
const currentUrl = ref<string | null>(null)
const interactionRequired = ref(false)
const isConnecting = ref(false)

// Computed
const connectionStatusText = computed(() => {
  const status = browserStatus.value
  return status.charAt(0).toUpperCase() + status.slice(1)
})

const connectionStatusClass = computed(() => ({
  'bg-green-500': browserStatus.value === 'connected',
  'bg-yellow-500': browserStatus.value === 'connecting',
  'bg-red-500': browserStatus.value === 'disconnected' || browserStatus.value === 'error'
}))

const sessionStateText = computed(() => {
  if (interactionRequired.value) return 'Interaction Required'
  if (browserStatus.value === 'connected') return 'Active'
  if (browserStatus.value === 'connecting') return 'Connecting'
  return 'Disconnected'
})

const sessionBadgeClass = computed(() => ({
  'bg-green-100 text-green-700': browserStatus.value === 'connected' && !interactionRequired.value,
  'bg-yellow-100 text-yellow-700': browserStatus.value === 'connecting' || interactionRequired.value,
  'bg-red-100 text-red-700': browserStatus.value === 'disconnected' || browserStatus.value === 'error'
}))

const sessionIcon = computed(() => {
  if (interactionRequired.value) return 'fas fa-hand-paper'
  if (browserStatus.value === 'connected') return 'fas fa-check-circle'
  if (browserStatus.value === 'connecting') return 'fas fa-spinner fa-spin'
  return 'fas fa-times-circle'
})

const iconClass = computed(() => ({
  'text-green-600': browserStatus.value === 'connected',
  'text-yellow-600': browserStatus.value === 'connecting',
  'text-red-600': browserStatus.value === 'disconnected' || browserStatus.value === 'error'
}))

// Retry configuration
const MAX_RETRIES = 3
const RETRY_DELAY_MS = 2000
let retryCount = 0

// Methods
const connectBrowserSession = async (retry = false) => {
  if (!props.chatSessionId) {
    logger.warn('Cannot connect browser session: no chat session ID')
    return
  }

  // Reset retry count on manual refresh
  if (!retry) {
    retryCount = 0
  }

  isConnecting.value = true
  browserStatus.value = 'connecting'

  try {
    logger.info('Getting/creating browser session for chat:', props.chatSessionId)

    // Get or create browser session for this conversation
    // Use type assertion for the API call since ApiClient is JavaScript
    const response = await (apiClient as any).getOrCreateChatBrowserSession({
      conversation_id: props.chatSessionId,
      headless: false
    }) as BrowserSessionResponse

    if (response && response.session_id) {
      browserSessionId.value = response.session_id
      currentUrl.value = response.current_url || null
      interactionRequired.value = response.interaction_required || false

      // CRITICAL FIX: Use browser_status from API response instead of hardcoding
      // Map backend status to frontend status
      const backendStatus = response.browser_status || 'unknown'
      if (backendStatus === 'active' || backendStatus === 'initializing') {
        browserStatus.value = 'connected'
      } else if (backendStatus === 'error' || backendStatus === 'closed') {
        browserStatus.value = 'error'
      } else {
        browserStatus.value = 'connected' // Default to connected if session exists
      }

      // Reset retry count on success
      retryCount = 0

      logger.info('Browser session connected:', {
        sessionId: response.session_id,
        status: response.status,
        browserStatus: response.browser_status,
        mappedStatus: browserStatus.value
      })
    } else {
      throw new Error('Invalid response from browser session API')
    }
  } catch (error) {
    logger.error('Failed to connect browser session:', error)

    // Retry logic with exponential backoff
    if (retryCount < MAX_RETRIES) {
      retryCount++
      const delay = RETRY_DELAY_MS * retryCount
      logger.info(`Retrying browser session connection in ${delay}ms (attempt ${retryCount}/${MAX_RETRIES})`)

      setTimeout(() => {
        connectBrowserSession(true)
      }, delay)
      return // Don't set error state yet, we're retrying
    }

    // Max retries exceeded
    browserStatus.value = 'error'
    browserSessionId.value = null
    retryCount = 0
  } finally {
    if (browserStatus.value !== 'connecting') {
      isConnecting.value = false
    }
  }
}

const refreshSession = async () => {
  if (isConnecting.value) return
  await connectBrowserSession()
}

const disconnectBrowserSession = async () => {
  if (!props.chatSessionId) return

  try {
    // Use type assertion for the API call since ApiClient is JavaScript
    await (apiClient as any).deleteChatBrowserSession(props.chatSessionId)
    logger.info('Browser session disconnected for chat:', props.chatSessionId)
  } catch (error) {
    logger.warn('Failed to disconnect browser session:', error)
  }

  browserSessionId.value = null
  browserStatus.value = 'disconnected'
  currentUrl.value = null
  interactionRequired.value = false
}

// Watch for chat session changes
watch(() => props.chatSessionId, async (newSessionId, oldSessionId) => {
  if (newSessionId !== oldSessionId) {
    // Disconnect old session
    if (oldSessionId && browserSessionId.value) {
      await disconnectBrowserSession()
    }

    // Connect to new session
    if (newSessionId && props.autoConnect) {
      await connectBrowserSession()
    }
  }
}, { immediate: false })

// Lifecycle
onMounted(async () => {
  if (props.chatSessionId && props.autoConnect) {
    await connectBrowserSession()
  }
})

onUnmounted(async () => {
  // Don't disconnect on unmount - session persists across tab switches
  // The session will be cleaned up when the chat itself is closed
  logger.debug('ChatBrowser unmounted, keeping session alive')
})
</script>

<style scoped>
.chat-browser-container {
  @apply flex flex-col h-full bg-white border border-gray-300 overflow-hidden rounded-lg;
}

.browser-header {
  @apply bg-gray-100 border-b border-gray-300 p-2 flex items-center justify-between;
}

.browser-btn {
  @apply px-2 py-1 text-gray-600 hover:text-gray-800 hover:bg-gray-200 rounded transition-colors duration-200;
}

.browser-btn:disabled {
  @apply opacity-50 cursor-not-allowed;
}

.session-badge {
  @apply flex items-center space-x-1 px-2 py-1 rounded-full text-xs;
}

.browser-body {
  @apply flex-1 flex flex-col overflow-hidden;
}
</style>
