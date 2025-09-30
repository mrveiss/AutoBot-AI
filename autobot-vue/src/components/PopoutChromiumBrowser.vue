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
          <button @click="refreshBrowser" class="browser-btn" :disabled="loading" title="Refresh">
            <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i>
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
          
          <button @click="runFrontendTest" class="browser-btn" :disabled="playwrightLoading" title="Test Frontend">
            <i class="fas fa-vials" :class="{ 'fa-spin': playwrightLoading }"></i>
          </button>
          
          <button @click="performWebSearch" class="browser-btn" :disabled="playwrightLoading" title="Web Search">
            <i class="fas fa-search" :class="{ 'fa-spin': playwrightLoading }"></i>
          </button>

          <button @click="sendTestMessage" class="browser-btn" :disabled="playwrightLoading" title="Test Message">
            <i class="fas fa-paper-plane" :class="{ 'fa-spin': playwrightLoading }"></i>
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
      <button @click="goBack" :disabled="!canGoBack" class="nav-btn" title="Back">
        <i class="fas fa-arrow-left"></i>
      </button>
      <button @click="goForward" :disabled="!canGoForward" class="nav-btn" title="Forward">
        <i class="fas fa-arrow-right"></i>
      </button>
      <div class="flex-1 flex items-center bg-gray-50 rounded-lg px-3 py-2">
        <i class="fas fa-lock text-green-500 text-sm mr-2" v-if="isSecure"></i>
        <input
          v-model="addressBarUrl"
          @keyup.enter="navigateToUrl(addressBarUrl)"
          class="flex-1 bg-transparent text-sm outline-none"
          placeholder="Enter URL or search..."
        />
        <button @click="navigateToUrl(addressBarUrl)" class="text-blue-600 hover:text-blue-800 ml-2">
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
            <button @click="performWebSearch" :disabled="playwrightLoading" class="w-full btn-sm btn-primary">
              <i class="fas fa-search mr-1"></i>
              Search
            </button>
          </div>
        </div>

        <!-- Frontend Testing -->
        <div class="automation-card">
          <div class="flex items-center space-x-2 mb-2">
            <i class="fas fa-vials text-blue-500"></i>
            <span class="text-sm font-medium">Frontend Test</span>
          </div>
          <button @click="runFrontendTest" :disabled="playwrightLoading" class="w-full btn-sm btn-primary">
            <i class="fas fa-play mr-1"></i>
            Run Tests
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
            <div v-if="playwrightLoading" class="text-blue-600">
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
            <button @click="initializeBrowser" class="btn btn-primary btn-sm">
              <i class="fas fa-retry mr-1"></i>
              Retry Connection
            </button>
          </div>
        </div>

        <!-- VNC iframe for live browser display -->
        <iframe
          v-show="browserStatus === 'connected' || browserStatus === 'ready'"
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
              <span class="text-xs px-2 py-1 bg-green-100 text-green-700 rounded">Connected</span>
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
          <div v-else class="text-center">
            <i class="fas fa-rocket text-gray-400 text-2xl mb-2"></i>
            <p class="text-sm text-gray-600">Use automation controls above to get started</p>
          </div>
        </div>
      </div>

      <!-- Manual Browser View (No Session) -->
      <div v-if="!sessionId || sessionId === 'manual-browser'" class="flex items-center justify-center h-full bg-gray-50">
        <div class="text-center p-8">
          <i class="fas fa-globe text-gray-400 text-6xl mb-4"></i>
          <h2 class="text-xl font-semibold text-gray-700 mb-2">Manual Browser Mode</h2>
          <p class="text-gray-600 mb-6">Direct control via VNC interface</p>
          <div class="space-y-3">
            <button @click="initializeBrowser" class="btn btn-primary">
              <i class="fas fa-rocket mr-2"></i>
              Launch Browser Session
            </button>
            <p class="text-sm text-gray-500">
              This will open a live browser that you can control directly
            </p>
          </div>
        </div>
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
            <button @click="handleInteraction('wait')" class="btn btn-primary">
              <i class="fas fa-clock mr-1"></i>
              Wait & Monitor
            </button>
            <button @click="handleInteraction('takeover')" class="btn btn-secondary">
              <i class="fas fa-hand-paper mr-1"></i>
              Take Control
            </button>
            <button @click="hideInteractionOverlay" class="btn btn-outline">
              Dismiss
            </button>
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

