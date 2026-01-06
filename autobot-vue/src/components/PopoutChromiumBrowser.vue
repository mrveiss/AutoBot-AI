<template>
  <div class="chromium-browser-container">
    <!-- Browser Header -->
    <div class="browser-header bg-gray-100 border-b border-gray-300 p-2 flex items-center justify-between">
      <div class="flex items-center space-x-3">
        <div class="flex space-x-1">
          <div class="w-3 h-3 bg-red-500 rounded-full"></div>
          <div class="w-3 h-3 bg-yellow-500 rounded-full"></div>
          <div class="w-3 h-3 bg-green-500 rounded-full"></div>
        </div>
        <div class="flex items-center space-x-2 text-sm">
          <i class="fab fa-chrome text-blue-600"></i>
          <span class="font-medium">Research Browser</span>
          <span v-if="sessionId" class="text-xs text-gray-500">Session: {{ sessionId.slice(0, 8) }}...</span>
        </div>
      </div>

      <div class="flex items-center space-x-2">
        <!-- Browser Controls -->
        <div class="flex items-center space-x-1">
          <button @click="refreshBrowser" class="browser-btn" :disabled="isRefreshing" title="Refresh">
            <i class="fas fa-sync-alt" :class="{ 'fa-spin': isRefreshing }"></i>
          </button>

          <button @click="navigateHome" class="browser-btn" title="Home">
            <i class="fas fa-home"></i>
          </button>

          <button @click="showDevTools = !showDevTools" class="browser-btn" title="Developer Tools">
            <i class="fas fa-code"></i>
          </button>

          <button @click="openVncPopout" class="browser-btn text-blue-600" title="Open VNC Browser (Visual Control)">
            <i class="fas fa-desktop"></i>
          </button>
        </div>

        <!-- Playwright Automation Controls -->
        <div class="border-l border-gray-300 pl-2 flex items-center space-x-1">
          <button @click="showPlaywrightPanel = !showPlaywrightPanel" class="browser-btn" title="Playwright Automation">
            <i class="fas fa-robot" :class="{ 'text-blue-600': showPlaywrightPanel }"></i>
          </button>

          <button @click="runFrontendTest" class="browser-btn" :disabled="isTestingFrontend" title="Test Frontend">
            <i class="fas fa-vials" :class="{ 'fa-spin': isTestingFrontend }"></i>
          </button>

          <button @click="performWebSearch" class="browser-btn" :disabled="isSearching" title="Web Search">
            <i class="fas fa-search" :class="{ 'fa-spin': isSearching }"></i>
          </button>

          <button @click="sendTestMessage" class="browser-btn" :disabled="isSendingMessage" title="Test Message">
            <i class="fas fa-paper-plane" :class="{ 'fa-spin': isSendingMessage }"></i>
          </button>
        </div>

        <div class="border-l border-gray-300 pl-2">
          <button @click="$emit('close')" class="browser-btn text-red-600" title="Close">
            <i class="fas fa-times"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Address Bar -->
    <div class="address-bar bg-white border-b border-gray-200 p-3 flex items-center space-x-3">
      <button @click="goBack" :disabled="!canGoBack || isGoingBack" class="nav-btn" title="Back">
        <i class="fas fa-arrow-left" :class="{ 'fa-pulse': isGoingBack }"></i>
      </button>
      <button @click="goForward" :disabled="!canGoForward || isGoingForward" class="nav-btn" title="Forward">
        <i class="fas fa-arrow-right" :class="{ 'fa-pulse': isGoingForward }"></i>
      </button>
      <div class="flex-1 flex items-center bg-gray-50 rounded-lg px-3 py-2" :class="{ 'opacity-50': isNavigating }">
        <i class="fas fa-lock text-green-500 text-sm mr-2" v-if="isSecure"></i>
        <input
          v-model="addressBarUrl"
          @keyup.enter="navigateToUrl(addressBarUrl)"
          class="flex-1 bg-transparent text-sm outline-none"
          placeholder="Enter URL or search..."
        />
        <button @click="navigateToUrl(addressBarUrl)" :disabled="isNavigating" class="text-blue-600 hover:text-blue-800 ml-2">
          <i class="fas fa-search"></i>
        </button>
      </div>
      <div class="text-xs text-gray-500">
        {{ Math.round(zoomLevel) }}% | {{ pageLoadTime }}ms
      </div>
    </div>

    <!-- Playwright Automation Panel -->
    <div v-if="showPlaywrightPanel" class="automation-panel bg-blue-50 border-b border-blue-200 p-4">
      <div class="flex items-center justify-between mb-4">
        <div class="flex items-center space-x-2">
          <i class="fas fa-robot text-blue-600"></i>
          <span class="font-medium text-blue-800">Browser Automation</span>
          <span class="text-sm px-2 py-1 bg-blue-200 text-blue-700 rounded">{{ playwrightStatus }}</span>
        </div>
        <button @click="showPlaywrightPanel = false" class="text-blue-400 hover:text-blue-600">
          <i class="fas fa-times"></i>
        </button>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <!-- Web Search -->
        <div class="automation-card">
          <div class="flex items-center space-x-2 mb-2">
            <i class="fas fa-search text-green-500"></i>
            <span class="text-sm font-medium">Web Search</span>
          </div>
          <div class="space-y-2">
            <input
              v-model="searchQuery"
              @keyup.enter="performWebSearch"
              class="w-full px-3 py-1 text-sm border border-gray-300 rounded"
              placeholder="Search the web..."
            />
            <button @click="performWebSearch" :disabled="isSearching" class="w-full btn-sm btn-primary">
              <i class="fas mr-1" :class="isSearching ? 'fa-spinner fa-spin' : 'fa-search'"></i>
              {{ isSearching ? 'Searching...' : 'Search' }}
            </button>
          </div>
        </div>

        <!-- Frontend Testing -->
        <div class="automation-card">
          <div class="flex items-center space-x-2 mb-2">
            <i class="fas fa-vials text-blue-500"></i>
            <span class="text-sm font-medium">Frontend Test</span>
          </div>
          <button @click="runFrontendTest" :disabled="isTestingFrontend" class="w-full btn-sm btn-primary">
              <i class="fas mr-1" :class="isTestingFrontend ? 'fa-spinner fa-spin' : 'fa-play'"></i>
              {{ isTestingFrontend ? 'Running...' : 'Run Tests' }}
          </button>
        </div>

        <!-- Automation Results -->
        <div class="automation-card">
          <div class="flex items-center space-x-2 mb-2">
            <i class="fas fa-chart-bar text-purple-500"></i>
            <span class="text-sm font-medium">Results</span>
          </div>
          <div class="text-xs text-gray-600 space-y-1">
            <div v-if="automationResults.lastSearch">
              Search: {{ (automationResults.lastSearch as SearchData).results?.length || 0 }} results
            </div>
            <div v-if="automationResults.lastTest">
              Tests: {{ (automationResults.lastTest as TestData).passed || 0 }}/{{ (automationResults.lastTest as TestData).total || 0 }} passed
            </div>
            <div v-if="isSearching || isTestingFrontend || isSendingMessage" class="text-blue-600">
              <i class="fas fa-spinner fa-spin mr-1"></i>Running...
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Browser Content Area -->
    <div class="browser-content flex-1 relative" :style="browserContentStyle">
      <!-- VNC Browser with Playwright Integration -->
      <div v-if="browserMode === 'vnc'" class="w-full h-full relative">
        <!-- API Connection Status Overlay -->
        <UnifiedLoadingView
          v-if="browserStatus === 'connecting'"
          loading-key="playwright-connecting"
          :has-content="false"
          :auto-timeout-ms="10000"
          @loading-complete="handlePlaywrightConnected"
          @loading-error="handlePlaywrightError"
          @loading-timeout="handlePlaywrightTimeout"
          class="absolute inset-0 bg-gray-100 z-10"
        >
          <template #loading-message>
            <p class="text-sm text-gray-600">Connecting to Playwright service...</p>
          </template>
        </UnifiedLoadingView>

        <!-- API Error Overlay -->
        <div v-if="browserStatus === 'error'" class="absolute inset-0 bg-red-50 flex items-center justify-center z-10">
          <div class="text-center p-4">
            <i class="fas fa-exclamation-triangle text-red-500 text-2xl mb-2"></i>
            <p class="text-sm text-red-600 mb-2">Playwright service connection failed</p>
            <BaseButton variant="primary" size="sm" @click="initializeBrowser" :loading="isInitializingBrowser">
              <i class="fas fa-retry mr-1"></i>
              Retry Connection
            </BaseButton>
          </div>
        </div>

        <!-- Loading state while VNC URL is being fetched -->
        <div v-if="!vncUrl" class="w-full h-full flex items-center justify-center bg-gray-900 text-white">
          <div class="text-center p-8">
            <i class="fas fa-robot text-6xl mb-4 text-blue-400"></i>
            <h3 class="text-xl font-semibold mb-2">Headless Browser Mode</h3>
            <p class="text-gray-300 mb-4">
              The browser is running on the Browser VM via Playwright API
            </p>
            <p class="text-sm text-gray-400 mb-4">
              Enter a URL in the address bar above to navigate. Results will be logged below.
            </p>
            <div class="bg-gray-800 rounded p-4 text-left max-w-md mx-auto">
              <div class="text-xs text-gray-400 mb-2">Current Status:</div>
              <div class="text-sm">
                <div>Status: <span class="text-green-400">{{ browserStatus }}</span></div>
                <div v-if="currentUrl">URL: <span class="text-blue-300">{{ currentUrl }}</span></div>
                <div v-if="pageTitle">Title: <span class="text-gray-200">{{ pageTitle }}</span></div>
              </div>
            </div>
          </div>
        </div>

        <!-- VNC iframe for live browser display with headed Playwright -->
        <!-- Using v-if instead of v-show to prevent iframe from loading at all -->
        <iframe
          v-if="vncUrl && (browserStatus === 'connected' || browserStatus === 'ready')"
          ref="vncIframe"
          :src="vncUrl"
          class="w-full h-full border-none"
          allow="clipboard-read; clipboard-write"
        ></iframe>
      </div>

      <!-- Playwright Automation Status Panel -->
      <div v-if="showPlaywrightPanel && browserStatus === 'connected'" class="playwright-status-panel">
        <div class="bg-white rounded-lg shadow-lg p-4 border border-gray-200">
          <div class="mb-4">
            <div class="flex items-center justify-between mb-2">
              <h4 class="text-sm font-medium text-gray-800">Browser Session</h4>
              <StatusBadge variant="success" size="small">Connected</StatusBadge>
            </div>
            <div class="text-xs text-gray-600">
              <div class="flex items-center space-x-2">
                <i class="fas fa-link text-blue-500"></i>
                <span class="text-sm text-blue-600">{{ currentUrl }}</span>
              </div>
            </div>
          </div>

          <!-- Recent results -->
          <div v-if="automationResults.lastSearch || automationResults.lastTest" class="bg-white rounded-lg p-4 shadow-sm border">
            <h4 class="text-sm font-medium text-gray-700 mb-3">Recent Automation Results</h4>

            <div v-if="automationResults.lastSearch" class="mb-3 p-3 bg-blue-50 rounded">
              <div class="flex items-center space-x-2 mb-1">
                <i class="fas fa-search text-blue-500"></i>
                <span class="text-sm font-medium">Web Search</span>
              </div>
              <p class="text-xs text-gray-600">Found {{ (automationResults.lastSearch as SearchData).results?.length || 0 }} results</p>
            </div>

            <div v-if="automationResults.lastTest" class="p-3 bg-green-50 rounded">
              <div class="flex items-center space-x-2 mb-1">
                <i class="fas fa-vials text-green-500"></i>
                <span class="text-sm font-medium">Frontend Test</span>
              </div>
              <p class="text-xs text-gray-600">{{ (automationResults.lastTest as TestData).passed }}/{{ (automationResults.lastTest as TestData).total }} tests passed</p>
            </div>
          </div>

          <!-- Getting started -->
          <EmptyState
            v-else
            icon="fas fa-rocket"
            message="Use automation controls above to get started"
            compact
          />
        </div>
      </div>

      <!-- Manual Browser View (No Session) -->
      <div v-if="!sessionId || sessionId === 'manual-browser'" class="flex items-center justify-center h-full bg-gray-50">
        <EmptyState
          icon="fas fa-globe"
          title="Manual Browser Mode"
          message="Direct control via VNC interface"
        >
          <template #actions>
            <BaseButton variant="primary" @click="initializeBrowser" :loading="isInitializingBrowser">
              <i class="fas fa-rocket mr-2"></i>
              {{ isInitializingBrowser ? 'Launching...' : 'Launch Browser Session' }}
            </BaseButton>
            <p class="text-sm text-gray-500 mt-3">
              This will open a live browser that you can control directly
            </p>
          </template>
        </EmptyState>
      </div>

      <!-- Session Loading -->
      <UnifiedLoadingView
        v-else-if="loading"
        loading-key="browser-session-init"
        :has-content="false"
        :auto-timeout-ms="15000"
        @loading-complete="handleSessionInitialized"
        @loading-error="handleSessionError"
        @loading-timeout="handleSessionTimeout"
        class="h-full"
      >
        <template #loading-message>
          <div class="text-center">
            <p class="text-gray-600">Initializing browser session...</p>
            <p class="text-sm text-gray-500 mt-2">Session ID: {{ sessionId || 'Not available' }}</p>
          </div>
        </template>
      </UnifiedLoadingView>

      <!-- Developer Tools Overlay -->
      <div v-if="showDevTools" class="absolute bottom-0 left-0 right-0 h-1/3 bg-gray-900 border-t border-gray-600">
        <div class="flex items-center justify-between bg-gray-800 p-2 text-white text-sm">
          <span>Developer Console</span>
          <button @click="showDevTools = false" class="text-gray-400 hover:text-white">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="h-full overflow-auto p-2 text-green-400 font-mono text-xs bg-black">
          <div v-for="(log, index) in consoleLogs" :key="index" class="mb-1">
            <span class="text-gray-500">{{ log.timestamp }}</span>
            <span :class="getLogColor(log.level)">{{ log.message }}</span>
          </div>
        </div>
      </div>

      <!-- Interaction Overlay -->
      <div v-if="showInteractionOverlay" class="absolute inset-0 bg-black bg-opacity-50 flex items-center justify-center">
        <div class="bg-white rounded-lg p-6 max-w-md mx-4">
          <div class="flex items-center mb-4">
            <i class="fas fa-exclamation-triangle text-yellow-500 text-2xl mr-3"></i>
            <h3 class="text-lg font-semibold">User Interaction Required</h3>
          </div>
          <p class="text-gray-700 mb-4">{{ interactionMessage }}</p>
          <div class="flex space-x-3">
            <BaseButton variant="primary" @click="handleInteraction('wait')">
              <i class="fas fa-clock mr-1"></i>
              Wait & Monitor
            </BaseButton>
            <BaseButton variant="secondary" @click="handleInteraction('takeover')">
              <i class="fas fa-hand-paper mr-1"></i>
              Take Control
            </BaseButton>
            <BaseButton variant="outline" @click="hideInteractionOverlay">
              Dismiss
            </BaseButton>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import type { Ref } from 'vue'
