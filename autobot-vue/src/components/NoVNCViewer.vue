<template>
  <div class="novnc-viewer h-full flex flex-col bg-black">
    <!-- Header -->
    <div class="flex justify-between items-center bg-gray-800 text-white px-4 py-2 text-sm flex-shrink-0">
      <div class="flex items-center gap-2">
        <i class="fas fa-desktop"></i>
        <span>Remote Desktop (noVNC)</span>
        <div class="connection-status" :class="connectionStatusClass">
          <div class="status-dot"></div>
          <span>{{ connectionStatusText }}</span>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <button
          @click="checkVNCService"
          class="text-gray-300 hover:text-white px-2 py-1 rounded hover:bg-gray-700 transition-colors"
          title="Check VNC service status"
          :disabled="isChecking"
        >
          <i :class="isChecking ? 'fas fa-spinner fa-spin' : 'fas fa-heartbeat'"></i>
          Service Check
        </button>
        <a
          :href="novncUrl"
          target="_blank"
          class="text-indigo-300 hover:text-indigo-100 underline flex items-center gap-1"
          title="Open noVNC in new window"
        >
          <i class="fas fa-external-link-alt"></i>
          New Window
        </a>
        <button
          @click="refreshViewer"
          class="text-gray-300 hover:text-white px-2 py-1 rounded hover:bg-gray-700 transition-colors"
          title="Refresh connection"
          :disabled="isRefreshing"
        >
          <i class="fas fa-sync-alt" :class="{ 'animate-spin': isRefreshing }"></i>
          Refresh
        </button>
        <button
          @click="toggleFullscreen"
          class="text-gray-300 hover:text-white px-2 py-1 rounded hover:bg-gray-700 transition-colors"
          title="Toggle fullscreen"
        >
          <i :class="isFullscreen ? 'fas fa-compress' : 'fas fa-expand'"></i>
          Fullscreen
        </button>
      </div>
    </div>

    <!-- Connection Status Banner -->
    <div v-if="connectionError" class="bg-red-600 text-white px-4 py-3 text-sm flex items-start gap-3">
      <i class="fas fa-exclamation-triangle flex-shrink-0 mt-0.5"></i>
      <div class="flex-1">
        <div class="font-medium">VNC Desktop Service Unavailable</div>
        <div class="text-xs mt-1 space-y-1">
          <div>The VNC desktop service is not responding on {{ vncHost }}:{{ vncPort }}.</div>
          <div v-if="errorDetails" class="text-red-200">{{ errorDetails }}</div>
          <div class="mt-2">
            <strong>To start VNC desktop:</strong>
            <br />1. Run: <code class="bg-red-700 px-1 rounded">bash run_autobot.sh --desktop</code>
            <br />2. Or manually: <code class="bg-red-700 px-1 rounded">vncserver -geometry 1920x1080 -depth 24</code>
          </div>
        </div>
      </div>
      <div class="flex gap-2">
        <button
          @click="retryConnection"
          class="px-3 py-1 bg-red-700 hover:bg-red-800 rounded text-sm transition-colors flex items-center gap-1"
          :disabled="isRetrying"
        >
          <i :class="isRetrying ? 'fas fa-spinner fa-spin' : 'fas fa-redo'"></i>
          {{ isRetrying ? 'Retrying...' : 'Retry' }}
        </button>
        <button
          @click="checkVNCService"
          class="px-3 py-1 bg-red-700 hover:bg-red-800 rounded text-sm transition-colors flex items-center gap-1"
          :disabled="isChecking"
        >
          <i :class="isChecking ? 'fas fa-spinner fa-spin' : 'fas fa-search'"></i>
          Check Service
        </button>
      </div>
    </div>

    <!-- Service Status Info -->
    <div v-if="serviceStatus && !connectionError" class="bg-green-600 text-white px-4 py-2 text-sm flex items-center justify-between">
      <div class="flex items-center gap-2">
        <i class="fas fa-check-circle"></i>
        <span>VNC service is running</span>
        <span class="text-green-200">{{ serviceStatus }}</span>
      </div>
      <button @click="clearServiceStatus" class="text-green-200 hover:text-white">
        <i class="fas fa-times"></i>
      </button>
    </div>

    <!-- Main VNC Display Area -->
    <div class="flex-1 relative">
      <UnifiedLoadingView
        loading-key="novnc-viewer"
        :has-content="!isLoading && !connectionError"
        :auto-timeout-ms="20000"
        @loading-complete="handleVNCConnected"
        @loading-error="handleVNCError"
        @loading-timeout="handleVNCTimeout"
        class="h-full"
      >
        <template #loading-message>
          <div class="text-center text-white">
            <p class="text-lg">Connecting to remote desktop...</p>
            <p class="text-sm text-gray-400 mt-2">{{ loadingMessage }}</p>
          </div>
        </template>

        <template #error-content>
          <div class="text-center text-white max-w-md mx-4">
            <i class="fas fa-desktop text-6xl text-gray-500 mb-4"></i>
            <h3 class="text-xl font-semibold mb-2">Desktop Not Available</h3>
            <p class="text-gray-400 mb-4">
              {{ connectionError || 'Unable to connect to the VNC desktop service. The service may not be running or may be temporarily unavailable.' }}
            </p>
            <div class="space-y-2">
              <button
                @click="retryConnection"
                class="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded transition-colors flex items-center justify-center gap-2"
                :disabled="isRetrying"
              >
                <i :class="isRetrying ? 'fas fa-spinner fa-spin' : 'fas fa-redo'"></i>
                {{ isRetrying ? 'Connecting...' : 'Try Again' }}
              </button>
              <button
                @click="openInNewWindow"
                class="w-full px-4 py-2 bg-gray-600 hover:bg-gray-700 rounded transition-colors flex items-center justify-center gap-2"
              >
                <i class="fas fa-external-link-alt"></i>
                Open in New Window
              </button>
            </div>
          </div>
        </template>

        <!-- VNC iframe content -->
        <iframe
          :key="iframeKey"
          :src="novncUrl"
          class="w-full h-full border-0"
          title="noVNC Remote Desktop"
          allowfullscreen
          @load="onIframeLoad"
          @error="onIframeError"
          ref="vncIframe"
        ></iframe>
      </UnifiedLoadingView>
    </div>

    <!-- Status Bar -->
    <div class="bg-gray-800 text-white px-4 py-1 text-xs flex justify-between items-center flex-shrink-0">
      <div class="flex items-center gap-4">
        <span>{{ vncHost }}:{{ vncPort }}</span>
        <span v-if="lastConnectionAttempt">
          Last attempt: {{ formatTime(lastConnectionAttempt) }}
        </span>
      </div>
      <div class="flex items-center gap-4">
        <span v-if="connectionLatency">Latency: {{ connectionLatency }}ms</span>
        <span class="cursor-pointer" @click="showDebugInfo = !showDebugInfo" title="Toggle debug info">
          <i class="fas fa-info-circle"></i>
        </span>
      </div>
    </div>

    <!-- Debug Info Panel -->
    <div v-if="showDebugInfo" class="bg-gray-800 text-white p-4 text-xs font-mono border-t border-gray-600">
      <div class="grid grid-cols-2 gap-4">
        <div>
          <div><strong>Connection:</strong></div>
          <div>URL: {{ novncUrl }}</div>
          <div>Host: {{ vncHost }}</div>
          <div>Port: {{ vncPort }}</div>
          <div>Status: {{ connectionStatusText }}</div>
        </div>
        <div>
          <div><strong>Diagnostics:</strong></div>
          <div>Iframe Key: {{ iframeKey }}</div>
          <div>Error Count: {{ errorCount }}</div>
          <div>Last Error: {{ lastError || 'None' }}</div>
          <div>Service Check: {{ lastServiceCheck || 'Never' }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, onUnmounted } from 'vue'
