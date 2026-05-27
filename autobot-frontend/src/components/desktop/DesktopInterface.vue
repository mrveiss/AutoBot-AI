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
      <LoadingBoundary
        :loading="loading"
        :error="error"
        :timeout-ms="15000"
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
      </LoadingBoundary>
    </div>

    <div class="desktop-controls">
      <button @click="toggleFullscreen" class="control-btn">
        <span v-if="isFullscreen">{{ $t('desktop.interface.exitFullscreen') }}</span>
        <span v-else>{{ $t('desktop.interface.fullscreen') }}</span>
      </button>
      <button @click="reconnect" class="control-btn">
        {{ $t('desktop.interface.reconnect') }}
      </button>
      <button
        v-if="vncUrl"
        class="control-btn"
        :title="$t('desktop.interface.openInNewWindow')"
        @click="window.open(vncUrl, '_blank', 'noopener')"
      >
        {{ $t('desktop.interface.openInNewWindow') }}
      </button>
      <button @click="showContextPanel = !showContextPanel" class="control-btn" :title="$t('desktop.contextPanel.title')">
        ℹ️
      </button>
      <div class="connection-status">
        <span :class="connectionStatusClass">{{ connectionStatusDisplay }}</span>
      </div>
    </div>

    <!-- Context Panel (collapsible right-side) -->
    <div v-if="showContextPanel" class="context-panel-overlay">
      <DesktopContextPanel />
    </div>

    <!-- Desktop Actions Toolbar (Issue #74) -->
    <div class="desktop-actions">
      <div class="actions-label text-sm font-medium text-autobot-text-secondary">
        {{ $t('desktop.interface.desktopActions') }}
      </div>
      <div class="actions-buttons">
        <TouchFriendlyButton
          variant="primary"
          size="sm"
          @click="takeScreenshot"
          :title="$t('desktop.interface.screenshot')"
          class="touch-action-btn"
        >
          📷 {{ $t('desktop.interface.screenshot') }}
        </TouchFriendlyButton>
        <TouchFriendlyButton
          variant="primary"
          size="sm"
          @click="showTypeDialog = true"
          :title="$t('desktop.interface.typeText')"
          class="touch-action-btn"
        >
          ⌨️ {{ $t('desktop.interface.typeText') }}
        </TouchFriendlyButton>
        <TouchFriendlyButton
          variant="error"
          size="sm"
          @click="sendCtrlAltDel"
          :title="$t('desktop.interface.ctrlAltDel')"
          class="touch-action-btn"
        >
          🔴 {{ $t('desktop.interface.ctrlAltDel') }}
        </TouchFriendlyButton>
        <TouchFriendlyButton
          variant="primary"
          size="sm"
          @click="pasteFromClipboard"
          :title="$t('desktop.interface.paste')"
          class="touch-action-btn"
        >
          📋 {{ $t('desktop.interface.paste') }}
        </TouchFriendlyButton>
      </div>
    </div>

    <!-- Screenshot Modal (Issue #74) -->
    <Teleport to="body">
      <div v-if="showScreenshotModal" class="screenshot-modal" @click="showScreenshotModal = false">
        <div class="screenshot-content" @click.stop>
          <div class="screenshot-header">
            <h3 class="text-lg font-semibold text-autobot-text-primary">{{ $t('desktop.interface.screenshotTitle') }}</h3>
            <button
              @click="showScreenshotModal = false"
              class="close-btn"
              :aria-label="$t('common.close')"
              :title="$t('common.close')"
              type="button"
            >×</button>
          </div>
          <div class="screenshot-body">
            <img v-if="screenshotData" :src="screenshotData" :alt="$t('desktop.interface.screenshotAlt')" class="screenshot-image" loading="lazy" />
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
            <button
              @click="showTypeDialog = false"
              class="close-btn"
              :aria-label="$t('common.close')"
              :title="$t('common.close')"
              type="button"
            >×</button>
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

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
// MIGRATED: Removed environment.js, using AppConfig.js only
import appConfig from '@/config/AppConfig.js'
import LoadingBoundary from '@/components/ui/LoadingBoundary.vue'
import TouchFriendlyButton from '@/components/ui/TouchFriendlyButton.vue'
import DesktopContextPanel from '@/components/desktop/DesktopContextPanel.vue'
import { useLoadingState } from '@/composables/useLoadingState'
import { useVncControls } from '@/composables/useVncControls'
import { usePollingJob } from '@/composables/usePollingJob'
import { createLogger } from '@/utils/debugUtils'
import type { SelectorHost } from '@/composables/useHostSelector'

/** Optional host prop — when provided, drives the VNC URL directly from the
 *  host record rather than fetching from AppConfig (Issue #4977). */
interface Props {
  host?: SelectorHost | null
}

const props = withDefaults(defineProps<Props>(), { host: null })

const { t } = useI18n()
const logger = createLogger('DesktopInterface')

// Async operation composables
const { isLoading: loadingVnc, wrap: wrapLoadVnc } = useLoadingState()
const { isLoading: loadingCheck, wrap: wrapCheckConnection } = useLoadingState()
const errorVnc = ref<Error | null>(null)
const errorCheck = ref<Error | null>(null)

// VNC controls (Issue #74)
const vncControls = useVncControls()
const showContextPanel = ref(false)
const showScreenshotModal = ref(false)
const screenshotData = ref<string | null>(null)
const textToType = ref('')
const showTypeDialog = ref(false)

const vncFrame = ref<HTMLIFrameElement | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)
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

// VNC connection URL - will be loaded asynchronously from AppConfig or derived from host prop
const vncUrl = ref('') // Will be loaded on mount

/** Build VNC URL from a SelectorHost record (Issue #4977). */
const buildHostVncUrl = (h: SelectorHost): string => {
  const port = h.vnc_port || 6080
  const scheme = window.location.protocol === 'https:' ? 'https' : 'http'
  return `${scheme}://${h.host}:${port}/vnc.html?autoconnect=true`
}

// Load dynamic VNC URL on component mount
const loadVncUrlFn = async () => {
  // Issue #4977: when a host prop is supplied, derive URL directly — no AppConfig call needed
  if (props.host) {
    vncUrl.value = buildHostVncUrl(props.host)
  } else {
    const dynamicVncUrl = await appConfig.getVncUrl('desktop');
    vncUrl.value = dynamicVncUrl;
  }
  // Clear any previous errors and update status
  error.value = null;
  loading.value = false;
  connectionStatus.value = 'Connected';
}

const loadVncUrl = async () => {
  errorVnc.value = null
  await wrapLoadVnc(loadVncUrlFn).catch(err => {
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

// Issue #4977: when the host prop changes, reload the VNC URL
watch(() => props.host, async (newHost: SelectorHost | null | undefined) => {
  if (newHost !== undefined) {
    loading.value = true
    error.value = null
    connectionStatus.value = 'Connecting...'
    await loadVncUrl()
  }
})

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
  errorCheck.value = null
  await wrapCheckConnection(checkConnectionFn).catch(err => {
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

// LoadingBoundary event handlers
const handleDesktopConnected = () => {
  loading.value = false
  connectionStatus.value = 'Connected'
}

const handleDesktopError = (err: Error | unknown) => {
  logger.error('Desktop connection error:', err)
  loading.value = false
  connectionStatus.value = 'Error'
  error.value = t('desktop.interface.errorVncConnection', { error: error.value.message || error })
}

const handleDesktopTimeout = () => {
  logger.warn('Desktop connection timeout')
  loading.value = false
  connectionStatus.value = 'Timeout'
  error.value = t('desktop.interface.errorServiceTimeout')
}

const { start: startConnectionCheck } = usePollingJob(
  async () => { await checkConnection() },
  { intervalMs: 10000, maxAttempts: Infinity }
)

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

  // Initial connection check after 2s, then poll every 10s
  setTimeout(() => startConnectionCheck(''), 2000)

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
  // Clean up event listener
  document.removeEventListener('fullscreenchange', handleFullscreenChange)
})
</script>

<style scoped>
.desktop-interface {
  display: flex;
  flex-direction: column;
  height: 100%;
  position: relative;
  background-color: var(--bg-primary);
}

.desktop-header {
  padding: var(--spacing-4) var(--spacing-6);
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
  contain: layout style paint;
}

/* Loading and error styles handled by LoadingBoundary */

.desktop-controls {
  padding: var(--spacing-3) var(--spacing-6);
  background-color: var(--bg-card);
  border-top: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.control-btn {
  padding: var(--spacing-1-5) var(--spacing-3);
  font-size: var(--text-sm);
  background-color: var(--bg-secondary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background-color var(--duration-150) var(--ease-out);
}

.control-btn:hover {
  background-color: var(--bg-tertiary);
}

.connection-status {
  font-size: var(--text-sm);
  font-weight: 500;
}

/* Desktop Actions Toolbar (Issue #74) */
.desktop-actions {
  padding: var(--spacing-3) var(--spacing-6);
  background-color: var(--bg-card);
  border-top: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
}

.actions-label {
  flex-shrink: 0;
}

.actions-buttons {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  flex-wrap: wrap;
}

.action-btn {
  padding: var(--spacing-1-5) var(--spacing-3);
  font-size: var(--text-sm);
  background-color: var(--color-primary-bg);
  color: var(--color-primary);
  border: 1px solid var(--color-primary-light);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background-color var(--duration-150) var(--ease-out);
}

.action-btn:hover {
  background-color: var(--color-primary-bg-hover);
}

/* Touch-friendly button variant for desktop actions */
.touch-action-btn {
  margin: var(--spacing-0);
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
  padding: var(--spacing-4) var(--spacing-6);
  border-bottom: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.screenshot-body {
  padding: var(--spacing-6);
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
  padding: var(--spacing-4) var(--spacing-6);
  border-top: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--spacing-2);
}

.download-btn {
  padding: var(--spacing-2) var(--spacing-4);
  background-color: var(--color-primary);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background-color var(--duration-150) var(--ease-out);
}

.download-btn:hover {
  background-color: var(--color-primary-hover);
}

.cancel-btn {
  padding: var(--spacing-2) var(--spacing-4);
  background-color: var(--bg-secondary);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background-color var(--duration-150) var(--ease-out);
}

.cancel-btn:hover {
  background-color: var(--bg-tertiary);
}

.close-btn {
  font-size: var(--text-2xl);
  color: var(--text-muted);
  background: none;
  border: none;
  cursor: pointer;
  transition: color var(--duration-150) var(--ease-out);
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
  padding: var(--spacing-4) var(--spacing-6);
  border-bottom: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.type-dialog-body {
  padding: var(--spacing-6);
}

.type-textarea {
  width: 100%;
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  background-color: var(--bg-secondary);
  color: var(--text-primary);
  resize: none;
  transition: border-color var(--duration-150) var(--ease-out);
}

.type-textarea:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px var(--color-primary-bg);
}
.type-textarea:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.type-dialog-footer {
  padding: var(--spacing-4) var(--spacing-6);
  border-top: 1px solid var(--border-default);
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--spacing-2);
}

.type-btn {
  padding: var(--spacing-2) var(--spacing-4);
  background-color: var(--color-primary);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background-color var(--duration-150) var(--ease-out);
}

.type-btn:hover {
  background-color: var(--color-primary-hover);
}

.type-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Context Panel (Issue #4771) */
.context-panel-overlay {
  position: absolute;
  top: 0;
  right: 0;
  width: 20rem;
  height: 100%;
  overflow-y: auto;
  z-index: 10;
  padding: var(--spacing-4);
  background-color: var(--bg-card);
  border-left: 1px solid var(--border-default);
  box-shadow: var(--shadow-lg, -2px 0 8px rgba(0, 0, 0, 0.15));
}
</style>