import type { AutomationResults, SearchData, TestData, MessageData } from '@/types/browser'
import appConfig from '@/config/AppConfig.js'
import apiClient from '@/utils/ApiClient.ts'
import UnifiedLoadingView from '@/components/ui/UnifiedLoadingView.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { NetworkConstants } from '@/constants/network'
import { useAsyncHandler } from '@/composables/useErrorHandler'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for PopoutChromiumBrowser
const logger = createLogger('PopoutChromiumBrowser')

interface ConsoleLogEntry {
  timestamp: string
  level: string
  message: string
}

// Type for Playwright navigation response
interface PlaywrightNavigationResponse {
  final_url?: string
  url?: string
  title?: string
  status?: string
  [key: string]: unknown
}

export default {
  name: 'PopoutChromiumBrowser',
  components: {
    UnifiedLoadingView,
    EmptyState,
    StatusBadge,
    BaseButton
  },
  props: {
    sessionId: {
      type: String,
      required: true
    },
    initialUrl: {
      type: String,
      default: 'about:blank'
    },
    canResize: {
      type: Boolean,
      default: true
    },
    autoPopout: {
      type: Boolean,
      default: false
    }
  },
  emits: ['close', 'navigate', 'interact', 'popout', 'dock'],
  setup(props: any, { emit }: any) {
    // Core state
    const loading = ref(false)
    const browserStatus = ref('initializing')
    const currentUrl = ref(props.initialUrl)
    const pageTitle = ref('')
    const addressBarUrl = ref(props.initialUrl)
    const isPopout = ref(false)
    const isFullscreen = ref(false)
    const showDevTools = ref(false)
    const showInteractionOverlay = ref(false)
    const interactionMessage = ref('')

    // Playwright API integration state with proper typing
    const showPlaywrightPanel = ref(false)
    const playwrightStatus = ref('checking')
    const searchQuery = ref('')
    const automationResults = ref<AutomationResults>({
      lastSearch: null,
      lastTest: null,
      lastMessage: null
    })

    // Browser modes - VNC for actual browser display and takeover
    const browserMode = ref('vnc') // 'vnc', 'api', 'native', 'remote'
    const vncUrl = ref('') // Will be loaded async
    const playwrightApiUrl = ref('/api/playwright') // Use relative path to avoid double base URL
    const remoteDebugUrl = ref('') // Will be loaded async if needed

    // Resize observer
    const resizeObserver: Ref<ResizeObserver | null> = ref(null)

    // Navigation state
    const canGoBack = ref(false)
    const canGoForward = ref(false)
    const isSecure = ref(false)
    const zoomLevel = ref(100)
    const pageLoadTime = ref(0)

    // Console logs for dev tools
    const consoleLogs: Ref<ConsoleLogEntry[]> = ref([])

    // Refs
    const vncIframe: Ref<HTMLIFrameElement | null> = ref(null)
    const webview: Ref<any | null> = ref(null)
    const remoteIframe: Ref<HTMLIFrameElement | null> = ref(null)

    // Computed styles with responsive sizing
    const browserContentStyle = computed(() => ({
      height: isPopout.value ? '80vh' : '60vh',
      minHeight: '400px',
      maxHeight: '90vh'
    }))

    // Helper function to add console logs
    const addConsoleLog = (level: string, message: string) => {
      consoleLogs.value.push({
        timestamp: new Date().toLocaleTimeString(),
        level,
        message
      })

      // Keep only last 100 logs
      if (consoleLogs.value.length > 100) {
        consoleLogs.value.shift()
      }
    }

    // ========================================
    // API Operations with useAsyncHandler
    // ========================================

    // 1. Initialize Browser (Sequential API calls)
    const { execute: initializeBrowser, loading: isInitializingBrowser } = useAsyncHandler(
      async () => {
        browserStatus.value = 'connecting'

        let sessionData = null
        if (props.sessionId &&
            props.sessionId !== 'manual-browser' &&
            props.sessionId !== 'unified-browser') {
          try {
            // ApiClient.get() returns parsed JSON directly, throws on error
            // Issue #552: Fixed path to match backend /api/research-browser/
            sessionData = await apiClient.get(`/api/research-browser/browser/${props.sessionId}`)
          } catch (sessionError) {
            logger.warn('Could not get session info, using manual mode')
          }
        }

        // Second API call - try to connect to Playwright service
        let healthResponse = null
        try {
          healthResponse = await fetch(`${playwrightApiUrl.value}/health`)
        } catch (playwrightError) {
          // Will be handled in onSuccess
        }

        return { sessionData, healthResponse }
      },
      {
        onSuccess: (result) => {
          if (result.sessionData) {
            const sessionResponse = result.sessionData as unknown as PlaywrightNavigationResponse
            currentUrl.value = sessionResponse.url || props.initialUrl
            addressBarUrl.value = currentUrl.value
          }

          if (result.healthResponse && result.healthResponse.ok) {
            playwrightStatus.value = 'connected'
            browserStatus.value = 'connected'
            addConsoleLog('info', 'Connected to Playwright automation service')
          } else {
            logger.warn('Playwright service not available, using VNC only')
            playwrightStatus.value = 'unavailable'
            browserStatus.value = 'connected' // Still connected via VNC
            addConsoleLog('warn', 'Playwright automation not available')
          }

          browserStatus.value = 'ready'
          addConsoleLog('info', 'Browser session initialized successfully')
        },
        onError: (error) => {
          browserStatus.value = 'error'
          addConsoleLog('error', `Browser initialization failed: ${error.message}`)
        },
        logErrors: true,
        errorPrefix: '[PopoutChromiumBrowser]'
      }
    )

    // 2. Navigate to URL
    const { execute: navigateToUrlHandler, loading: isNavigating } = useAsyncHandler(
      async (url: string) => {
        if (!url.trim()) return null

        let targetUrl = url.trim()

        // Handle search queries vs URLs
        if (!targetUrl.includes('://') && !targetUrl.startsWith('localhost') && !targetUrl.includes('.')) {
          targetUrl = `https://duckduckgo.com/?q=${encodeURIComponent(targetUrl)}`
        } else if (!targetUrl.includes('://')) {
          targetUrl = `https://${targetUrl}`
        }

        const startTime = Date.now()

        // Update current URL immediately for UI
        currentUrl.value = targetUrl
        addressBarUrl.value = targetUrl
        isSecure.value = targetUrl.startsWith('https://')

        // Try Playwright navigation if available
        let playwrightResult: PlaywrightNavigationResponse | null = null
        if (playwrightStatus.value === 'connected') {
          try {
            // ApiClient.post() returns parsed JSON directly, throws on error
            playwrightResult = await apiClient.post(`${playwrightApiUrl.value}/navigate`, {
              url: targetUrl,
              session_id: props.sessionId
            }) as unknown as PlaywrightNavigationResponse
          } catch (navError) {
            logger.warn('Playwright navigation failed, relying on VNC')
          }
        }

        return {
          targetUrl,
          playwrightResult,
          loadTime: Date.now() - startTime
        }
      },
      {
        onSuccess: (result) => {
          if (result && result.playwrightResult) {
            const navResponse = result.playwrightResult
            currentUrl.value = navResponse.final_url || result.targetUrl
            addressBarUrl.value = navResponse.final_url || result.targetUrl
            addConsoleLog('info', `Navigation completed: ${navResponse.final_url}`)
          } else if (result) {
            addConsoleLog('info', `Navigated to: ${result.targetUrl}`)
          }

          if (result) {
            pageLoadTime.value = result.loadTime
            emit('navigate', { url: result.targetUrl, sessionId: props.sessionId })
          }
        },
        onError: (error) => {
          addConsoleLog('error', `Navigation failed: ${error.message}`)
        },
        logErrors: true,
        errorPrefix: '[PopoutChromiumBrowser]'
      }
    )

    // Wrapper function to maintain API
    const navigateToUrl = async (url: string) => {
      await navigateToUrlHandler(url)
    }

    // 3. Go Back
    const { execute: goBack, loading: isGoingBack } = useAsyncHandler(
      async () => {
        if (browserMode.value !== 'vnc') {
          if (webview.value && webview.value.canGoBack()) {
            webview.value.goBack()
            canGoBack.value = webview.value.canGoBack()
            canGoForward.value = webview.value.canGoForward()
            return null // No API call needed
          }
          return null
        }

        // ApiClient.post() returns parsed JSON directly, throws on error
        return await apiClient.post('/api/playwright/back') as unknown as PlaywrightNavigationResponse
      },
      {
        onSuccess: (result) => {
          if (result) {
            const navResponse = result as PlaywrightNavigationResponse
            if (navResponse.final_url) {
              currentUrl.value = navResponse.final_url
              addressBarUrl.value = navResponse.final_url
              addConsoleLog('info', `Navigated back to: ${navResponse.final_url}`)
            }
          }
        },
        onError: (error) => {
          addConsoleLog('error', `Back navigation failed: ${error.message}`)
        },
        logErrors: true,
        errorPrefix: '[PopoutChromiumBrowser]'
      }
    )

    // 4. Go Forward
    const { execute: goForward, loading: isGoingForward } = useAsyncHandler(
      async () => {
        if (browserMode.value !== 'vnc') {
          if (webview.value && webview.value.canGoForward()) {
            webview.value.goForward()
            canGoBack.value = webview.value.canGoBack()
            canGoForward.value = webview.value.canGoForward()
            return null // No API call needed
          }
          return null
        }

        // ApiClient.post() returns parsed JSON directly, throws on error
        return await apiClient.post('/api/playwright/forward') as unknown as PlaywrightNavigationResponse
      },
      {
        onSuccess: (result) => {
          if (result) {
            const navResponse = result as PlaywrightNavigationResponse
            if (navResponse.final_url) {
              currentUrl.value = navResponse.final_url
              addressBarUrl.value = navResponse.final_url
              addConsoleLog('info', `Navigated forward to: ${navResponse.final_url}`)
            }
          }
        },
        onError: (error) => {
          addConsoleLog('error', `Forward navigation failed: ${error.message}`)
        },
        logErrors: true,
        errorPrefix: '[PopoutChromiumBrowser]'
      }
    )

    // 5. Refresh Browser
    const { execute: refreshBrowser, loading: isRefreshing } = useAsyncHandler(
      async () => {
        if (browserMode.value !== 'vnc') {
          if (webview.value) {
            webview.value.reload()
            return null // No API call needed
          }
          // Fallback to navigation
          return 'navigate-fallback'
        }

        // ApiClient.post() returns parsed JSON directly, throws on error
        return await apiClient.post('/api/playwright/reload') as unknown as PlaywrightNavigationResponse
      },
      {
        onSuccess: async (result) => {
          if (result === 'navigate-fallback') {
            await navigateToUrl(currentUrl.value)
            return
          }

          if (result && typeof result === 'object') {
            const navResponse = result as PlaywrightNavigationResponse
            if (navResponse.final_url) {
              currentUrl.value = navResponse.final_url
              addressBarUrl.value = navResponse.final_url
              addConsoleLog('info', `Page refreshed: ${navResponse.final_url}`)
            }
          }
        },
        onError: (error) => {
          addConsoleLog('error', `Refresh failed: ${error.message}`)
        },
        logErrors: true,
        errorPrefix: '[PopoutChromiumBrowser]'
      }
    )

    // 6. Perform Web Search
    const { execute: performWebSearch, loading: isSearching } = useAsyncHandler(
      async () => {
        if (!searchQuery.value.trim()) return null

        addConsoleLog('info', `Starting web search for: ${searchQuery.value}`)

        // ApiClient.post() returns parsed JSON directly, throws on error
        return await apiClient.post(`${playwrightApiUrl.value}/search`, {
          query: searchQuery.value,
          search_engine: 'duckduckgo'
        })
      },
      {
        onSuccess: (data) => {
          if (data) {
            automationResults.value.lastSearch = data as unknown as SearchData
            addConsoleLog('info', `Search completed: ${(data as any).results?.length || 0} results found`)
          }
        },
        onError: (error) => {
          addConsoleLog('error', `Web search failed: ${error.message}`)
        },
        logErrors: true,
        errorPrefix: '[PopoutChromiumBrowser]'
      }
    )

    // 7. Run Frontend Test
    const { execute: runFrontendTest, loading: isTestingFrontend } = useAsyncHandler(
      async () => {
        addConsoleLog('info', 'Starting frontend tests...')

        // ApiClient.post() returns parsed JSON directly, throws on error
        return await apiClient.post(`${playwrightApiUrl.value}/test-frontend`, {
          frontend_url: window.location.origin
        })
      },
      {
        onSuccess: (data) => {
          if (data) {
            const tests = (data as any).tests
            const passed = tests?.filter((t: any) => t.status === 'PASS').length || 0
            const total = tests?.length || 0

            automationResults.value.lastTest = { passed, total, data } as TestData
            addConsoleLog('info', `Frontend test completed: ${passed}/${total} tests passed`)
          }
        },
        onError: (error) => {
          addConsoleLog('error', `Frontend test failed: ${error.message}`)
        },
        logErrors: true,
        errorPrefix: '[PopoutChromiumBrowser]'
      }
    )

    // 8. Send Test Message
    const { execute: sendTestMessage, loading: isSendingMessage } = useAsyncHandler(
      async () => {
        addConsoleLog('info', 'Sending test message...')

        // ApiClient.post() returns parsed JSON directly, throws on error
        return await apiClient.post(`${playwrightApiUrl.value}/send-test-message`, {
          message: 'Test message from browser automation',
          frontend_url: window.location.origin
        })
      },
      {
        onSuccess: (data) => {
          if (data) {
            automationResults.value.lastMessage = data as unknown as MessageData
            const steps = (data as any).steps
            const successSteps = steps?.filter((s: any) => s.status === 'SUCCESS').length || 0
            addConsoleLog('info', `Test message completed: ${successSteps} steps successful`)
          }
        },
        onError: (error) => {
          addConsoleLog('error', `Test message failed: ${error.message}`)
        },
        logErrors: true,
        errorPrefix: '[PopoutChromiumBrowser]'
      }
    )

    // ========================================
    // Helper Functions
    // ========================================

    const navigateHome = () => {
      navigateToUrl('about:blank')
    }

    const openVncPopout = () => {
      // Create VNC popout window
      const vncWindow = window.open(
        vncUrl.value,
        'autobot-vnc',
        'width=1200,height=800,menubar=no,toolbar=no,location=no,status=no'
      )

      if (vncWindow) {
        addConsoleLog('info', 'VNC browser opened in new window')
      }
    }

    // Interaction handlers
    const handleInteraction = (action: string) => {
      emit('interact', { action, sessionId: props.sessionId })
      hideInteractionOverlay()
    }

    const hideInteractionOverlay = () => {
      showInteractionOverlay.value = false
      interactionMessage.value = ''
    }

    // Utility functions
    const getLogColor = (level: string): string => {
      switch (level) {
        case 'error': return 'text-red-400'
        case 'warn': return 'text-yellow-400'
        case 'info': return 'text-blue-400'
        default: return 'text-green-400'
      }
    }

    // ========================================
    // Lifecycle
    // ========================================

    onMounted(async () => {
      // Load VNC URL for real-time browser viewing on Browser VM
      // Playwright now runs in headed mode with VNC on port 6080
      try {
        vncUrl.value = await appConfig.getVncUrl('playwright', {
          autoconnect: true,
          resize: 'scale'
        })
        logger.debug('Loaded VNC URL for headed mode:', vncUrl.value)
      } catch (error) {
        logger.error('Failed to load VNC URL:', error)
      }

      // Initialize Playwright connection
      initializeBrowser()

      // Set up resize observer for responsive behavior
      if (props.canResize) {
        resizeObserver.value = new ResizeObserver(() => {
          // Handle resize events
        })
      }
    })

    onUnmounted(() => {
      if (resizeObserver.value) {
        resizeObserver.value.disconnect()
      }
    })

    // Watch for prop changes
    watch(() => props.sessionId, (newSessionId) => {
      if (newSessionId) {
        initializeBrowser()
      }
    })

    // UnifiedLoadingView event handlers
    const handlePlaywrightConnected = () => {
      browserStatus.value = 'connected'
    }

    const handlePlaywrightError = (error: any) => {
      logger.error('Playwright connection error:', error)
      browserStatus.value = 'error'
      addConsoleLog('error', `Playwright connection failed: ${error.message || error}`)
    }

    const handlePlaywrightTimeout = () => {
      logger.warn('Playwright connection timeout')
      browserStatus.value = 'error'
      addConsoleLog('warning', 'Playwright connection timed out')
    }

    const handleSessionInitialized = () => {
      loading.value = false
      browserStatus.value = 'ready'
    }

    const handleSessionError = (error: any) => {
      logger.error('Session initialization error:', error)
      loading.value = false
      browserStatus.value = 'error'
      addConsoleLog('error', `Session initialization failed: ${error.message || error}`)
    }

    const handleSessionTimeout = () => {
      logger.warn('Session initialization timeout')
      loading.value = false
      browserStatus.value = 'error'
      addConsoleLog('warning', 'Session initialization timed out')
    }

    return {
      // State
      loading,
      browserStatus,
      currentUrl,
      pageTitle,
      addressBarUrl,
      isPopout,
      isFullscreen,
      showDevTools,
      showInteractionOverlay,
      interactionMessage,
      browserMode,
      vncUrl,
      playwrightApiUrl,
      remoteDebugUrl,
      canGoBack,
      canGoForward,
      isSecure,
      zoomLevel,
      pageLoadTime,
      consoleLogs,

      // Playwright state
      showPlaywrightPanel,
      playwrightStatus,
      searchQuery,
      automationResults,

      // Loading states (NEW - expose for UI)
      isInitializingBrowser,
      isNavigating,
      isGoingBack,
      isGoingForward,
      isRefreshing,
      isSearching,
      isTestingFrontend,
      isSendingMessage,

      // Refs
      vncIframe,
      webview,
      remoteIframe,

      // Computed
      browserContentStyle,

      // Methods
      initializeBrowser,
      navigateToUrl,
      goBack,
      goForward,
      refreshBrowser,
      navigateHome,
      openVncPopout,
      performWebSearch,
      runFrontendTest,
      sendTestMessage,
      handleInteraction,
      hideInteractionOverlay,
      addConsoleLog,
      getLogColor,

      // UnifiedLoadingView event handlers
      handlePlaywrightConnected,
      handlePlaywrightError,
      handlePlaywrightTimeout,
      handleSessionInitialized,
      handleSessionError,
      handleSessionTimeout
    }
  }
}
</script>

<style scoped>
.chromium-browser-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #f5f5f5;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.browser-header {
  flex-shrink: 0;
}

.address-bar {
  flex-shrink: 0;
}

.browser-content {
  flex: 1;
  position: relative;
  min-height: 0;
}

.browser-btn {
  padding: 6px 8px;
  border: none;
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.2s;
  font-size: 14px;
}

.browser-btn:hover {
  background-color: rgba(0, 0, 0, 0.1);
}

.browser-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.nav-btn {
  padding: 8px 12px;
  border: 1px solid #d1d5db;
  background: white;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.nav-btn:hover:not(:disabled) {
  background-color: #f3f4f6;
}

.nav-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.automation-panel {
  flex-shrink: 0;
}

.automation-card {
  background: white;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
}

.playwright-status-panel {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 300px;
  z-index: 20;
}

</style>
