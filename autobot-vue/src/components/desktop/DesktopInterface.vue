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
      <div class="vnc-wrapper">
        <iframe 
          ref="vncFrame"
          :src="vncUrl"
          class="vnc-iframe"
          title="Remote Desktop - XFCE Environment"
          frameborder="0"
          allowfullscreen
        ></iframe>
      </div>
      
      <div v-if="loading" class="loading-overlay">
        <div class="loading-spinner">
          <div class="spinner"></div>
          <p class="loading-text">Connecting to desktop...</p>
        </div>
      </div>

      <div v-if="error" class="error-overlay">
        <div class="error-content">
          <div class="error-icon">⚠️</div>
          <h3>Desktop Connection Error</h3>
          <p>{{ error }}</p>
          <button @click="reconnect" class="reconnect-btn">
            Reconnect
          </button>
        </div>
      </div>
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

const vncFrame = ref(null)
const loading = ref(true)
const error = ref(null)
const isFullscreen = ref(false)
const connectionStatus = ref('Connecting...')

// VNC connection URL
const vncUrl = ref('http://localhost:6080/vnc.html?autoconnect=true&resize=scale')

const connectionStatusClass = computed(() => {
  switch (connectionStatus.value) {
    case 'Connected':
      return 'text-green-600 dark:text-green-400'
    case 'Disconnected':
      return 'text-red-600 dark:text-red-400'
    case 'Connecting...':
      return 'text-yellow-600 dark:text-yellow-400'
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
  
  // Reload the VNC iframe
  if (vncFrame.value) {
    vncFrame.value.src = vncFrame.value.src
  }
}

const checkConnection = async () => {
  try {
    const response = await fetch('http://localhost:6080/vnc.html', { method: 'HEAD' })
    if (response.ok) {
      connectionStatus.value = 'Connected'
      loading.value = false
      error.value = null
    } else {
      throw new Error(`HTTP ${response.status}`)
    }
  } catch (err) {
    connectionStatus.value = 'Disconnected'
    error.value = `Cannot connect to desktop service: ${err.message}`
    loading.value = false
  }
}

let connectionCheckInterval

onMounted(() => {
  // Initial connection check
  setTimeout(checkConnection, 2000)
  
  // Check connection status periodically
  connectionCheckInterval = setInterval(checkConnection, 10000)
  
  // Listen for fullscreen changes
  document.addEventListener('fullscreenchange', () => {
    isFullscreen.value = !!document.fullscreenElement
  })
})

onUnmounted(() => {
  if (connectionCheckInterval) {
    clearInterval(connectionCheckInterval)
  }
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

.loading-overlay {
  @apply absolute inset-0 bg-white dark:bg-gray-900 flex items-center justify-center z-10;
}

.loading-spinner {
  @apply flex flex-col items-center space-y-4;
}

.spinner {
  @apply w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin;
}

.loading-text {
  @apply text-gray-600 dark:text-gray-400 text-sm;
}

.error-overlay {
  @apply absolute inset-0 bg-white dark:bg-gray-900 flex items-center justify-center z-10;
}

.error-content {
  @apply text-center p-8 max-w-md;
}

.error-icon {
  @apply text-4xl mb-4;
}

.error-content h3 {
  @apply text-xl font-semibold text-gray-800 dark:text-gray-200 mb-2;
}

.error-content p {
  @apply text-gray-600 dark:text-gray-400 mb-4;
}

.reconnect-btn {
  @apply px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors;
}

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