interface ConsoleLogEntry {
  timestamp: string
  level: string
  message: string
}

export default {
  name: 'PopoutChromiumBrowser',
  components: {
    UnifiedLoadingView
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
    const addressBarUrl = ref(props.initialUrl)
    const isPopout = ref(false)
    const isFullscreen = ref(false)
    const showDevTools = ref(false)
    const showInteractionOverlay = ref(false)
    const interactionMessage = ref('')
    
    // Playwright API integration state with proper typing
    const showPlaywrightPanel = ref(false)
    const playwrightLoading = ref(false)
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

    // Initialize browser session
    const initializeBrowser = async () => {
      try {
        loading.value = true
        browserStatus.value = 'connecting'

        // Only try to get session info if we have a real session ID
        if (props.sessionId &&
            props.sessionId !== 'manual-browser' &&
            props.sessionId !== 'unified-browser') {
          try {
            // Get browser session info for real research sessions
            const response = await apiClient.get(`/api/research/browser/${props.sessionId}`)
            if (response.ok) {
              const sessionData = await response.json()
              currentUrl.value = sessionData.url || props.initialUrl
              addressBarUrl.value = currentUrl.value
            }
          } catch (sessionError) {
            console.warn('Could not get session info, using manual mode')
            addConsoleLog('warn', 'Session info not available, using manual mode')
          }
        }

        // Try to connect to Playwright service
        try {
          const healthResponse = await fetch(`${playwrightApiUrl.value}/health`)
          if (healthResponse.ok) {
            playwrightStatus.value = 'connected'
            browserStatus.value = 'connected'
            addConsoleLog('info', 'Connected to Playwright automation service')
          } else {
            throw new Error('Playwright service not available')
          }
        } catch (playwrightError) {
          console.warn('Playwright service not available, using VNC only')
          playwrightStatus.value = 'unavailable'
          browserStatus.value = 'connected' // Still connected via VNC
          addConsoleLog('warn', 'Playwright automation not available')
        }

        // Always show VNC for visual control
        browserStatus.value = 'ready'
        addConsoleLog('info', 'Browser session initialized successfully')

      } catch (error) {
        console.error('Browser initialization failed:', error)
        browserStatus.value = 'error'
        addConsoleLog('error', `Browser initialization failed: ${error instanceof Error ? error.message : String(error)}`)
      } finally {
        loading.value = false
      }
    }

    // Navigation function with API integration
    const navigateToUrl = async (url: string) => {
      if (!url.trim()) return

      let targetUrl = url.trim()
      
      // Handle search queries vs URLs
      if (!targetUrl.includes('://') && !targetUrl.startsWith('localhost') && !targetUrl.includes('.')) {
        targetUrl = `https://duckduckgo.com/?q=${encodeURIComponent(targetUrl)}`
      } else if (!targetUrl.includes('://')) {
        targetUrl = `https://${targetUrl}`
      }

      try {
        loading.value = true
        const startTime = Date.now()
        
        // Update current URL immediately for UI
        currentUrl.value = targetUrl
        addressBarUrl.value = targetUrl
        isSecure.value = targetUrl.startsWith('https://')
        
        // Try Playwright navigation if available
        if (playwrightStatus.value === 'connected') {
          try {
            const response = await apiClient.post(`${playwrightApiUrl.value}/navigate`, {
              url: targetUrl,
              session_id: props.sessionId
            })
            
            if (response.ok) {
              const result = await response.json()
              currentUrl.value = result.final_url || targetUrl
              addressBarUrl.value = result.final_url || targetUrl
              addConsoleLog('info', `Navigation completed: ${result.final_url}`)
            }
          } catch (navError) {
            console.warn('Playwright navigation failed, relying on VNC')
            addConsoleLog('warn', 'API navigation failed, using manual control')
          }
        }

        pageLoadTime.value = Date.now() - startTime
        emit('navigate', { url: targetUrl, sessionId: props.sessionId })

        addConsoleLog('info', `Navigated to: ${targetUrl}`)

      } catch (error) {
        console.error('Navigation failed:', error)
        addConsoleLog('error', `Navigation failed: ${error instanceof Error ? error.message : String(error)}`)
      } finally {
        loading.value = false
      }
    }

    const goBack = async () => {
      if (browserMode.value === 'vnc') {
        try {
          loading.value = true
          const response = await apiClient.post('/api/playwright/back')
          if (response.ok) {
            const result = await response.json()
            currentUrl.value = result.final_url
            addressBarUrl.value = result.final_url
            addConsoleLog('info', `Navigated back to: ${result.final_url}`)
          }
        } catch (error) {
          addConsoleLog('error', `Back navigation failed: ${error instanceof Error ? error.message : String(error)}`)
        } finally {
          loading.value = false
        }
      } else if (webview.value && webview.value.canGoBack()) {
        webview.value.goBack()
        canGoBack.value = webview.value.canGoBack()
        canGoForward.value = webview.value.canGoForward()
      }
    }

    const goForward = async () => {
      if (browserMode.value === 'vnc') {
        try {
          loading.value = true
          const response = await apiClient.post('/api/playwright/forward')
          if (response.ok) {
            const result = await response.json()
            currentUrl.value = result.final_url
            addressBarUrl.value = result.final_url
            addConsoleLog('info', `Navigated forward to: ${result.final_url}`)
          }
        } catch (error) {
          addConsoleLog('error', `Forward navigation failed: ${error instanceof Error ? error.message : String(error)}`)
        } finally {
          loading.value = false
        }
      } else if (webview.value && webview.value.canGoForward()) {
        webview.value.goForward()
        canGoBack.value = webview.value.canGoBack()
        canGoForward.value = webview.value.canGoForward()
      }
    }

    const refreshBrowser = async () => {
      if (browserMode.value === 'vnc') {
        try {
          loading.value = true
          const response = await apiClient.post('/api/playwright/reload')
          if (response.ok) {
            const result = await response.json()
            currentUrl.value = result.final_url
            addressBarUrl.value = result.final_url
            addConsoleLog('info', `Page refreshed: ${result.final_url}`)
          }
        } catch (error) {
          addConsoleLog('error', `Refresh failed: ${error instanceof Error ? error.message : String(error)}`)
        } finally {
          loading.value = false
        }
      } else if (webview.value) {
        webview.value.reload()
      } else {
        // Refresh VNC or remote session
        await navigateToUrl(currentUrl.value)
      }
    }

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

    // Playwright automation methods
    const performWebSearch = async () => {
      if (!searchQuery.value.trim()) return
      
      try {
        playwrightLoading.value = true
        addConsoleLog('info', `Starting web search for: ${searchQuery.value}`)
        
        const data = await apiClient.post(`${playwrightApiUrl.value}/search`, {
          query: searchQuery.value,
          search_engine: 'duckduckgo'
        })
        
        automationResults.value.lastSearch = data as unknown as SearchData
        addConsoleLog('info', `Search completed: ${(data as any).results?.length || 0} results found`)
      } catch (error) {
        addConsoleLog('error', `Web search failed: ${error instanceof Error ? error.message : String(error)}`)
      } finally {
        playwrightLoading.value = false
      }
    }

    const runFrontendTest = async () => {
      try {
        playwrightLoading.value = true
        addConsoleLog('info', 'Starting frontend tests...')
        
        const data = await apiClient.post(`${playwrightApiUrl.value}/test-frontend`, {
          frontend_url: window.location.origin
        })
        
        const tests = (data as any).tests
        const passed = tests?.filter((t: any) => t.status === 'PASS').length || 0
        const total = tests?.length || 0
        
        automationResults.value.lastTest = { passed, total, data } as TestData
        addConsoleLog('info', `Frontend test completed: ${passed}/${total} tests passed`)
      } catch (error) {
        addConsoleLog('error', `Frontend test failed: ${error instanceof Error ? error.message : String(error)}`)
      } finally {
        playwrightLoading.value = false
      }
    }

    const sendTestMessage = async () => {
      try {
        playwrightLoading.value = true
        addConsoleLog('info', 'Sending test message...')
        
        const data = await apiClient.post(`${playwrightApiUrl.value}/send-test-message`, {
          message: 'Test message from browser automation',
          frontend_url: window.location.origin
        })
        
        automationResults.value.lastMessage = data as unknown as MessageData
        const steps = (data as any).steps
        const successSteps = steps?.filter((s: any) => s.status === 'SUCCESS').length || 0
        addConsoleLog('info', `Test message completed: ${successSteps} steps successful`)
      } catch (error) {
        addConsoleLog('error', `Test message failed: ${error instanceof Error ? error.message : String(error)}`)
      } finally {
        playwrightLoading.value = false
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

    // Lifecycle
    onMounted(async () => {
      // Load VNC URL dynamically
      try {
        const dynamicVncUrl = await appConfig.getVncUrl('playwright', {
          autoconnect: true,
          resize: 'remote',
          reconnect: true,
          quality: 9,
          compression: 9
        });
        vncUrl.value = dynamicVncUrl;
      } catch (error) {
        console.warn('Failed to load dynamic VNC URL, using fallback');
        vncUrl.value = 'http://172.16.168.25:6081/vnc.html?autoconnect=true&resize=remote&reconnect=true&quality=9&compression=9&password=playwright';
      }

      // Initialize browser when component mounts
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
      console.log('[PopoutChromiumBrowser] Playwright connection established')
      browserStatus.value = 'connected'
    }

    const handlePlaywrightError = (error: any) => {
      console.error('[PopoutChromiumBrowser] Playwright connection error:', error)
      browserStatus.value = 'error'
      addConsoleLog('error', `Playwright connection failed: ${error.message || error}`)
    }

    const handlePlaywrightTimeout = () => {
      console.warn('[PopoutChromiumBrowser] Playwright connection timeout')
      browserStatus.value = 'error'
      addConsoleLog('warning', 'Playwright connection timed out')
    }

    const handleSessionInitialized = () => {
      console.log('[PopoutChromiumBrowser] Browser session initialized')
      loading.value = false
      browserStatus.value = 'ready'
    }

    const handleSessionError = (error: any) => {
      console.error('[PopoutChromiumBrowser] Session initialization error:', error)
      loading.value = false
      browserStatus.value = 'error'
      addConsoleLog('error', `Session initialization failed: ${error.message || error}`)
    }

    const handleSessionTimeout = () => {
      console.warn('[PopoutChromiumBrowser] Session initialization timeout')
      loading.value = false
      browserStatus.value = 'error'
      addConsoleLog('warning', 'Session initialization timed out')
    }

    return {
      // State
      loading,
      browserStatus,
      currentUrl,
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
      playwrightLoading,
      playwrightStatus,
      searchQuery,
      automationResults,

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

.btn-sm {
  padding: 4px 8px;
  font-size: 12px;
  border-radius: 4px;
}

.btn-primary {
  background-color: #3b82f6;
  color: white;
  border: none;
}

.btn-primary:hover:not(:disabled) {
  background-color: #2563eb;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn {
  padding: 8px 16px;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-secondary {
  background-color: #6b7280;
  color: white;
}

.btn-secondary:hover {
  background-color: #4b5563;
}

.btn-outline {
  background-color: transparent;
  color: #374151;
  border: 1px solid #d1d5db;
}

.btn-outline:hover {
  background-color: #f9fafb;
}
</style>