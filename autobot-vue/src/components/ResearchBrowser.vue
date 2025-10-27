<template>
  <div class="research-browser">
    <!-- Research Session Header -->
    <div class="research-header bg-blue-50 border-b border-blue-200 p-4">
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-3">
          <i class="fas fa-search text-blue-600"></i>
          <div>
            <h3 class="text-lg font-semibold text-blue-800">Research Browser Session</h3>
            <p class="text-sm text-blue-600">{{ sessionId ? `Session: ${sessionId.slice(0, 8)}...` : 'No active session' }}</p>
          </div>
        </div>
        <div class="flex items-center space-x-2">
          <span class="status-badge" :class="statusClass">{{ status || 'Unknown' }}</span>
          <button @click="refreshStatus" class="btn btn-secondary btn-sm" :disabled="isRefreshingStatus" aria-label="Refresh status">
            <i class="fas fa-sync-alt" :class="{ 'fa-spin': isRefreshingStatus }"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Current URL Display -->
    <div v-if="currentUrl" class="url-bar bg-gray-100 border-b p-3">
      <div class="flex items-center space-x-3">
        <i class="fas fa-globe text-gray-500"></i>
        <span class="text-sm text-gray-700 font-mono">{{ currentUrl }}</span>
        <button @click="copyUrl" class="btn btn-outline btn-xs" title="Copy URL">
          <i class="fas fa-copy"></i>
        </button>
      </div>
    </div>

    <!-- Interaction Required Alert -->
    <div v-if="interactionRequired" class="interaction-alert bg-yellow-50 border-l-4 border-yellow-400 p-4">
      <div class="flex items-center">
        <div class="flex-shrink-0">
          <i class="fas fa-exclamation-triangle text-yellow-400"></i>
        </div>
        <div class="ml-3 flex-1">
          <p class="text-sm text-yellow-800">
            {{ interactionMessage || 'User interaction required to continue' }}
          </p>
        </div>
        <div class="ml-4 flex space-x-2">
          <button @click="handleWaitForUser" class="btn btn-primary btn-sm" :disabled="isWaitingForUser" aria-label="Wait for user">
            <i class="fas" :class="isWaitingForUser ? 'fa-spinner fa-spin' : 'fa-clock'" class="mr-1"></i>
            {{ isWaitingForUser ? 'Waiting...' : 'Wait' }}
          </button>
          <button @click="openBrowserSession" class="btn btn-secondary btn-sm">
            <i class="fas fa-external-link-alt mr-1"></i>
            Open Browser
          </button>
        </div>
      </div>
    </div>

    <!-- Research Results -->
    <div v-if="researchResults && researchResults.length > 0" class="research-results p-4">
      <h4 class="text-md font-semibold text-gray-800 mb-3">Research Results</h4>
      <div class="space-y-4">
        <div v-for="(result, index) in researchResults" :key="index" class="result-card bg-white border rounded-lg p-4 shadow-sm">
          <div class="flex items-start justify-between mb-2">
            <div class="flex-1">
              <h5 class="text-sm font-medium text-gray-900">{{ result.query }}</h5>
              <p class="text-xs text-gray-500 mt-1">{{ result.url }}</p>
            </div>
            <span class="status-badge" :class="getResultStatusClass(result.status)">{{ result.status }}</span>
          </div>

          <div v-if="result.content && result.content.success" class="content-preview mt-3">
            <div class="text-xs font-medium text-gray-600 mb-2">Content Preview:</div>
            <div class="text-sm text-gray-700 bg-gray-50 rounded p-2 max-h-32 overflow-y-auto">
              {{ result.content.text_content ? result.content.text_content.substring(0, 300) + '...' : 'No content extracted' }}
            </div>

            <!-- Structured Data -->
            <div v-if="result.content.structured_data && result.content.structured_data.headings && result.content.structured_data.headings.length > 0" class="mt-2">
              <div class="text-xs font-medium text-gray-600 mb-1">Headings:</div>
              <div class="flex flex-wrap gap-1">
                <span v-for="heading in result.content.structured_data.headings.slice(0, 3)" :key="heading.text"
                      class="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">
                  {{ heading.level }}: {{ heading.text.substring(0, 30) }}{{ heading.text.length > 30 ? '...' : '' }}
                </span>
              </div>
            </div>
          </div>

          <!-- Interaction Required for This Result -->
          <div v-if="result.interaction_required" class="mt-3 p-3 bg-yellow-50 border border-yellow-200 rounded">
            <div class="flex items-center justify-between">
              <div class="text-sm text-yellow-800">
                <i class="fas fa-hand-paper mr-1"></i>
                Manual intervention required
              </div>
              <button @click="openBrowserForResult(result)" class="btn btn-warning btn-sm">
                <i class="fas fa-external-link-alt mr-1"></i>
                Open Browser
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Browser Session Controls -->
    <div v-if="sessionId" class="session-controls border-t p-4 bg-gray-50">
      <h4 class="text-md font-semibold text-gray-800 mb-3">Session Controls</h4>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
        <button @click="() => handleSessionAction('extract_content')"
                class="btn btn-outline btn-sm" :disabled="isPerformingAction" aria-label="Extract content">
          <i class="fas" :class="isPerformingAction ? 'fa-spinner fa-spin' : 'fa-file-alt'" class="mr-1"></i>
          Extract Content
        </button>

        <button @click="() => handleSessionAction('save_mhtml')"
                class="btn btn-outline btn-sm" :disabled="isPerformingAction" aria-label="Save MHTML">
          <i class="fas" :class="isPerformingAction ? 'fa-spinner fa-spin' : 'fa-save'" class="mr-1"></i>
          Save MHTML
        </button>

        <button @click="navigateToUrl"
                class="btn btn-outline btn-sm" :disabled="isNavigating" aria-label="Navigate to URL">
          <i class="fas" :class="isNavigating ? 'fa-spinner fa-spin' : 'fa-arrow-right'" class="mr-1"></i>
          {{ isNavigating ? 'Navigating...' : 'Navigate' }}
        </button>

        <button @click="closeSessionHandler"
                class="btn btn-danger btn-sm" :disabled="isClosingSession" aria-label="Close session">
          <i class="fas" :class="isClosingSession ? 'fa-spinner fa-spin' : 'fa-times'" class="mr-1"></i>
          {{ isClosingSession ? 'Closing...' : 'Close Session' }}
        </button>
      </div>

      <!-- URL Input for Navigation -->
      <div v-if="showNavigationInput" class="mt-3">
        <div class="flex space-x-2">
          <input v-model="navigationUrl"
                 type="url"
                 placeholder="Enter URL to navigate to..."
                 class="flex-1 px-3 py-2 border border-gray-300 rounded text-sm"
                 :disabled="isNavigating"
                 @keyup.enter="performNavigation">
          <button @click="performNavigation"
                  class="btn btn-primary btn-sm" :disabled="!navigationUrl || isNavigating">
            <i class="fas" :class="isNavigating ? 'fa-spinner fa-spin' : 'fa-arrow-right'"></i>
            {{ isNavigating ? 'Going...' : 'Go' }}
          </button>
          <button @click="showNavigationInput = false"
                  class="btn btn-secondary btn-sm">
            Cancel
          </button>
        </div>
      </div>
    </div>

    <!-- Unified Browser -->
    <div class="browser-container border-t">
      <div class="browser-header bg-blue-50 p-3 flex items-center justify-between">
        <div class="flex items-center space-x-2">
          <i class="fab fa-chrome text-blue-600"></i>
          <span class="text-sm font-medium text-blue-800">Unified Browser</span>
          <span v-if="sessionId && !agentPaused" class="text-xs text-blue-600">(Agent Research Active)</span>
          <span v-if="sessionId && agentPaused" class="text-xs text-orange-600">(Agent Paused - User Control)</span>
        </div>
        <div class="flex items-center space-x-2">
          <!-- URL Input Bar -->
          <div class="flex items-center space-x-1" :class="{ 'opacity-50': isNavigatingBrowser }">
            <input
              v-model="browserUrl"
              type="url"
              placeholder="Enter URL to navigate..."
              class="px-2 py-1 border border-gray-300 rounded text-sm w-48"
              :disabled="sessionId && !agentPaused || isNavigatingBrowser"
              @keyup.enter="navigateToBrowserUrl"
            >
            <button
              @click="navigateToBrowserUrl"
              :disabled="!browserUrl || isNavigatingBrowser || (sessionId && !agentPaused)"
              class="btn btn-primary btn-xs"
              aria-label="Navigate browser">
              <i class="fas" :class="isNavigatingBrowser ? 'fa-spinner fa-spin' : 'fa-arrow-right'"></i>
            </button>
          </div>

          <!-- Agent Control Buttons -->
          <div v-if="sessionId" class="flex items-center space-x-1 border-l border-gray-300 pl-2">
            <button
              v-if="!agentPaused"
              @click="pauseAgent"
              class="btn btn-warning btn-xs"
              title="Pause agent and take control of browser"
              :disabled="isPausingAgent"
              aria-label="Pause agent">
              <i class="fas" :class="isPausingAgent ? 'fa-spinner fa-spin' : 'fa-pause'" class="mr-1"></i>
              {{ isPausingAgent ? 'Pausing...' : 'Take Control' }}
            </button>
            <button
              v-if="agentPaused"
              @click="resumeAgent"
              class="btn btn-success btn-xs"
              title="Resume agent research session"
              :disabled="isResumingAgent"
              aria-label="Resume agent">
              <i class="fas" :class="isResumingAgent ? 'fa-spinner fa-spin' : 'fa-play'" class="mr-1"></i>
              {{ isResumingAgent ? 'Resuming...' : 'Resume Agent' }}
            </button>
          </div>
          <button @click="toggleBrowserView" class="btn btn-outline btn-xs">
            <i class="fas" :class="showBrowser ? 'fa-eye-slash' : 'fa-eye'"></i>
            {{ showBrowser ? 'Hide Browser' : 'Show Browser' }}
          </button>
          <button @click="popoutBrowser" class="btn btn-primary btn-xs">
            <i class="fas fa-external-link-alt mr-1"></i>
            Pop Out
          </button>
        </div>
      </div>

      <div v-if="showBrowser" class="browser-content">
        <PopoutChromiumBrowser
          :session-id="activeSessionId"
          :initial-url="currentUrlForDisplay"
          :can-resize="true"
          :auto-popout="false"
          @close="onBrowserClose"
          @navigate="onBrowserNavigate"
          @interact="onBrowserInteract"
          @popout="onBrowserPopout"
          @dock="onBrowserDock"
        />
      </div>

      <!-- Browser hidden message -->
      <div v-else class="p-4 text-center text-gray-500">
        <i class="fas fa-eye text-4xl mb-3 opacity-30"></i>
        <p class="text-sm">Browser is hidden</p>
        <p class="text-xs mt-2 text-blue-600">Click "Show Browser" above to observe {{ sessionId ? 'agent research activity' : 'browser' }}</p>
        <p v-if="sessionId" class="text-xs mt-1 text-orange-600">⚠️ Agent may be actively researching in the background</p>
      </div>
    </div>

    <!-- Action Results -->
    <div v-if="actionResult" class="action-result p-4 border-t">
      <div class="bg-white border rounded-lg p-3">
        <div class="flex items-center justify-between mb-2">
          <h5 class="text-sm font-medium text-gray-900">Action Result</h5>
          <button @click="actionResult = null" class="text-gray-400 hover:text-gray-600">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <pre class="text-xs text-gray-600 bg-gray-50 rounded p-2 overflow-auto max-h-40">{{ JSON.stringify(actionResult, null, 2) }}</pre>
      </div>
    </div>

    <!-- Combined Loading State Indicator -->
    <div v-if="isPerformingAction || isNavigating || isNavigatingBrowser" class="loading-indicator">
      <div class="loading-bar"></div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import apiClient from '@/utils/ApiClient'
