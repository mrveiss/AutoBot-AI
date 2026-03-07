<template>
  <div class="desktop-interface">
    <div class="desktop-header">
      <h2 class="text-lg font-semibold text-autobot-text-primary">
        {{ $t('desktop.interface.title') }}
      </h2>
      <p class="text-sm text-autobot-text-secondary">
        {{ $t('desktop.interface.description') }}
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
            <p class="text-autobot-text-secondary">{{ $t('desktop.interface.connecting') }}</p>
            <p class="text-sm text-autobot-text-muted mt-2">{{ connectionStatusDisplay }}</p>
          </div>
        </template>

        <template #error-content>
          <div class="text-center p-6">
            <div class="text-4xl mb-4">⚠️</div>
            <h3 class="text-lg font-semibold mb-2">{{ $t('desktop.interface.connectionError') }}</h3>
            <p class="text-autobot-text-secondary mb-4">{{ error }}</p>
            <button @click="reconnect" class="px-4 py-2 bg-electric-600 text-white rounded hover:bg-electric-700">
              {{ $t('desktop.interface.reconnect') }}
            </button>
          </div>
        </template>

        <!-- Desktop iframe content -->
        <div class="vnc-wrapper h-full">
          <iframe
            ref="vncFrame"
            :src="vncUrl"
            class="vnc-iframe"
            :title="$t('desktop.interface.iframeTitle')"
            frameborder="0"
            allowfullscreen
          ></iframe>
        </div>
      </UnifiedLoadingView>
    </div>

    <div class="desktop-controls">
      <button @click="toggleFullscreen" class="control-btn">
        <span v-if="isFullscreen">{{ $t('desktop.interface.exitFullscreen') }}</span>
        <span v-else>{{ $t('desktop.interface.fullscreen') }}</span>
      </button>
      <button @click="reconnect" class="control-btn">
        {{ $t('desktop.interface.reconnect') }}
      </button>
      <div class="connection-status">
        <span :class="connectionStatusClass">{{ connectionStatusDisplay }}</span>
      </div>
    </div>

    <!-- Desktop Actions Toolbar (Issue #74) -->
    <div class="desktop-actions">
      <div class="actions-label text-sm font-medium text-autobot-text-secondary">
        {{ $t('desktop.interface.desktopActions') }}
      </div>
      <div class="actions-buttons">
        <button @click="takeScreenshot" class="action-btn" :title="$t('desktop.interface.screenshot')">
          📷 {{ $t('desktop.interface.screenshot') }}
        </button>
        <button @click="showTypeDialog = true" class="action-btn" :title="$t('desktop.interface.typeText')">
          ⌨️ {{ $t('desktop.interface.typeText') }}
        </button>
        <button @click="sendCtrlAltDel" class="action-btn" :title="$t('desktop.interface.ctrlAltDel')">
          🔴 {{ $t('desktop.interface.ctrlAltDel') }}
        </button>
        <button @click="pasteFromClipboard" class="action-btn" :title="$t('desktop.interface.paste')">
          📋 {{ $t('desktop.interface.paste') }}
        </button>
      </div>
    </div>

    <!-- Screenshot Modal (Issue #74) -->
    <Teleport to="body">
      <div v-if="showScreenshotModal" class="screenshot-modal" @click="showScreenshotModal = false">
        <div class="screenshot-content" @click.stop>
          <div class="screenshot-header">
            <h3 class="text-lg font-semibold text-autobot-text-primary">{{ $t('desktop.interface.screenshotTitle') }}</h3>
            <button @click="showScreenshotModal = false" class="close-btn">×</button>
          </div>
          <div class="screenshot-body">
            <img v-if="screenshotData" :src="screenshotData" :alt="$t('desktop.interface.screenshotAlt')" class="screenshot-image" />
          </div>
          <div class="screenshot-footer">
            <button @click="downloadScreenshot" class="download-btn">
              💾 {{ $t('desktop.interface.download') }}
            </button>
            <button @click="showScreenshotModal = false" class="cancel-btn">
              {{ $t('desktop.interface.close') }}
            </button>
          </div>
        </div>
      </div>

      <!-- Type Text Dialog (Issue #74) -->
      <div v-if="showTypeDialog" class="type-dialog-modal" @click="showTypeDialog = false">
        <div class="type-dialog-content" @click.stop>
          <div class="type-dialog-header">
            <h3 class="text-lg font-semibold text-autobot-text-primary">{{ $t('desktop.interface.typeTextTitle') }}</h3>
            <button @click="showTypeDialog = false" class="close-btn">×</button>
          </div>
          <div class="type-dialog-body">
            <textarea
              v-model="textToType"
              :placeholder="$t('desktop.interface.typeTextPlaceholder')"
              class="type-textarea"
              rows="4"
            ></textarea>
          </div>
          <div class="type-dialog-footer">
            <button @click="handleTypeText" :disabled="!textToType.trim()" class="type-btn">
              ⌨️ {{ $t('desktop.interface.typeTextSend') }}
            </button>
            <button @click="showTypeDialog = false" class="cancel-btn">
              {{ $t('desktop.interface.cancel') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
// MIGRATED: Removed environment.js, using AppConfig.js only
import appConfig from '@/config/AppConfig.js'
import UnifiedLoadingView from '@/components/ui/UnifiedLoadingView.vue'
import { useAsyncOperation } from '@/composables/useAsyncOperation'
import { useVncControls } from '@/composables/useVncControls'
import { createLogger } from '@/utils/debugUtils'

const { t } = useI18n()
const logger = createLogger('DesktopInterface')

// Async operation composables
const { execute: executeLoadVnc, loading: loadingVnc, error: errorVnc } = useAsyncOperation()
const { execute: executeCheckConnection, loading: loadingCheck, error: errorCheck } = useAsyncOperation()

// VNC controls (Issue #74)
const vncControls = useVncControls()
const showScreenshotModal = ref(false)
const screenshotData = ref<string | null>(null)
const textToType = ref('')
const showTypeDialog = ref(false)

const vncFrame = ref(null)
const loading = ref(true)
const error = ref(null)
const isFullscreen = ref(false)
const connectionStatus = ref('Connecting...')

const connectionStatusDisplay = computed(() => {
  const statusMap = {
    'Connecting...': t('desktop.interface.statusConnecting'),
    'Connected': t('desktop.interface.statusConnected'),
    'Disconnected': t('desktop.interface.statusDisconnected'),
    'Configuration Error': t('desktop.interface.statusConfigError'),
    'Network Error': t('desktop.interface.statusNetworkError'),
    'Timeout': t('desktop.interface.statusTimeout'),
    'Error': t('desktop.interface.statusConfigError')
  }
  return statusMap[connectionStatus.value] || connectionStatus.value
})

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
      error.value = t('desktop.interface.errorBackendUnavailable');
      connectionStatus.value = 'Configuration Error';
    } else if (err.message && err.message.includes('Network Error')) {
      error.value = t('desktop.interface.errorNetworkConnectivity');
      connectionStatus.value = 'Network Error';
    } else if (err.message && err.message.includes('timeout')) {
      error.value = t('desktop.interface.errorConfigTimeout');
      connectionStatus.value = 'Timeout';
    } else {
      error.value = t('desktop.interface.errorConfigFailed');
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
      return 'text-green-600'
    case 'Disconnected':
      return 'text-red-600'
    case 'Connecting...':
      return 'text-yellow-600'
    case 'Configuration Error':
      return 'text-red-600'
    case 'Network Error':
      return 'text-red-600'
    case 'Timeout':
      return 'text-orange-600'
    default:
      return 'text-autobot-text-secondary'
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
      error.value = t('desktop.interface.errorServiceTimeout');
    } else {
      const isServiceDisabled = err.message.includes('Connection refused') ||
                                err.message.includes('Network Error') ||
                                err.message.includes('Failed to fetch');

      if (isServiceDisabled) {
        error.value = t('desktop.interface.errorServiceDisabled');
      } else {
        error.value = t('desktop.interface.errorVncConnection', { error: err.message });
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
  error.value = t('desktop.interface.errorVncConnection', { error: error.message || error })
}

const handleDesktopTimeout = () => {
  logger.warn('Desktop connection timeout')
  loading.value = false
  connectionStatus.value = 'Timeout'
  error.value = t('desktop.interface.errorServiceTimeout')
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
    error.value = t('desktop.interface.errorInitFailed')
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

// Desktop interaction actions (Issue #74)
async function takeScreenshot() {
  const result = await vncControls.captureScreenshot()
  if (result.status === 'success' && result.image_data) {
    screenshotData.value = `data:image/png;base64,${result.image_data}`
    showScreenshotModal.value = true
  } else {
    logger.error('Screenshot failed:', result.message)
    error.value = result.message
  }
}

async function handleTypeText() {
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

async function sendCtrlAltDel() {
  const result = await vncControls.sendCtrlAltDel()
  if (result.status !== 'success') {
    logger.error('Ctrl+Alt+Del failed:', result.message)
    error.value = result.message
  }
}

async function pasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText()
    const result = await vncControls.syncClipboard(text)
    if (result.status !== 'success') {
      logger.error('Clipboard sync failed:', result.message)
      error.value = result.message
    }
  } catch (err) {
    logger.error('Clipboard read failed:', err)
    error.value = t('desktop.interface.errorClipboardRead')
  }
}

function downloadScreenshot() {
  if (!screenshotData.value) return

  const link = document.createElement('a')
  link.href = screenshotData.value
  link.download = `desktop-screenshot-${Date.now()}.png`
  link.click()
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
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: var(--bg-primary);
}

.desktop-header {
  padding: 1rem 1.5rem;
  background-color: var(--bg-card);
  border-bottom: 1px solid var(--border-default);
}

.desktop-container {
  flex: 1;
  position: relative;
  overflow: hidden;
}

.vnc-wrapper {
  width: 100%;
  height: 100%;
}

.vnc-iframe {
  width: 100%;
  height: 100%;
  border: none;
  min-height: 600px;
}

/* Loading and error styles moved to UnifiedLoadingView */

.desktop-controls {
  padding: 0.75rem 1.5rem;
  background-color: var(--bg-card);
  border-top: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.control-btn {
  padding: 0.375rem 0.75rem;
  font-size: 0.875rem;
  background-color: var(--bg-secondary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.control-btn:hover {
  background-color: var(--bg-tertiary);
}

.connection-status {
  font-size: 0.875rem;
  font-weight: 500;
}

/* Desktop Actions Toolbar (Issue #74) */
.desktop-actions {
  padding: 0.75rem 1.5rem;
  background-color: var(--bg-card);
  border-top: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  gap: 1rem;
}

.actions-label {
  flex-shrink: 0;
}

.actions-buttons {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.action-btn {
  padding: 0.375rem 0.75rem;
  font-size: 0.875rem;
  background-color: var(--color-primary-bg);
  color: var(--color-primary);
  border: 1px solid var(--color-primary-light);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.action-btn:hover {
  background-color: var(--color-primary-bg-hover);
}

/* Screenshot Modal (Issue #74) */
.screenshot-modal {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.75);
}

.screenshot-content {
  background-color: var(--bg-card);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-2xl);
  max-width: 56rem;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}

.screenshot-header {
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.screenshot-body {
  padding: 1.5rem;
  overflow: auto;
  flex: 1;
}

.screenshot-image {
  max-width: 100%;
  height: auto;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
}

.screenshot-footer {
  padding: 1rem 1.5rem;
  border-top: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
}

.download-btn {
  padding: 0.5rem 1rem;
  background-color: var(--color-primary);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.download-btn:hover {
  background-color: var(--color-primary-hover);
}

.cancel-btn {
  padding: 0.5rem 1rem;
  background-color: var(--bg-secondary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.cancel-btn:hover {
  background-color: var(--bg-tertiary);
}

.close-btn {
  font-size: 1.5rem;
  color: var(--text-muted);
  background: none;
  border: none;
  cursor: pointer;
  transition: color 0.15s ease;
}

.close-btn:hover {
  color: var(--text-primary);
}

/* Type Dialog (Issue #74) */
.type-dialog-modal {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.5);
}

.type-dialog-content {
  background-color: var(--bg-card);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-2xl);
  width: 100%;
  max-width: 28rem;
}

.type-dialog-header {
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.type-dialog-body {
  padding: 1.5rem;
}

.type-textarea {
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  background-color: var(--bg-secondary);
  color: var(--text-primary);
  resize: none;
  transition: border-color 0.15s ease;
}

.type-textarea:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px var(--color-primary-bg);
}

.type-dialog-footer {
  padding: 1rem 1.5rem;
  border-top: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
}

.type-btn {
  padding: 0.5rem 1rem;
  background-color: var(--color-primary);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.type-btn:hover {
  background-color: var(--color-primary-hover);
}

.type-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
