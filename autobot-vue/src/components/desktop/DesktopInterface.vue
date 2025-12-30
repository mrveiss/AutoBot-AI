<template>
  <div class="desktop-interface">
    <div class="desktop-header">
      <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-200">
        Remote Desktop Access
      </h2>
      <p class="text-sm text-gray-600 dark:text-gray-400">
        Access the full XFCE desktop environment for system administration and GUI applications
      </p>
    </div>

    <div class="desktop-container">
      <UnifiedLoadingView
        loading-key="desktop-vnc"
        :has-content="!loading && !error"
        :auto-timeout-ms="15000"
        @loading-complete="handleDesktopConnected"
        @loading-error="handleDesktopError"
        @loading-timeout="handleDesktopTimeout"
        class="h-full"
      >
        <template #loading-message>
          <div class="text-center">
            <p class="text-gray-600 dark:text-gray-400">Connecting to desktop...</p>
            <p class="text-sm text-gray-500 mt-2">{{ connectionStatus }}</p>
          </div>
        </template>

        <template #error-content>
          <div class="text-center p-6">
            <div class="text-4xl mb-4">⚠️</div>
            <h3 class="text-lg font-semibold mb-2">Desktop Connection Error</h3>
            <p class="text-gray-600 mb-4">{{ error }}</p>
            <button @click="reconnect" class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">
              Reconnect
            </button>
          </div>
        </template>

        <!-- Desktop iframe content -->
        <div class="vnc-wrapper h-full">
          <iframe
            ref="vncFrame"
            :src="vncUrl"
            class="vnc-iframe"
            title="Remote Desktop - XFCE Environment"
            frameborder="0"
            allowfullscreen
          ></iframe>
        </div>
      </UnifiedLoadingView>
    </div>

    <div class="desktop-controls">
      <button @click="toggleFullscreen" class="control-btn">
        <span v-if="isFullscreen">Exit Fullscreen</span>
        <span v-else>Fullscreen</span>
      </button>
      <button @click="reconnect" class="control-btn">
        Reconnect
      </button>
      <div class="connection-status">
        <span :class="connectionStatusClass">{{ connectionStatus }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
// MIGRATED: Removed environment.js, using AppConfig.js only
import appConfig from '@/config/AppConfig.js'
import UnifiedLoadingView from '@/components/ui/UnifiedLoadingView.vue'
import { useAsyncOperation } from '@/composables/useAsyncOperation'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('DesktopInterface')

// Async operation composables
const { execute: executeLoadVnc, loading: loadingVnc, error: errorVnc } = useAsyncOperation()
const { execute: executeCheckConnection, loading: loadingCheck, error: errorCheck } = useAsyncOperation()

const vncFrame = ref(null)
const loading = ref(true)
const error = ref(null)
const isFullscreen = ref(false)
const connectionStatus = ref('Connecting...')

// VNC connection URL - will be loaded asynchronously from AppConfig
const vncUrl = ref('') // Will be loaded on mount

// Load dynamic VNC URL on component mount
const loadVncUrlFn = async () => {
  const dynamicVncUrl = await appConfig.getVncUrl('desktop');
  vncUrl.value = dynamicVncUrl;
  // Clear any previous errors and update status
  error.value = null;
  loading.value = false;
  connectionStatus.value = 'Connected';
}

const loadVncUrl = async () => {
  await executeLoadVnc(loadVncUrlFn).catch(err => {
    logger.error('Failed to load VNC URL from config:', err);

    // CRITICAL: No fallbacks - config failure is real failure
    // Desktop cannot function without proper configuration
    if (err.message && err.message.includes('Failed to fetch')) {
      error.value = 'Backend configuration service unavailable. Desktop requires configuration to function.';
      connectionStatus.value = 'Configuration Error';
    } else if (err.message && err.message.includes('Network Error')) {
      error.value = 'Network connectivity issues. Cannot retrieve desktop configuration.';
      connectionStatus.value = 'Network Error';
    } else if (err.message && err.message.includes('timeout')) {
      error.value = 'Configuration service timeout. Desktop configuration unavailable.';
      connectionStatus.value = 'Timeout';
    } else {
      error.value = `Configuration error: ${err.message}. Desktop requires valid configuration.`;
      connectionStatus.value = 'Configuration Error';
    }

    loading.value = false;

    // CRITICAL: No hardcoded fallbacks - config file is the only source of truth
    // Desktop cannot function without configuration - this is a real error state
    logger.error('Desktop unavailable - no configuration loaded');
  });
}

const connectionStatusClass = computed(() => {
  switch (connectionStatus.value) {
    case 'Connected':
      return 'text-green-600 dark:text-green-400'
    case 'Disconnected':
      return 'text-red-600 dark:text-red-400'
    case 'Connecting...':
      return 'text-yellow-600 dark:text-yellow-400'
    case 'Configuration Error':
      return 'text-red-600 dark:text-red-400'
    case 'Network Error':
      return 'text-red-600 dark:text-red-400'
    case 'Timeout':
      return 'text-orange-600 dark:text-orange-400'
    default:
      return 'text-gray-600 dark:text-gray-400'
  }
})

const toggleFullscreen = () => {
  if (!document.fullscreenElement) {
    vncFrame.value?.requestFullscreen?.()
    isFullscreen.value = true
  } else {
    document.exitFullscreen()
    isFullscreen.value = false
  }
}

const reconnect = () => {
  error.value = null
  loading.value = true
  connectionStatus.value = 'Connecting...'
  
  // Reload the VNC iframe with cache-bust to force refresh
  if (vncFrame.value) {
    // Issue #672: Force iframe refresh by appending cache-bust query param
    const currentSrc = vncFrame.value.src;
    const separator = currentSrc.includes('?') ? '&' : '?';
    vncFrame.value.src = `${currentSrc.split('&_refresh=')[0]}${separator}_refresh=${Date.now()}`;
  }
}

const checkConnectionFn = async () => {
  // Check the actual desktop VNC server health (backend server)
  const vncBaseUrl = await appConfig.getServiceUrl('vnc_desktop');

  // Create controller for timeout
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 5000);

  const response = await fetch(`${vncBaseUrl}/vnc.html`, {
    method: 'HEAD',
    signal: controller.signal
  });

  clearTimeout(timeoutId);

  if (response.ok) {
    connectionStatus.value = 'Connected'
    loading.value = false
    error.value = null
  } else {
    throw new Error(`HTTP ${response.status}`)
  }
}

