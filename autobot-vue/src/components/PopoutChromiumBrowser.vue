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

    <!-- Browser Content Area -->
    <div class="browser-content flex-1 relative" :style="browserContentStyle">
      <!-- VNC Viewer for Remote Browser -->
      <div v-if="browserMode === 'vnc'" class="w-full h-full relative">
        <!-- VNC Connection Status Overlay -->
        <div v-if="browserStatus === 'connecting'" class="absolute inset-0 bg-gray-100 flex items-center justify-center z-10">
          <div class="text-center">
            <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-2"></div>
            <p class="text-sm text-gray-600">Connecting to browser...</p>
          </div>
        </div>

        <!-- VNC Error Overlay -->
        <div v-if="browserStatus === 'error'" class="absolute inset-0 bg-red-50 flex items-center justify-center z-10">
          <div class="text-center p-4">
            <i class="fas fa-exclamation-triangle text-red-500 text-2xl mb-2"></i>
            <p class="text-sm text-red-600 mb-2">Browser connection failed</p>
            <button @click="initializeBrowser" class="btn btn-primary btn-sm">
              <i class="fas fa-redo mr-1"></i>Retry Connection
            </button>
          </div>
        </div>

        <!-- VNC Browser Instructions -->
        <div v-if="(sessionId === 'unified-browser' || sessionId === 'manual-browser')"
             class="absolute top-4 left-4 right-4 bg-blue-900 bg-opacity-90 text-white p-3 rounded-lg z-20">
          <div class="flex items-center justify-between">
            <div class="flex items-center space-x-2">
              <i class="fas fa-mouse-pointer text-blue-300"></i>
              <div>
                <p class="text-sm font-medium">VNC Browser Control</p>
                <p class="text-xs text-blue-200">Click and interact directly in the browser below</p>
              </div>
            </div>
            <div class="text-xs text-blue-200">
              Right-click for menu • Scroll to navigate
            </div>
          </div>
        </div>

        <iframe
          :src="vncUrl"
          class="w-full h-full border-0"
          @load="onVncLoad"
          ref="vncIframe"
        />
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

    // Browser modes
    const browserMode = ref('vnc') // 'vnc', 'native', 'remote'
    const vncUrl = ref(`${API_CONFIG.PLAYWRIGHT_VNC_URL}?autoconnect=true&resize=scale&reconnect=true&quality=6&view_only=false`)
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
          // For manual browser, attempt to launch browser in VNC container
          if (browserMode.value === 'vnc') {
            try {
              // For VNC browser, just update the status and URL display
              // The VNC iframe will show whatever is running in the container
              addConsoleLog('info', `Manual navigation requested: ${targetUrl}`)
              browserStatus.value = 'ready'

              // The actual browser will be controlled manually by the user through VNC
              // This gives the user full control over the browser in the VNC session

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

    const goBack = () => {
      if (webview.value && webview.value.canGoBack()) {
        webview.value.goBack()
        canGoBack.value = webview.value.canGoBack()
        canGoForward.value = webview.value.canGoForward()
      }
    }

    const goForward = () => {
      if (webview.value && webview.value.canGoForward()) {
        webview.value.goForward()
        canGoBack.value = webview.value.canGoBack()
        canGoForward.value = webview.value.canGoForward()
      }
    }

    const refreshBrowser = async () => {
      if (webview.value) {
        webview.value.reload()
      } else {
        // Refresh VNC or remote session
        await navigateToUrl(currentUrl.value)
      }
    }

    const navigateHome = () => {
      navigateToUrl('about:blank')
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

      // Methods
      initializeBrowser,
      navigateToUrl,
      goBack,
      goForward,
      refreshBrowser,
      navigateHome,
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
      onRemoteDebugLoad
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
</style>
