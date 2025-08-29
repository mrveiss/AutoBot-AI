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
        </div>

        <div class="border-l border-gray-300 pl-2 flex items-center space-x-1">
          <button @click="togglePopout" class="browser-btn" :title="isPopout ? 'Dock Browser' : 'Pop Out Browser'">
            <i class="fas" :class="isPopout ? 'fa-compress-arrows-alt' : 'fa-external-link-alt'"></i>
          </button>

          <button v-if="canResize" @click="toggleFullscreen" class="browser-btn" title="Toggle Fullscreen">
            <i class="fas" :class="isFullscreen ? 'fa-compress' : 'fa-expand'"></i>
          </button>

          <button @click="closeBrowser" class="browser-btn text-red-600" title="Close Browser">
            <i class="fas fa-times"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Address Bar -->
    <div class="address-bar bg-white border-b border-gray-200 p-2">
      <div class="flex items-center space-x-2">
        <div class="flex items-center space-x-1">
          <button @click="goBack" class="nav-btn" :disabled="!canGoBack">
            <i class="fas fa-arrow-left"></i>
          </button>
          <button @click="goForward" class="nav-btn" :disabled="!canGoForward">
            <i class="fas fa-arrow-right"></i>
          </button>
        </div>

        <div class="flex-1 flex items-center">
          <div class="url-input-container flex-1">
            <i class="fas fa-lock text-green-500 mr-2" v-if="isSecure"></i>
            <i class="fas fa-globe text-gray-500 mr-2" v-else></i>
            <input
              v-model="addressBarUrl"
              @keyup.enter="() => navigateToUrl()"
              @focus="selectAll"
              class="url-input flex-1 bg-transparent outline-none text-sm"
              placeholder="Enter URL or search terms..."
              :class="{ 'text-green-700': isSecure, 'text-gray-700': !isSecure }"
            >
          </div>
          <button @click="() => navigateToUrl()" class="nav-btn ml-2">
            <i class="fas fa-arrow-right"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Playwright Automation Panel -->
    <div v-if="showPlaywrightPanel" class="playwright-panel bg-blue-50 border-b border-blue-200 p-3">
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center space-x-2">
          <i class="fas fa-robot text-blue-600"></i>
          <h3 class="text-sm font-medium text-blue-800">Browser Automation</h3>
        </div>
        <div class="flex items-center space-x-1 text-xs">
          <span class="status-indicator" :class="playwrightStatus === 'healthy' ? 'bg-green-400' : 'bg-red-400'"></span>
          <span class="text-gray-600">{{ playwrightStatus }}</span>
        </div>
      </div>
      
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
        <!-- Web Search -->
        <div class="automation-card">
          <div class="flex items-center space-x-2 mb-2">
            <i class="fas fa-search text-blue-500"></i>
            <span class="text-sm font-medium">Web Search</span>
          </div>
          <input 
            v-model="searchQuery" 
            @keyup.enter="performWebSearch"
            placeholder="Enter search query..."
            class="w-full px-2 py-1 text-xs border rounded"
          >
          <button @click="performWebSearch" :disabled="playwrightLoading" class="w-full mt-1 px-2 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600">
            Search
          </button>
        </div>

        <!-- Frontend Testing -->
        <div class="automation-card">
          <div class="flex items-center space-x-2 mb-2">
            <i class="fas fa-vials text-green-500"></i>
            <span class="text-sm font-medium">Frontend Tests</span>
          </div>
          <button @click="runFrontendTest" :disabled="playwrightLoading" class="w-full px-2 py-1 text-xs bg-green-500 text-white rounded hover:bg-green-600 mb-1">
            Test Interface
          </button>
          <button @click="sendTestMessage" :disabled="playwrightLoading" class="w-full px-2 py-1 text-xs bg-green-500 text-white rounded hover:bg-green-600">
            Send Test Message
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
              Search: {{ automationResults.lastSearch.results?.length || 0 }} results
            </div>
            <div v-if="automationResults.lastTest">
              Tests: {{ automationResults.lastTest.passed || 0 }}/{{ automationResults.lastTest.total || 0 }} passed
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
        <div v-if="browserStatus === 'connecting'" class="absolute inset-0 bg-gray-100 flex items-center justify-center z-10">
          <div class="text-center">
            <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-2"></div>
            <p class="text-sm text-gray-600">Connecting to Playwright service...</p>
          </div>
        </div>

        <!-- API Error Overlay -->
        <div v-if="browserStatus === 'error'" class="absolute inset-0 bg-red-50 flex items-center justify-center z-10">
          <div class="text-center p-4">
            <i class="fas fa-exclamation-triangle text-red-500 text-2xl mb-2"></i>
            <p class="text-sm text-red-600 mb-2">Playwright service connection failed</p>
            <button @click="initializeBrowser" class="btn btn-primary btn-sm">
              <i class="fas fa-redo mr-1"></i>Retry Connection
            </button>
          </div>
        </div>

        <!-- Playwright Browser Interface (Headless API Control) -->
        <div v-if="browserStatus === 'ready'" class="w-full h-full bg-white">
          <div class="h-full flex flex-col">
            <!-- Browser simulation area -->
            <div class="flex-1 p-6 bg-gray-50">
              <div class="text-center">
                <div class="mb-4">
                  <i class="fas fa-robot text-blue-500 text-4xl mb-2"></i>
                  <h3 class="text-lg font-medium text-gray-800">Headless Browser Control</h3>
                  <p class="text-sm text-gray-600 mt-1">Control the browser programmatically. Use the <i class="fas fa-desktop text-blue-500"></i> VNC button for visual control.</p>
                </div>
                
                <!-- Current page info -->
                <div v-if="currentUrl && currentUrl !== 'about:blank'" class="bg-white rounded-lg p-4 shadow-sm border mb-4">
                  <div class="flex items-center justify-center space-x-2">
                    <i class="fas fa-globe text-green-500"></i>
                    <span class="text-sm font-medium">Current Page:</span>
                    <span class="text-sm text-blue-600">{{ currentUrl }}</span>
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
                    <p class="text-xs text-gray-600">Found {{ automationResults.lastSearch.results?.length || 0 }} results</p>
                  </div>

                  <div v-if="automationResults.lastTest" class="p-3 bg-green-50 rounded">
                    <div class="flex items-center space-x-2 mb-1">
                      <i class="fas fa-vials text-green-500"></i>
                      <span class="text-sm font-medium">Frontend Test</span>
                    </div>
                    <p class="text-xs text-gray-600">{{ automationResults.lastTest.passed }}/{{ automationResults.lastTest.total }} tests passed</p>
                  </div>
                </div>

                <!-- Getting started -->
                <div v-else class="text-center">
                  <p class="text-gray-500 text-sm mb-4">Click the robot icon above to start browser automation</p>
                  <div class="flex justify-center space-x-3">
                    <button @click="showPlaywrightPanel = true" class="btn btn-primary btn-sm">
                      <i class="fas fa-robot mr-1"></i>Open Automation Panel
                    </button>
                    <button @click="checkPlaywrightStatus" class="btn btn-outline btn-sm">
                      <i class="fas fa-heart mr-1"></i>Check Status
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <!-- Status footer -->
            <div class="border-t bg-gray-50 px-4 py-2 text-xs text-gray-500">
              <div class="flex items-center justify-between">
                <span>Playwright Service: {{ playwrightStatus }}</span>
                <span>Mode: Headless Browser API</span>
              </div>
            </div>
          </div>
        </div>

        <!-- VNC iframe hidden - use VNC popout button instead -->
        <!-- <iframe
          :src="vncUrl"
          class="w-full h-full border-0"
          @load="onVncLoad"
          ref="vncIframe"
        /> -->
      </div>

      <!-- Native Browser Embed (if available) -->
      <div v-else-if="browserMode === 'native'" class="w-full h-full">
        <webview
          :src="currentUrl"
          class="w-full h-full"
          @dom-ready="onWebviewReady"
          @did-navigate="onNavigate"
          @page-title-updated="onTitleUpdate"
          ref="webview"
          allowpopups
          plugins
        />
      </div>

      <!-- Chromium Remote Debugging -->
      <div v-else-if="browserMode === 'remote'" class="w-full h-full">
        <iframe
          :src="remoteDebugUrl"
          class="w-full h-full border-0"
          @load="onRemoteDebugLoad"
          ref="remoteIframe"
        />
      </div>

      <!-- Fallback Loading State -->
      <div v-else class="flex items-center justify-center h-full bg-gray-50">
        <div class="text-center">
          <div v-if="isPopout" class="text-center">
            <i class="fas fa-external-link-alt text-blue-500 text-4xl mb-4"></i>
            <h3 class="text-lg font-medium text-gray-800 mb-2">Browser Popped Out</h3>
            <p class="text-sm text-gray-600 mb-4">VNC browser is open in a separate window</p>
            <button @click="togglePopout" class="btn btn-primary btn-sm">
              <i class="fas fa-compress-arrows-alt mr-1"></i>
              Dock Browser Back
            </button>
          </div>
          <div v-else>
            <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
            <p class="text-gray-600">Initializing browser session...</p>
            <p class="text-sm text-gray-500 mt-2">Session ID: {{ sessionId || 'Not available' }}</p>
          </div>
        </div>
      </div>

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

    <!-- Status Bar -->
    <div class="status-bar bg-gray-100 border-t border-gray-300 p-1 text-xs text-gray-600 flex items-center justify-between">
      <div class="flex items-center space-x-4">
        <span>Status: {{ browserStatus }}</span>
        <span v-if="currentUrl">{{ currentUrl }}</span>
        <span v-if="pageLoadTime">Load: {{ pageLoadTime }}ms</span>
      </div>
      <div class="flex items-center space-x-2">
        <span v-if="zoomLevel !== 100">{{ zoomLevel }}%</span>
        <button @click="adjustZoom(-0.1)" class="status-btn">-</button>
        <button @click="resetZoom" class="status-btn">100%</button>
        <button @click="adjustZoom(0.1)" class="status-btn">+</button>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import type { Ref } from 'vue'