import PopoutChromiumBrowser from './PopoutChromiumBrowser.vue'
import { useAsyncHandler } from '@/composables/useErrorHandler'

export default {
  name: 'ResearchBrowser',
  components: {
    PopoutChromiumBrowser
  },
  props: {
    sessionId: {
      type: String,
      default: null
    },
    researchData: {
      type: Object,
      default: () => ({})
    }
  },
  setup(props) {
    const status = ref('unknown')
    const currentUrl = ref('')
    const interactionRequired = ref(false)
    const interactionMessage = ref('')
    const browserInfo = ref(null)
    const showBrowser = ref(false)
    const showNavigationInput = ref(false)
    const navigationUrl = ref('')
    const actionResult = ref(null)
    const currentBrowserUrl = ref('')
    const browserUrl = ref('')
    const agentPaused = ref(false)

    const researchResults = computed(() => {
      return props.researchData?.results || []
    })

    // Unified session ID - use research session if available, otherwise manual
    const activeSessionId = computed(() => {
      return props.sessionId || 'unified-browser'
    })

    // Get current URL from research results or user input
    const currentUrlForDisplay = computed(() => {
      if (researchResults.value.length > 0) {
        return researchResults.value[0].url || researchResults.value[0].navigation?.url
      }
      return currentBrowserUrl.value || currentUrl.value || 'about:blank'
    })

    const statusClass = computed(() => {
      const statusClasses = {
        'active': 'bg-green-100 text-green-800',
        'waiting_for_user': 'bg-yellow-100 text-yellow-800',
        'error': 'bg-red-100 text-red-800',
        'closed': 'bg-gray-100 text-gray-800',
        'initializing': 'bg-blue-100 text-blue-800'
      }
      return statusClasses[status.value] || 'bg-gray-100 text-gray-800'
    })

    const getResultStatusClass = (resultStatus) => {
      const statusClasses = {
        'completed': 'bg-green-100 text-green-800',
        'interaction_required': 'bg-yellow-100 text-yellow-800',
        'mhtml_fallback': 'bg-orange-100 text-orange-800',
        'error': 'bg-red-100 text-red-800'
      }
      return statusClasses[resultStatus] || 'bg-gray-100 text-gray-800'
    }

    // 1. Migrate refreshStatus - Complex: 2 sequential API calls
    const { execute: refreshStatus, loading: isRefreshingStatus } = useAsyncHandler(
      async () => {
        if (!props.sessionId) return null

        // Two sequential API calls
        const statusResponse = await apiClient.get(`/api/research/session/${props.sessionId}/status`)
        const browserResponse = await apiClient.get(`/api/research/browser/${props.sessionId}`)

        return { statusResponse, browserResponse }
      },
      {
        onSuccess: (result) => {
          if (!result) return

          const { statusResponse, browserResponse } = result

          // Update all state from both responses
          status.value = statusResponse.data.status
          currentUrl.value = statusResponse.data.current_url
          currentBrowserUrl.value = statusResponse.data.current_url
          interactionRequired.value = statusResponse.data.interaction_required
          interactionMessage.value = statusResponse.data.interaction_message
          browserInfo.value = browserResponse.data
        }
      }
    )

    // 2. Migrate handleWaitForUser - Chains refreshStatus
    const { execute: handleWaitForUser, loading: isWaitingForUser } = useAsyncHandler(
      async () => {
        return await apiClient.post('/api/research/session/action', {
          session_id: props.sessionId,
          action: 'wait',
          timeout_seconds: 300
        })
      },
      {
        onSuccess: async (response) => {
          actionResult.value = response.data
          await refreshStatus()
        },
        onError: (error) => {
          actionResult.value = { error: error.message }
        }
      }
    )

    // 3. Migrate handleSessionAction - Chains refreshStatus
    const { execute: performSessionAction, loading: isPerformingAction } = useAsyncHandler(
      async (action) => {
        return await apiClient.post('/api/research/session/action', {
          session_id: props.sessionId,
          action: action
        })
      },
      {
        onSuccess: async (response) => {
          actionResult.value = response.data
          await refreshStatus()
        },
        onError: (error) => {
          actionResult.value = { error: error.message }
        }
      }
    )

    // Wrapper to maintain original function signature
    const handleSessionAction = (action) => {
      performSessionAction(action)
    }

    // 4. Migrate performNavigation - Chains refreshStatus
    const { execute: performNavigation, loading: isNavigating } = useAsyncHandler(
      async () => {
        if (!navigationUrl.value) return null

        return await apiClient.post(`/api/research/session/${props.sessionId}/navigate`, {
          url: navigationUrl.value
        })
      },
      {
        onSuccess: async (response) => {
          if (!response) return

          actionResult.value = response.data
          showNavigationInput.value = false
          navigationUrl.value = ''
          await refreshStatus()
        },
        onError: (error) => {
          actionResult.value = { error: error.message }
        }
      }
    )

    // 5. Migrate closeSession - With confirmation dialog
    const { execute: closeSession, loading: isClosingSession } = useAsyncHandler(
      async () => {
        return await apiClient.delete(`/api/research/session/${props.sessionId}`)
      },
      {
        onSuccess: () => {
          window.location.reload()
        }
      }
    )

    // Wrapper to handle confirmation before execution
    const closeSessionHandler = async () => {
      if (!confirm('Are you sure you want to close this research session?')) return
      await closeSession()
    }

    // 6. Migrate navigateToBrowserUrl - Conditional POST, complex logic
    const { execute: navigateToBrowserUrl, loading: isNavigatingBrowser } = useAsyncHandler(
      async () => {
        if (!browserUrl.value) return null

        // Always show the browser when navigating
        showBrowser.value = true

        // If there's no research session, create one for this navigation
        if (!props.sessionId) {
          const response = await apiClient.post('/api/research/url', {
            conversation_id: 'unified-browser-session',
            url: browserUrl.value,
            extract_content: false
          })
          return response
        }

        return null
      },
      {
        onSuccess: (response) => {
          // Update the browser URL
          currentBrowserUrl.value = browserUrl.value

          if (response && response.data && response.data.success && response.data.session_id) {
            // Successfully created research session for unified browser
          }

          // Clear the input
          browserUrl.value = ''
        },
        onError: () => {
          // Even on error, try to navigate the browser directly
          currentBrowserUrl.value = browserUrl.value
          showBrowser.value = true
          browserUrl.value = ''
        }
      }
    )

    // 7. Migrate pauseAgent - POST manual_intervention
    const { execute: pauseAgent, loading: isPausingAgent } = useAsyncHandler(
      async () => {
        if (!props.sessionId) return null

        return await apiClient.post('/api/research/session/action', {
          session_id: props.sessionId,
          action: 'manual_intervention'
        })
      },
      {
        onSuccess: (response) => {
          if (!response) return

          if (response.data && response.data.success) {
            agentPaused.value = true

            actionResult.value = {
              message: 'Agent paused - you now have control of the browser',
              timestamp: new Date().toISOString()
            }
          }
        }
      }
    )

    // 8. Migrate resumeAgent - Chains refreshStatus
    const { execute: resumeAgent, loading: isResumingAgent } = useAsyncHandler(
      async () => {
        if (!props.sessionId) return null

        return await apiClient.post('/api/research/session/action', {
          session_id: props.sessionId,
          action: 'wait',
          timeout_seconds: 300
        })
      },
      {
        onSuccess: async (response) => {
          if (!response) return

          agentPaused.value = false

          actionResult.value = {
            message: 'Agent resumed - research session is now active',
            timestamp: new Date().toISOString()
          }

          await refreshStatus()
        }
      }
    )

    const openBrowserSession = () => {
      if (browserInfo.value && browserInfo.value.docker_browser && browserInfo.value.docker_browser.vnc_url) {
        window.open(browserInfo.value.docker_browser.vnc_url, '_blank', 'width=1280,height=720')
      }
    }

    const openBrowserForResult = (result) => {
      if (result.browser_url) {
        showBrowser.value = true
      } else {
        openBrowserSession()
      }
    }

    const navigateToUrl = () => {
      showNavigationInput.value = true
    }

    const copyUrl = async () => {
      if (currentUrl.value) {
        await navigator.clipboard.writeText(currentUrl.value)
      }
    }

    const toggleBrowserView = () => {
      showBrowser.value = !showBrowser.value
    }

    const onBrowserLoad = () => {
      // Browser iframe loaded
    }

    // PopoutChromiumBrowser event handlers
    const onBrowserClose = () => {
      showBrowser.value = false
    }

    const onBrowserNavigate = (data) => {
      currentBrowserUrl.value = data.url
      currentUrl.value = data.url
    }

    const onBrowserInteract = (data) => {
      // Browser interaction
    }

    const onBrowserPopout = () => {
      // Browser popped out
    }

    const onBrowserDock = () => {
      // Browser docked
    }

    const popoutBrowser = () => {
      showBrowser.value = true
    }

    const relaunchBrowser = () => {
      showBrowser.value = true
    }

    // Auto-refresh status periodically
    let statusInterval

    onMounted(() => {
      if (props.sessionId) {
        refreshStatus()
        statusInterval = setInterval(refreshStatus, 10000) // Refresh every 10 seconds
        showBrowser.value = true
      } else if (props.researchData && props.researchData.results && props.researchData.results.length > 0) {
        showBrowser.value = true
      }

      // Always show browser for better observability
      showBrowser.value = true
    })

    onUnmounted(() => {
      if (statusInterval) {
        clearInterval(statusInterval)
      }
    })

    // Watch for research data changes to auto-show browser
    watch(() => props.researchData, (newData) => {
      if (newData && newData.results && newData.results.length > 0) {
        showBrowser.value = true
      }
    }, { deep: true })

    return {
      // Loading states (exposed for UI integration)
      isRefreshingStatus,
      isWaitingForUser,
      isPerformingAction,
      isNavigating,
      isClosingSession,
      isNavigatingBrowser,
      isPausingAgent,
      isResumingAgent,

      // State
      status,
      currentUrl,
      interactionRequired,
      interactionMessage,
      browserInfo,
      showBrowser,
      showNavigationInput,
      navigationUrl,
      actionResult,
      currentBrowserUrl,
      browserUrl,
      agentPaused,

      // Computed
      activeSessionId,
      currentUrlForDisplay,
      researchResults,
      statusClass,
      getResultStatusClass,

      // Methods
      refreshStatus,
      handleWaitForUser,
      handleSessionAction,
      performNavigation,
      closeSession,
      closeSessionHandler,
      navigateToBrowserUrl,
      pauseAgent,
      resumeAgent,
      openBrowserSession,
      openBrowserForResult,
      navigateToUrl,
      copyUrl,
      toggleBrowserView,
      onBrowserLoad,
      onBrowserClose,
      onBrowserNavigate,
      onBrowserInteract,
      onBrowserPopout,
      onBrowserDock,
      popoutBrowser,
      relaunchBrowser
    }
  }
}
</script>