import UnifiedLoadingView from '@/components/ui/UnifiedLoadingView.vue'
import appConfig from '@/config/AppConfig.js'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for NoVNCViewer
const logger = createLogger('NoVNCViewer')
import { NetworkConstants } from '@/constants/network'
import { formatTime } from '@/utils/formatHelpers'
import { useAsyncOperation } from '@/composables/useAsyncOperation'

// Async operation for service checks
const { execute: executeServiceCheck, loading: isChecking } = useAsyncOperation()

// Component state
const vncHost = ref('')  // Will be loaded from appConfig
const vncPort = ref(0)   // Will be loaded from appConfig
const novncUrl = ref('')  // Will be loaded from appConfig.getVncUrl()
const isLoading = ref(true)
const isRefreshing = ref(false)
const isRetrying = ref(false)
const connectionError = ref(false)
const errorDetails = ref('')
const errorCount = ref(0)
const lastError = ref('')
const iframeKey = ref(0)
const lastConnectionAttempt = ref<Date | null>(null)
const connectionLatency = ref<number | null>(null)
const serviceStatus = ref<string | null>(null)  // Allow null values
const loadingMessage = ref('Initializing connection...')
const showDebugInfo = ref(false)
const isFullscreen = ref(false)
const lastServiceCheck = ref('')
const vncIframe = ref<HTMLIFrameElement | null>(null)