import { API_CONFIG } from '@/config/environment.js'
import apiClient from '@/utils/ApiClient.ts'

interface ConsoleLogEntry {
  timestamp: string
  level: string
  message: string
}

export default {
  name: 'PopoutChromiumBrowser',
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
    
    // Playwright API integration state
    const showPlaywrightPanel = ref(false)
    const playwrightLoading = ref(false)
    const playwrightStatus = ref('checking')
    const searchQuery = ref('')
    const automationResults = ref({
      lastSearch: null,
      lastTest: null,
      lastMessage: null
    })

    // Browser modes - VNC for actual browser display and takeover
    const browserMode = ref('vnc') // 'vnc', 'api', 'native', 'remote'  
    const vncUrl = ref(`${API_CONFIG.PLAYWRIGHT_VNC_URL}?autoconnect=true&resize=remote&reconnect=true&quality=9&compression=9`)
    const playwrightApiUrl = ref('/api/playwright') // Use relative path to avoid double base URL
    const remoteDebugUrl = ref(API_CONFIG.CHROME_DEBUG_URL)

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
            const data = await response.json()

            if (data.docker_browser && data.docker_browser.available) {
              browserMode.value = 'vnc'
              vncUrl.value = data.docker_browser.vnc_url || vncUrl.value
              browserStatus.value = 'connected'
            } else {
              browserMode.value = 'vnc'
              browserStatus.value = 'ready'
            }
          } catch (sessionError) {
            console.warn('Could not get session info, using default browser mode:', sessionError)
            browserMode.value = 'vnc'
            browserStatus.value = 'ready'
          }
        } else {
          // For manual browsers or no session, use default VNC mode
          browserMode.value = 'vnc'
          browserStatus.value = 'ready'
        }

        // Try remote debugging as fallback
        if (browserMode.value !== 'vnc') {
          try {
            const debugResponse = await fetch(`${API_CONFIG.CHROME_DEBUG_URL}/json`)
            if (debugResponse.ok) {
              browserMode.value = 'remote'
              const tabs = await debugResponse.json()
              if (tabs.length > 0) {
                remoteDebugUrl.value = tabs[0].devtoolsFrontendUrl
              }
            }
          } catch (e) {
            console.warn('Remote debugging not available, using VNC')
            browserMode.value = 'vnc'
          }
        }

        // Navigate to initial URL if provided and valid
        if (props.initialUrl && typeof props.initialUrl === 'string' && props.initialUrl !== 'about:blank') {
          // Set the URL in the address bar immediately
          currentUrl.value = props.initialUrl
          addressBarUrl.value = props.initialUrl
          isSecure.value = props.initialUrl.startsWith('https://')

          // Navigate to the URL
          await navigateToUrl(props.initialUrl)
          addConsoleLog('info', `Navigating to initial URL: ${props.initialUrl}`)
        } else {
          addConsoleLog('info', `No initial URL provided, using: ${props.initialUrl || 'about:blank'}`)
        }

      } catch (error) {
        console.error('Browser initialization failed:', error)
        browserStatus.value = 'error'
        // Set default mode even on error
        browserMode.value = 'vnc'
      } finally {
        loading.value = false
      }
    }

    // Navigation methods
    const navigateToUrl = async (url: string | null = null) => {
      let targetUrl = url || addressBarUrl.value

      // Validate and sanitize URL
      if (!targetUrl || typeof targetUrl !== 'string') {
        console.warn('Invalid URL provided:', targetUrl)
        return
      }

      targetUrl = targetUrl.trim()
      if (!targetUrl) return

      // Add protocol if missing
      if (!targetUrl.startsWith('http://') && !targetUrl.startsWith('https://') && !targetUrl.startsWith('about:')) {
        targetUrl = 'https://' + targetUrl
      }

      try {
        loading.value = true
        const startTime = Date.now()

        // Update current URL
        currentUrl.value = targetUrl
        addressBarUrl.value = targetUrl
        isSecure.value = targetUrl.startsWith('https://')

        // Navigate via API only for real research sessions (not fake session IDs)
        if (props.sessionId &&
            props.sessionId !== 'manual-browser' &&
            props.sessionId !== 'unified-browser') {
          try {
            await apiClient.post(`/api/research/session/${props.sessionId}/navigate`, {
              url: targetUrl
            })
          } catch (apiError) {
            console.warn('API navigation failed, continuing with local navigation:', apiError)
          }
        } else if (props.sessionId === 'manual-browser' || props.sessionId === 'unified-browser') {
          // For manual browser, control the VNC browser via Playwright API
          if (browserMode.value === 'vnc') {
            try {
              addConsoleLog('info', `Navigating VNC browser to: ${targetUrl}`)
              
              // Use Playwright API to navigate the browser in VNC container
              const response = await apiClient.post('/api/playwright/navigate', {
                url: targetUrl,
                wait_for: 'domcontentloaded'
              })
              
              if (response.ok) {
                const result = await response.json()
                addConsoleLog('success', `Navigation completed: ${result.final_url || targetUrl}`)
                currentUrl.value = result.final_url || targetUrl
                addressBarUrl.value = result.final_url || targetUrl
              } else {
                throw new Error('Navigation API call failed')
              }
              
              browserStatus.value = 'ready'

            } catch (vncError) {
              console.warn('VNC manual navigation failed:', vncError)
              browserStatus.value = 'error'
            }
          }

          if (webview.value && browserMode.value === 'native') {
            // For native webview, use direct navigation
            webview.value.src = targetUrl
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
          addConsoleLog('error', `Back navigation failed: ${error.message}`)
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
          addConsoleLog('error', `Forward navigation failed: ${error.message}`)
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
          addConsoleLog('error', `Refresh failed: ${error.message}`)
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

    const createVncPopupHtml = () => {
      // Build HTML content using dynamic string construction to avoid Vue parser issues
      const lt = '<'
      const gt = '>'
      const slash = '/'
      
      // Helper function to create closing tags
      const closeTag = (tagName: string) => lt + slash + tagName + gt
      
      let html = '<!DOCTYPE html>\n'
      html += lt + 'html' + gt + '\n'
      html += lt + 'head' + gt + '\n'
      html += lt + 'title' + gt + 'AutoBot VNC Browser' + closeTag('title') + '\n'
      html += lt + 'meta charset="utf-8"' + gt + '\n'
      html += lt + 'style' + gt + '\n'
      html += '* { margin: 0; padding: 0; box-sizing: border-box; }\n'
      html += 'body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f5f5; height: 100vh; display: flex; flex-direction: column; }\n'
      html += '.browser-header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 12px 16px; display: flex; align-items: center; gap: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }\n'
      html += '.browser-controls { display: flex; gap: 8px; align-items: center; }\n'
      html += '.control-btn { background: rgba(255,255,255,0.2); border: none; color: white; padding: 8px 12px; border-radius: 6px; cursor: pointer; font-size: 14px; transition: all 0.2s; display: flex; align-items: center; gap: 6px; }\n'
      html += '.control-btn:hover { background: rgba(255,255,255,0.3); transform: translateY(-1px); }\n'
      html += '.control-btn:disabled { opacity: 0.5; cursor: not-allowed; }\n'
      html += '.address-bar { flex: 1; background: white; border: none; padding: 10px 16px; border-radius: 25px; font-size: 14px; outline: none; box-shadow: inset 0 2px 4px rgba(0,0,0,0.1); }\n'
      html += '.vnc-container { flex: 1; background: white; border: 2px solid #e1e5e9; border-radius: 8px; margin: 12px; overflow: hidden; position: relative; }\n'
      html += '.vnc-iframe { width: 100%; height: 100%; border: none; }\n'
      html += '.status-bar { background: #2c3e50; color: white; padding: 8px 16px; font-size: 12px; display: flex; justify-content: space-between; align-items: center; }\n'
      html += '.loading { opacity: 0.6; pointer-events: none; }\n'
      html += closeTag('style') + '\n'
      html += closeTag('head') + '\n'
      html += lt + 'body' + gt + '\n'
      
      // Browser header
      html += lt + 'div class="browser-header"' + gt + '\n'
      html += lt + 'div class="browser-controls"' + gt + '\n'
      html += lt + 'button class="control-btn" onclick="goBack()" title="Back"' + gt + '← Back' + closeTag('button') + '\n'
      html += lt + 'button class="control-btn" onclick="goForward()" title="Forward"' + gt + 'Forward →' + closeTag('button') + '\n'
      html += lt + 'button class="control-btn" onclick="refresh()" title="Refresh"' + gt + '⟳ Refresh' + closeTag('button') + '\n'
      html += closeTag('div') + '\n'
      
      // Address bar
      html += lt + 'input class="address-bar" id="addressBar" placeholder="Enter URL or search terms..." onkeydown="if(event.key===\'Enter\') navigateToUrl()"' + gt + '\n'
      
      // Right controls
      html += lt + 'div class="browser-controls"' + gt + '\n'
      html += lt + 'button class="control-btn" onclick="navigateToUrl()" title="Navigate"' + gt + 'Go →' + closeTag('button') + '\n'
      html += lt + 'button class="control-btn" onclick="window.close()" title="Close"' + gt + '✕ Close' + closeTag('button') + '\n'
      html += closeTag('div') + '\n'
      html += closeTag('div') + '\n'
      
      // VNC container
      html += lt + 'div class="vnc-container"' + gt + '\n'
      html += lt + 'iframe src="' + vncUrl.value + '" class="vnc-iframe" title="VNC Browser Session"' + gt + closeTag('iframe') + '\n'
      html += closeTag('div') + '\n'
      
      // Status bar
      html += lt + 'div class="status-bar"' + gt + '\n'
      html += lt + 'span' + gt + 'VNC Browser - Full Visual Control' + closeTag('span') + '\n'
      html += lt + 'span id="currentUrl"' + gt + 'Ready' + closeTag('span') + '\n'
      html += closeTag('div') + '\n'
      
      // JavaScript
      html += lt + 'script' + gt + '\n'
      html += 'let isLoading = false;\n'
      html += 'function setLoading(loading) { isLoading = loading; document.body.classList.toggle("loading", loading); }\n'
      html += 'function updateStatus(message) { document.getElementById("currentUrl").textContent = message; }\n'
      html += 'async function apiCall(endpoint, method = "POST", data = null) {\n'
      html += 'try { setLoading(true);\n'
      html += 'const options = { method: method, headers: { "Content-Type": "application/json" } };\n'
      html += 'if (data) options.body = JSON.stringify(data);\n'
      html += 'try {\n'
      html += 'const response = await fetch("' + API_CONFIG.BASE_URL + '/api/playwright" + endpoint, options);\n'
      html += 'const result = await response.json();\n'
      html += 'if (result.success) {\n'
      html += 'updateStatus(result.final_url || result.url || "Success");\n'
      html += 'if (result.final_url) document.getElementById("addressBar").value = result.final_url;\n'
      html += 'return result;\n'
      html += '} else { throw new Error(result.error || "API call failed"); }\n'
      html += '} catch (apiError) {\n'
      html += 'updateStatus("API unavailable - use VNC interface below for manual control");\n'
      html += 'console.log("API fallback:", apiError.message);\n'
      html += 'return { success: false, fallback: true };\n'
      html += '}\n'
      html += '} catch (error) { updateStatus("Error: " + error.message); console.error("API call failed:", error); }\n'
      html += 'finally { setLoading(false); } }\n'
      html += 'function navigateToUrl() {\n'
      html += 'const url = document.getElementById("addressBar").value.trim();\n'
      html += 'if (!url) return;\n'
      html += 'let targetUrl = url;\n'
      html += 'if (!url.startsWith("http://") && !url.startsWith("https://") && !url.startsWith("about:")) targetUrl = "https://" + url;\n'
      html += 'apiCall("/navigate", "POST", { url: targetUrl }); }\n'
      html += 'function goBack() { apiCall("/back"); }\n'
      html += 'function goForward() { apiCall("/forward"); }\n'
      html += 'function refresh() { apiCall("/reload"); }\n'
      html += 'document.getElementById("addressBar").value = "https://example.com";\n'
      html += 'updateStatus("VNC Browser Ready - Click and interact directly in the VNC window below");\n'
      html += 'setTimeout(() => { document.getElementById("addressBar").focus(); }, 1000);\n'
      html += 'setTimeout(() => { updateStatus("💡 Type URL above or interact directly with the browser in VNC window"); }, 3000);\n'
      html += closeTag('script') + '\n'
      html += closeTag('body') + '\n'
      html += closeTag('html') + '\n'
      
      return html
    }

    const openVncPopout = () => {
      addConsoleLog('info', 'Opening VNC browser with controls in new window')
      
      // Create a custom HTML page with VNC viewer and browser controls
      const vncWindow = window.open(
        '',
        'vnc-browser',
        'width=1300,height=800,scrollbars=yes,resizable=yes,status=no,location=no,toolbar=no,menubar=no'
      )
      
      if (vncWindow) {
        vncWindow.document.write(createVncPopupHtml())
        vncWindow.document.close()
        vncWindow.focus()
        addConsoleLog('success', 'VNC browser window opened with full controls!')
      } else {
        addConsoleLog('error', 'Failed to open VNC popup - please check popup blocker settings')
      }
    }

    // Browser control methods
    const togglePopout = () => {
      isPopout.value = !isPopout.value

      if (isPopout.value) {
        // Create popup window for VNC browser
        const popup = window.open(
          '',
          'vnc-research-browser',
          `width=1400,height=900,scrollbars=yes,resizable=yes,toolbar=no,menubar=no,location=no,status=no`
        )

        if (popup) {
          // Create the popup content with VNC iframe
          const sessionTitle = props.sessionId ? `(${props.sessionId.slice(0, 8)}...)` : '(Manual)'

          // Build HTML content as DOM elements instead of string to avoid parsing issues
          popup.document.head.innerHTML = `
            <title>VNC Research Browser - ${sessionTitle}</title>
            <style>
              body { margin: 0; padding: 0; font-family: system-ui, sans-serif; background: #f3f4f6; }
              .browser-header { background: #e5e7eb; padding: 8px 12px; border-bottom: 1px solid #d1d5db; display: flex; align-items: center; justify-content: space-between; font-size: 14px; }
              .browser-title { font-weight: 600; color: #374151; }
              .browser-controls { display: flex; gap: 8px; }
              .control-btn { padding: 4px 8px; border: 1px solid #d1d5db; background: white; border-radius: 4px; cursor: pointer; font-size: 12px; }
              .control-btn:hover { background: #f9fafb; }
              .vnc-container { position: relative; height: calc(100vh - 40px); }
              .vnc-iframe { width: 100%; height: 100%; border: none; display: block; }
              .vnc-overlay { position: absolute; top: 10px; left: 10px; right: 10px; background: rgba(59, 130, 246, 0.9); color: white; padding: 8px 12px; border-radius: 6px; font-size: 12px; z-index: 10; }
            </style>
          `

          popup.document.body.innerHTML = `
            <div class="browser-header">
              <div class="browser-title">🖥️ VNC Research Browser ${sessionTitle}</div>
              <div class="browser-controls">
                <button class="control-btn" onclick="location.reload()" title="Refresh">🔄 Refresh</button>
                <button class="control-btn" onclick="window.close()" title="Close">✕ Close</button>
              </div>
            </div>
            <div class="vnc-container">
              <div class="vnc-overlay">🖱️ VNC Browser Control - Click and interact directly • Right-click for menu • Scroll to navigate</div>
              <iframe src="${vncUrl.value}" class="vnc-iframe" title="VNC Browser Session"></iframe>
            </div>
          `

          // Add JavaScript for resizing and overlay management
          const script = popup.document.createElement('script')
          script.textContent = `
            function resizeVNCFrame() {
              const iframe = document.querySelector('.vnc-iframe');
              if (iframe) {
                iframe.style.height = 'calc(100vh - 40px)';
                iframe.style.width = '100%';
              }
            }
            window.addEventListener('resize', resizeVNCFrame);
            window.addEventListener('load', resizeVNCFrame);
            setTimeout(function() {
              const overlay = document.querySelector('.vnc-overlay');
              if (overlay) {
                overlay.style.opacity = '0';
                overlay.style.transition = 'opacity 0.5s';
                setTimeout(() => overlay.remove(), 500);
              }
            }, 5000);
          `
          popup.document.body.appendChild(script)

          // Focus the popup
          popup.focus()

          emit('popout', { popup, sessionId: props.sessionId })
          addConsoleLog('info', 'VNC browser popped out to new window')
        }
      } else {
        emit('dock', { sessionId: props.sessionId })
        addConsoleLog('info', 'VNC browser docked back to main window')
      }
    }

    const toggleFullscreen = () => {
      isFullscreen.value = !isFullscreen.value
      // Implementation depends on the parent container
    }

    const closeBrowser = () => {
      emit('close', { sessionId: props.sessionId })
    }

    // Interaction handling
    const handleInteraction = async (action: string) => {
      try {
        // Only call API for real research sessions
        if (props.sessionId &&
            props.sessionId !== 'manual-browser' &&
            props.sessionId !== 'unified-browser') {
          const response = await apiClient.post('/api/research/session/action', {
            session_id: props.sessionId,
            action: action === 'wait' ? 'wait' : 'manual_intervention'
          })

          emit('interact', { action, response, sessionId: props.sessionId })
        } else {
          // For manual browsers, just handle locally
          emit('interact', { action, sessionId: props.sessionId })
        }

        if (action === 'takeover') {
          showInteractionOverlay.value = false
          addConsoleLog('info', 'User took manual control of browser session')
        }

      } catch (error) {
        console.error('Interaction handling failed:', error)
        addConsoleLog('error', `Interaction failed: ${error instanceof Error ? error.message : String(error)}`)
      }
    }

    const hideInteractionOverlay = () => {
      showInteractionOverlay.value = false
    }

    const showInteractionPrompt = (message: string) => {
      interactionMessage.value = message
      showInteractionOverlay.value = true
    }

    // Zoom controls
    const adjustZoom = (delta: number) => {
      zoomLevel.value = Math.max(25, Math.min(500, zoomLevel.value + (delta * 100)))

      if (webview.value) {
        webview.value.setZoomFactor(zoomLevel.value / 100)
      }
    }

    const resetZoom = () => {
      zoomLevel.value = 100
      if (webview.value) {
        webview.value.setZoomFactor(1)
      }
    }

    // Utility methods
    const selectAll = (event: Event) => {
      (event.target as HTMLInputElement).select()
    }

    const addConsoleLog = (level: string, message: string) => {
      consoleLogs.value.push({
        timestamp: new Date().toLocaleTimeString(),
        level,
        message
      })

      // Keep only last 100 logs
      if (consoleLogs.value.length > 100) {
        consoleLogs.value = consoleLogs.value.slice(-100)
      }
    }

    const getLogColor = (level: string) => {
      const colors: Record<string, string> = {
        info: 'text-blue-400',
        warn: 'text-yellow-400',
        error: 'text-red-400',
        debug: 'text-green-400'
      }
      return colors[level] || 'text-gray-400'
    }

    // Event handlers
    const onVncLoad = () => {
      browserStatus.value = 'ready'
      addConsoleLog('info', `VNC browser connection established for session: ${props.sessionId || 'manual'}`)
      
      // Set up automatic VNC scaling based on iframe dimensions
      nextTick(() => {
        const iframe = vncIframe.value
        if (iframe) {
          const updateVncScaling = () => {
            const rect = iframe.getBoundingClientRect()
            const width = Math.floor(rect.width)
            const height = Math.floor(rect.height)
            
            if (width > 0 && height > 0) {
              // Send a message to the VNC to adjust scaling
              try {
                iframe.contentWindow?.postMessage({
                  type: 'resize',
                  width: width,
                  height: height
                }, '*')
                
                addConsoleLog('info', `VNC scaling adjusted to: ${width}x${height}`)
              } catch (e) {
                console.log('VNC scaling adjustment not available:', e.message)
              }
            }
          }
          
          // Initial scaling adjustment
          setTimeout(updateVncScaling, 1000)
          
          // Set up resize observer for dynamic scaling
          if (window.ResizeObserver) {
            const resizeObserver = new ResizeObserver(updateVncScaling)
            resizeObserver.observe(iframe)
          }
        }
      })
    }

    const onWebviewReady = () => {
      browserStatus.value = 'ready'
      addConsoleLog('info', 'Native webview ready')
    }

    const onNavigate = (event: any) => {
      currentUrl.value = event.url
      addressBarUrl.value = event.url
      isSecure.value = event.url.startsWith('https://')
    }

    const onTitleUpdate = (event: any) => {
      document.title = event.title || 'Research Browser'
    }

    const onRemoteDebugLoad = () => {
      browserStatus.value = 'ready'
      addConsoleLog('info', 'Remote debugging interface loaded')
    }

    // Playwright API integration methods
    const checkPlaywrightStatus = async () => {
      try {
        playwrightLoading.value = true
        const data = await apiClient.get(`${playwrightApiUrl.value}/health`)
        playwrightStatus.value = data.status === 'healthy' ? 'healthy' : 'unhealthy'
        addConsoleLog('info', `Playwright status: ${playwrightStatus.value}`)
      } catch (error) {
        playwrightStatus.value = 'error'
        addConsoleLog('error', `Playwright status check failed: ${error.message}`)
      } finally {
        playwrightLoading.value = false
      }
    }

    const performWebSearch = async () => {
      if (!searchQuery.value.trim()) return

      try {
        playwrightLoading.value = true
        addConsoleLog('info', `Performing web search: ${searchQuery.value}`)
        
        const data = await apiClient.post(`${playwrightApiUrl.value}/search`, {
          query: searchQuery.value,
          search_engine: 'duckduckgo'
        })
        
        automationResults.value.lastSearch = data
        addConsoleLog('info', `Search completed: ${data.results?.length || 0} results found`)
      } catch (error) {
        addConsoleLog('error', `Web search failed: ${error.message}`)
      } finally {
        playwrightLoading.value = false
      }
    }

    const runFrontendTest = async () => {
      try {
        playwrightLoading.value = true
        addConsoleLog('info', 'Running frontend test suite')
        
        const data = await apiClient.post(`${playwrightApiUrl.value}/test-frontend`, {
          frontend_url: window.location.origin
        })
        
        const passed = data.tests?.filter(t => t.status === 'PASS').length || 0
        const total = data.tests?.length || 0
        
        automationResults.value.lastTest = { passed, total, data }
        addConsoleLog('info', `Frontend test completed: ${passed}/${total} tests passed`)
      } catch (error) {
        addConsoleLog('error', `Frontend test failed: ${error.message}`)
      } finally {
        playwrightLoading.value = false
      }
    }

    const sendTestMessage = async () => {
      try {
        playwrightLoading.value = true
        addConsoleLog('info', 'Sending test message via Playwright')
        
        const data = await apiClient.post(`${playwrightApiUrl.value}/send-test-message`, {
          message: 'Test message from browser automation',
          frontend_url: window.location.origin
        })
        
        automationResults.value.lastMessage = data
        const successSteps = data.steps?.filter(s => s.status === 'SUCCESS').length || 0
        addConsoleLog('info', `Test message completed: ${successSteps} steps successful`)
      } catch (error) {
        addConsoleLog('error', `Test message failed: ${error.message}`)
      } finally {
        playwrightLoading.value = false
      }
    }

    // Window resize handler
    const handleResize = () => {
      // Force iframe/webview resize by triggering reflow
      nextTick(() => {
        if (vncIframe.value) {
          // For VNC iframe, get container dimensions and update URL
          const iframe = vncIframe.value
          const container = iframe.parentElement
          if (container) {
            const width = Math.floor(container.clientWidth)
            const height = Math.floor(container.clientHeight)

            // Update VNC URL with current dimensions
            let newSrc = vncUrl.value
            if (newSrc.includes('resize=')) {
              newSrc = newSrc.replace(/resize=\w+/, 'resize=scale')
            }

            // Add viewport dimensions if not already present
            if (!newSrc.includes('width=') && !newSrc.includes('height=')) {
              newSrc += `&width=${width}&height=${height}`
            } else {
              newSrc = newSrc.replace(/width=\d+/, `width=${width}`)
              newSrc = newSrc.replace(/height=\d+/, `height=${height}`)
            }

            // Only update if URL changed to avoid unnecessary reloads
            if (iframe.src !== newSrc) {
              iframe.src = newSrc
            }
          }
        }

        if (webview.value) {
          // For native webview, trigger layout update
          try {
            webview.value.executeJavaScript(`
              window.dispatchEvent(new Event('resize'));
              document.body.style.zoom = ${zoomLevel.value / 100};
            `)
          } catch (e) {
            // Webview resize update failed
          }
        }

        if (remoteIframe.value) {
          // For remote debugging iframe
          const iframe = remoteIframe.value
          iframe.style.width = '100%'
          iframe.style.height = '100%'
        }
      })
    }

    // Lifecycle
    onMounted(() => {
      initializeBrowser()
      checkPlaywrightStatus() // Check Playwright service on mount

      // Add resize listener
      window.addEventListener('resize', handleResize)

      // Set up ResizeObserver for container changes
      if (window.ResizeObserver) {
        resizeObserver.value = new ResizeObserver(entries => {
          for (const entry of entries) {
            handleResize()
          }
        })

        // Observe the browser content div
        nextTick(() => {
          const browserContent = document.querySelector('.browser-content')
          if (browserContent && resizeObserver.value) {
            resizeObserver.value.observe(browserContent)
          }
        })
      }

      if (props.autoPopout) {
        setTimeout(() => togglePopout(), 1000)
      }
    })

    onUnmounted(() => {
      // Cleanup
      window.removeEventListener('resize', handleResize)

      if (resizeObserver.value) {
        resizeObserver.value.disconnect()
      }

      if (isPopout.value) {
        // Close popup if open
        emit('dock')
      }
    })

    // Watch for session changes
    watch(() => props.sessionId, (newSessionId) => {
      if (newSessionId) {
        initializeBrowser()
      }
    })

    // Watch for initial URL changes
    watch(() => props.initialUrl, (newUrl) => {
      if (newUrl && typeof newUrl === 'string' && newUrl !== 'about:blank') {
        currentUrl.value = newUrl
        addressBarUrl.value = newUrl
        isSecure.value = newUrl.startsWith('https://')

        // If browser is ready, navigate to the new URL
        if (browserStatus.value === 'ready') {
          navigateToUrl(newUrl)
        }
      }
    }, { immediate: true })

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
      remoteDebugUrl,
      canGoBack,
      canGoForward,
      isSecure,
      zoomLevel,
      pageLoadTime,
      consoleLogs,

      // Refs
      vncIframe,
      webview,
      remoteIframe,

      // Computed
      browserContentStyle,

      // Playwright state
      showPlaywrightPanel,
      playwrightLoading,
      playwrightStatus,
      searchQuery,
      automationResults,
      playwrightApiUrl,

      // Methods
      initializeBrowser,
      navigateToUrl,
      goBack,
      goForward,
      refreshBrowser,
      navigateHome,
      openVncPopout,
      togglePopout,
      toggleFullscreen,
      closeBrowser,
      handleInteraction,
      hideInteractionOverlay,
      showInteractionPrompt,
      adjustZoom,
      resetZoom,
      selectAll,
      getLogColor,
      onVncLoad,
      onWebviewReady,
      onNavigate,
      onTitleUpdate,
      onRemoteDebugLoad,

      // Playwright methods
      checkPlaywrightStatus,
      performWebSearch,
      runFrontendTest,
      sendTestMessage
    }
  }
}
</script>

<style scoped>
.chromium-browser-container {
  @apply flex flex-col h-full bg-white border rounded-lg shadow-lg overflow-hidden;
}

.browser-header {
  @apply flex-shrink-0;
}

.address-bar {
  @apply flex-shrink-0;
}

.browser-content {
  @apply flex-shrink flex-grow relative;
  min-height: 400px;
}

.status-bar {
  @apply flex-shrink-0;
}

.browser-btn {
  @apply w-8 h-8 flex items-center justify-center rounded text-gray-600 hover:bg-gray-200 hover:text-gray-800 transition-colors duration-150;
}

.browser-btn:disabled {
  @apply opacity-50 cursor-not-allowed hover:bg-transparent hover:text-gray-600;
}

.nav-btn {
  @apply w-8 h-8 flex items-center justify-center rounded text-gray-600 hover:bg-gray-100 hover:text-gray-800 transition-colors duration-150;
}

.nav-btn:disabled {
  @apply opacity-50 cursor-not-allowed hover:bg-transparent hover:text-gray-600;
}

.status-btn {
  @apply px-2 py-1 text-xs rounded hover:bg-gray-200 transition-colors duration-150;
}

.url-input-container {
  @apply flex items-center bg-gray-50 border border-gray-300 rounded px-3 py-1;
}

.url-input {
  @apply flex-1 bg-transparent outline-none text-sm;
}

.url-input:focus {
  @apply bg-white;
}

.btn {
  @apply px-4 py-2 text-sm font-medium rounded transition-colors duration-150;
}

.btn-primary {
  @apply bg-blue-600 text-white hover:bg-blue-700;
}

.btn-secondary {
  @apply bg-gray-600 text-white hover:bg-gray-700;
}

.btn-outline {
  @apply bg-white text-gray-700 border border-gray-300 hover:bg-gray-50;
}

/* WebView specific styles */
webview {
  width: 100%;
  height: 100%;
}

/* VNC iframe specific styles */
iframe {
  width: 100% !important;
  height: 100% !important;
  border: none;
  display: block;
  object-fit: contain;
}

/* Playwright automation panel styles */
.playwright-panel {
  @apply flex-shrink-0;
}

.automation-card {
  @apply bg-white rounded-lg p-3 border shadow-sm;
}

.status-indicator {
  @apply w-2 h-2 rounded-full;
}
</style>