<style scoped>
.research-browser {
  @apply bg-white border rounded-lg overflow-hidden relative;
}

.browser-content {
  height: 60vh;
  min-height: 400px;
  max-height: 80vh;
  position: relative;
  display: flex;
  flex-direction: column;
}

.status-badge {
  @apply px-2 py-1 text-xs font-medium rounded;
}

.result-card {
  @apply hover:shadow-md transition-shadow duration-150;
}

.btn {
  @apply px-3 py-1 text-sm font-medium rounded border transition-all duration-150;
}

.btn:disabled {
  @apply opacity-50 cursor-not-allowed;
}

.btn-primary {
  @apply bg-blue-600 text-white border-blue-600 hover:bg-blue-700;
}

.btn-secondary {
  @apply bg-gray-600 text-white border-gray-600 hover:bg-gray-700;
}

.btn-outline {
  @apply bg-white text-gray-700 border-gray-300 hover:bg-gray-50;
}

.btn-warning {
  @apply bg-yellow-600 text-white border-yellow-600 hover:bg-yellow-700;
}

.btn-danger {
  @apply bg-red-600 text-white border-red-600 hover:bg-red-700;
}

.btn-success {
  @apply bg-green-600 text-white border-green-600 hover:bg-green-700;
}

.btn-sm {
  @apply px-2 py-1 text-xs;
}

.btn-xs {
  @apply px-1 py-0.5 text-xs;
}

/* Loading indicator bar */
.loading-indicator {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 9999;
  height: 3px;
  background-color: transparent;
}

.loading-bar {
  height: 100%;
  background: linear-gradient(90deg, #3b82f6, #60a5fa, #3b82f6);
  background-size: 200% 100%;
  animation: loading 1.5s ease-in-out infinite;
}

@keyframes loading {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}
</style>