// Connection status
const connectionStatusClass = computed(() => {
  if (isLoading.value || isRetrying.value) return 'connecting'
  if (connectionError.value) return 'disconnected'
  return 'connected'
})

const connectionStatusText = computed(() => {
  if (isLoading.value) return 'Connecting...'
  if (isRetrying.value) return 'Reconnecting...'
  if (connectionError.value) return 'Disconnected'
  return 'Connected'
})

// Methods
const onIframeLoad = async () => {

  // Small delay to ensure VNC has time to establish connection
  setTimeout(async () => {
    isLoading.value = false
    connectionError.value = false
    errorDetails.value = ''

    // Measure connection latency
    await measureLatency()

    loadingMessage.value = 'Connected successfully!'
  }, 2000)
}

const onIframeError = (event: Event) => {
  logger.error('Iframe error:', event)
  isLoading.value = false
  connectionError.value = true
  errorCount.value += 1
  lastError.value = 'Iframe load error'
  errorDetails.value = 'Failed to load noVNC interface'
}

const measureLatency = async () => {
  try {
    const start = performance.now()
    const testUrl = `${vncHost.value}:${vncPort.value}`
    await fetch(`http://${testUrl}/`, {
      method: 'HEAD',
      mode: 'no-cors'
    })
    const end = performance.now()
    connectionLatency.value = Math.round(end - start)
  } catch (error) {
    connectionLatency.value = null
  }
}

const checkVNCServiceFn = async () => {
  lastServiceCheck.value = new Date().toLocaleTimeString()

  // Try to reach the VNC service
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 5000)

  const testUrl = `${vncHost.value}:${vncPort.value}`
  await fetch(`http://${testUrl}/`, {
    method: 'HEAD',
    signal: controller.signal,
    mode: 'no-cors'
  })

  clearTimeout(timeoutId)
  serviceStatus.value = `Service responding (${new Date().toLocaleTimeString()})`

  // If we can reach the service but iframe is broken, try refresh
  if (connectionError.value) {
    setTimeout(() => {
      refreshViewer()
    }, 1000)
  }
}

const checkVNCService = async () => {
  await executeServiceCheck(checkVNCServiceFn).catch(async (error: any) => {
    logger.warn('VNC service check failed:', error.message)
    if (error.name === 'AbortError') {
      errorDetails.value = 'Connection timeout - service may be starting up'
    } else {
      errorDetails.value = `Service check failed: ${error.message}`
    }

    // Try alternative ports
    await checkAlternativePorts()
  })
}

const checkAlternativePorts = async () => {
  const alternatePorts = [5901, 5902, 6080, 8080]

  for (const port of alternatePorts) {
    if (port === vncPort.value) continue

    try {
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 2000)

      await fetch(`http://${vncHost.value}:${port}/`, {
        method: 'HEAD',
        signal: controller.signal,
        mode: 'no-cors'
      })

      clearTimeout(timeoutId)

      // Found service on alternative port
      serviceStatus.value = `Found VNC service on port ${port}! Switching...`
      vncPort.value = port

      setTimeout(() => {
        refreshViewer()
      }, 1500)

      break
    } catch (error) {
      // Port not available, continue checking
    }
  }
}

const clearServiceStatus = () => {
  serviceStatus.value = null
}

const refreshViewer = async () => {
  isRefreshing.value = true
  isLoading.value = true
  connectionError.value = false
  errorDetails.value = ''
  lastConnectionAttempt.value = new Date()
  loadingMessage.value = 'Refreshing connection...'

  // Reload VNC URL from appConfig
  try {
    novncUrl.value = await appConfig.getVncUrl('desktop', {
      autoconnect: true,
      resize: 'scale',
      reconnect: true
    })
  } catch (error) {
    logger.error('Failed to reload VNC URL:', error)
  }

  // Force iframe refresh
  iframeKey.value += 1

  setTimeout(() => {
    isRefreshing.value = false
  }, 1000)

  // Set loading timeout
  setTimeout(() => {
    if (isLoading.value) {
      connectionError.value = true
      isLoading.value = false
      errorDetails.value = 'Connection timeout after refresh'
      errorCount.value += 1
      lastError.value = 'Refresh timeout'
    }
  }, 15000)
}

const retryConnection = () => {
  isRetrying.value = true
  loadingMessage.value = 'Attempting to reconnect...'

  setTimeout(() => {
    refreshViewer()
    isRetrying.value = false
  }, 1000)
}