const checkConnection = async () => {
  await executeCheckConnection(checkConnectionFn).catch(err => {
    connectionStatus.value = 'Disconnected'

    if (err.name === 'AbortError') {
      error.value = 'Desktop service connection timeout. Service may be starting up.';
    } else {
      const isServiceDisabled = err.message.includes('Connection refused') ||
                                err.message.includes('Network Error') ||
                                err.message.includes('Failed to fetch');

      if (isServiceDisabled) {
        error.value = 'Desktop service is currently disabled. Start AutoBot with desktop access enabled to use this feature.';
      } else {
        error.value = `Cannot connect to desktop service: ${err.message}`;
      }
    }
    loading.value = false
  });
}

// UnifiedLoadingView event handlers
const handleDesktopConnected = () => {
  loading.value = false
  connectionStatus.value = 'Connected'
}

const handleDesktopError = (error) => {
  logger.error('Desktop connection error:', error)
  loading.value = false
  connectionStatus.value = 'Error'
  error.value = `Desktop service error: ${error.message || error}`
}

const handleDesktopTimeout = () => {
  logger.warn('Desktop connection timeout')
  loading.value = false
  connectionStatus.value = 'Timeout'
  error.value = 'Desktop service connection timed out. Service may be starting up.'
}

let connectionCheckInterval

onMounted(async () => {
  // Load dynamic VNC URL first - wrapped in try-catch for safety
  try {
    await loadVncUrl()
  } catch (error) {
    logger.error('Critical error in loadVncUrl:', error)
    // Fallback to default state
    loading.value = false
    connectionStatus.value = 'Configuration Error'
    error.value = 'Failed to initialize desktop interface. Please refresh the page.'
  }
  
  // Initial connection check
  setTimeout(checkConnection, 2000)
  
  // Check connection status periodically
  connectionCheckInterval = setInterval(checkConnection, 10000)
  
  // Listen for fullscreen changes
  document.addEventListener('fullscreenchange', handleFullscreenChange)
})

// Define fullscreen handler function for proper cleanup
const handleFullscreenChange = () => {
  isFullscreen.value = !!document.fullscreenElement
}

onUnmounted(() => {
  if (connectionCheckInterval) {
    clearInterval(connectionCheckInterval)
  }

  // Clean up event listener
  document.removeEventListener('fullscreenchange', handleFullscreenChange)
})
</script>

<style scoped>
.desktop-interface {
  @apply flex flex-col h-full bg-gray-50 dark:bg-gray-900;
}

.desktop-header {
  @apply px-6 py-4 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700;
}

.desktop-container {
  @apply flex-1 relative overflow-hidden;
}

.vnc-wrapper {
  @apply w-full h-full;
}

.vnc-iframe {
  @apply w-full h-full border-0;
  min-height: 600px;
}

/* Loading and error styles moved to UnifiedLoadingView */

.desktop-controls {
  @apply px-6 py-3 bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 flex items-center justify-between;
}

.control-btn {
  @apply px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded border transition-colors;
}

.connection-status {
  @apply text-sm font-medium;
}
</style>