const openInNewWindow = () => {
  window.open(novncUrl.value, '_blank', 'width=1200,height=800')
}

const toggleFullscreen = async () => {
  if (!document.fullscreenElement) {
    try {
      await document.documentElement.requestFullscreen()
      isFullscreen.value = true
    } catch (error) {
      logger.error('Failed to enter fullscreen:', error)
    }
  } else {
    try {
      await document.exitFullscreen()
      isFullscreen.value = false
    } catch (error) {
      logger.error('Failed to exit fullscreen:', error)
    }
  }
}


// Refs for cleanup
const loadingTimeout = ref<number | null>(null)

// Define fullscreen handler function for proper cleanup
const handleFullscreenChange = () => {
  isFullscreen.value = !!document.fullscreenElement
}

// UnifiedLoadingView event handlers
const handleVNCConnected = () => {
  isLoading.value = false
  connectionError.value = false
  errorDetails.value = ''
}

const handleVNCError = (error: any) => {
  logger.error('VNC connection error:', error)
  isLoading.value = false
  connectionError.value = true
  errorDetails.value = `VNC service error: ${error.message || error}`
  errorCount.value += 1
  lastError.value = error.message || error
}

const handleVNCTimeout = () => {
  logger.warn('VNC connection timeout')
  isLoading.value = false
  connectionError.value = true
  errorDetails.value = 'VNC service connection timed out. Service may be starting up.'
  errorCount.value += 1
  lastError.value = 'Connection timeout'
}

// Lifecycle
onMounted(async () => {
  lastConnectionAttempt.value = new Date()

  // Load VNC configuration from appConfig
  try {
    // Get VNC URL with standard options
    novncUrl.value = await appConfig.getVncUrl('desktop', {
      autoconnect: true,
      resize: 'scale',
      reconnect: true
    })

    // Extract host and port for display (parse from generated URL)
    const backendConfig = await appConfig.getBackendConfig()
    vncHost.value = backendConfig?.services?.vnc?.desktop?.host || NetworkConstants.MAIN_MACHINE_IP
    vncPort.value = Number(backendConfig?.services?.vnc?.desktop?.port || NetworkConstants.VNC_DESKTOP_PORT)

  } catch (error) {
    logger.warn('Failed to load VNC configuration from appConfig:', error)
    // Fallback values will be used
    vncHost.value = NetworkConstants.MAIN_MACHINE_IP
    vncPort.value = NetworkConstants.VNC_DESKTOP_PORT
    novncUrl.value = `http://${vncHost.value}:${vncPort.value}/vnc.html?autoconnect=true&resize=scale&reconnect=true`
  }

  // Set initial loading timeout
  loadingTimeout.value = setTimeout(() => {
    if (isLoading.value) {
      connectionError.value = true
      isLoading.value = false
      errorDetails.value = 'Initial connection timeout - VNC service may not be running'
      errorCount.value += 1
      lastError.value = 'Initial load timeout'
    }
  }, 12000)

  // Auto-check service status after initial load
  setTimeout(() => {
    if (connectionError.value) {
      checkVNCService()
    }
  }, 3000)

  // Listen for fullscreen changes
  document.addEventListener('fullscreenchange', handleFullscreenChange)
})

onUnmounted(() => {
  // Clean up timeout
  if (loadingTimeout.value) {
    clearTimeout(loadingTimeout.value)
    loadingTimeout.value = null
  }

  // Clean up event listener
  document.removeEventListener('fullscreenchange', handleFullscreenChange)
})
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.novnc-viewer {
  height: calc(100vh - 120px);
}

.connection-status {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
  font-size: var(--text-xs);
  margin-left: var(--spacing-4);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  transition: background-color var(--duration-300) var(--ease-in-out);
}

.connection-status.connected .status-dot {
  background: var(--color-success);
}

.connection-status.connecting .status-dot {
  background: var(--color-warning);
  animation: pulse 1.5s infinite;
}

.connection-status.disconnected .status-dot {
  background: var(--color-error);
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.5;
    transform: scale(1.1);
  }
}

/* Fullscreen styles */
:fullscreen .novnc-viewer {
  height: 100vh;
}

/* Hide scrollbars in fullscreen */
:fullscreen {
  overflow: hidden;
}

/* Smooth transitions */
.transition-colors {
  transition: color 0.2s ease, background-color 0.2s ease;
}

/* Better button hover states */
button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

button:disabled:hover {
  transform: none;
}
</style>
