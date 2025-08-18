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
          <button @click="refreshStatus" class="btn btn-secondary btn-sm" :disabled="loading">
            <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i>
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
          <button @click="handleWaitForUser" class="btn btn-primary btn-sm" :disabled="loading">
            <i class="fas fa-clock mr-1"></i>
            Wait
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
        <button @click="handleSessionAction('extract_content')" 
                class="btn btn-outline btn-sm" :disabled="loading">
          <i class="fas fa-file-alt mr-1"></i>
          Extract Content
        </button>
        
        <button @click="handleSessionAction('save_mhtml')" 
                class="btn btn-outline btn-sm" :disabled="loading">
          <i class="fas fa-save mr-1"></i>
          Save MHTML
        </button>
        
        <button @click="navigateToUrl" 
                class="btn btn-outline btn-sm" :disabled="loading">
          <i class="fas fa-arrow-right mr-1"></i>
          Navigate
        </button>
        
        <button @click="closeSession" 
                class="btn btn-danger btn-sm" :disabled="loading">
          <i class="fas fa-times mr-1"></i>
          Close Session
        </button>
      </div>
      
      <!-- URL Input for Navigation -->
      <div v-if="showNavigationInput" class="mt-3">
        <div class="flex space-x-2">
          <input v-model="navigationUrl" 
                 type="url" 
                 placeholder="Enter URL to navigate to..." 
                 class="flex-1 px-3 py-2 border border-gray-300 rounded text-sm"
                 @keyup.enter="performNavigation">
          <button @click="performNavigation" 
                  class="btn btn-primary btn-sm" :disabled="!navigationUrl || loading">
            Go
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
          <div class="flex items-center space-x-1">
            <input 
              v-model="browserUrl" 
              type="url" 
              placeholder="Enter URL to navigate..."
              class="px-2 py-1 border border-gray-300 rounded text-sm w-48"
              :disabled="sessionId && !agentPaused"
              @keyup.enter="navigateToBrowserUrl"
            >
            <button 
              @click="navigateToBrowserUrl" 
              :disabled="!browserUrl || browserLoading || (sessionId && !agentPaused)"
              class="btn btn-primary btn-xs"
            >
              <i class="fas fa-arrow-right"></i>
            </button>
          </div>
          
          <!-- Agent Control Buttons -->
          <div v-if="sessionId" class="flex items-center space-x-1 border-l border-gray-300 pl-2">
            <button 
              v-if="!agentPaused" 
              @click="pauseAgent" 
              class="btn btn-warning btn-xs"
              title="Pause agent and take control of browser"
            >
              <i class="fas fa-pause mr-1"></i>
              Take Control
            </button>
            <button 
              v-if="agentPaused" 
              @click="resumeAgent" 
              class="btn btn-success btn-xs"
              title="Resume agent research session"
            >
              <i class="fas fa-play mr-1"></i>
              Resume Agent
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
  </div>
</template>

<script>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import apiClient from '@/utils/ApiClient'
import PopoutChromiumBrowser from './PopoutChromiumBrowser.vue'

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
    const loading = ref(false)
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
    const browserLoading = ref(false)
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
    
    const refreshStatus = async () => {
      if (!props.sessionId) return
      
      loading.value = true
      try {
        const response = await apiClient.get(`/api/research/session/${props.sessionId}/status`)
        
        status.value = response.data.status
        currentUrl.value = response.data.current_url
        currentBrowserUrl.value = response.data.current_url
        interactionRequired.value = response.data.interaction_required
        interactionMessage.value = response.data.interaction_message
        
        // Get browser info
        const browserResponse = await apiClient.get(`/api/research/browser/${props.sessionId}`)
        browserInfo.value = browserResponse.data
        
      } catch (error) {
        console.error('Failed to refresh status:', error)
      } finally {
        loading.value = false
      }
    }
    
    const handleWaitForUser = async () => {
      loading.value = true
      try {
        const response = await apiClient.post('/api/research/session/action', {
          session_id: props.sessionId,
          action: 'wait',
          timeout_seconds: 300
        })
        
        actionResult.value = response.data
        await refreshStatus()
        
      } catch (error) {
        console.error('Wait for user failed:', error)
        actionResult.value = { error: error.message }
      } finally {
        loading.value = false
      }
    }
    
    const handleSessionAction = async (action) => {
      loading.value = true
      try {
        const response = await apiClient.post('/api/research/session/action', {
          session_id: props.sessionId,
          action: action
        })
        
        actionResult.value = response.data
        await refreshStatus()
        
      } catch (error) {
        console.error(`Session action ${action} failed:`, error)
        actionResult.value = { error: error.message }
      } finally {
        loading.value = false
      }
    }
    
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
    
    const performNavigation = async () => {
      if (!navigationUrl.value) return
      
      loading.value = true
      try {
        const response = await apiClient.post(`/api/research/session/${props.sessionId}/navigate`, {
          url: navigationUrl.value
        })
        
        actionResult.value = response.data
        showNavigationInput.value = false
        navigationUrl.value = ''
        await refreshStatus()
        
      } catch (error) {
        console.error('Navigation failed:', error)
        actionResult.value = { error: error.message }
      } finally {
        loading.value = false
      }
    }
    
    const closeSession = async () => {
      if (!confirm('Are you sure you want to close this research session?')) return
      
      loading.value = true
      try {
        await apiClient.delete(`/api/research/session/${props.sessionId}`)
        
        // Emit event to parent component
        // In a full implementation, you'd use emit or store
        window.location.reload() // Simple approach for now
        
      } catch (error) {
        console.error('Close session failed:', error)
      } finally {
        loading.value = false
      }
    }
    
    const copyUrl = async () => {
      if (currentUrl.value) {
        await navigator.clipboard.writeText(currentUrl.value)
        // Could show a toast notification here
      }
    }
    
    const toggleBrowserView = () => {
      showBrowser.value = !showBrowser.value
    }
    
    const onBrowserLoad = () => {
      console.log('Browser iframe loaded')
    }
    
    // PopoutChromiumBrowser event handlers
    const onBrowserClose = () => {
      showBrowser.value = false
      console.log('Browser closed')
    }
    
    const onBrowserNavigate = (data) => {
      currentBrowserUrl.value = data.url
      currentUrl.value = data.url
      console.log('Browser navigated to:', data.url)
    }
    
    const onBrowserInteract = (data) => {
      console.log('Browser interaction:', data.action)
    }
    
    const onBrowserPopout = () => {
      console.log('Browser popped out')
    }
    
    const onBrowserDock = () => {
      console.log('Browser docked')
    }
    
    const popoutBrowser = () => {
      // This will be handled by the PopoutChromiumBrowser component
      showBrowser.value = true
    }
    
    const navigateToBrowserUrl = async () => {
      if (!browserUrl.value) return
      
      browserLoading.value = true
      try {
        // Always show the browser when navigating
        showBrowser.value = true
        
        // If there's no research session, create one for this navigation
        if (!props.sessionId) {
          const response = await apiClient.post('/api/research/url', {
            conversation_id: 'unified-browser-session',
            url: browserUrl.value,
            extract_content: false // Just navigate, don't extract content
          })
          
          console.log('Unified browser navigation response:', response.data)
          
          if (response.data && response.data.success && response.data.session_id) {
            // We now have a research session for this navigation
            currentBrowserUrl.value = browserUrl.value
            console.log('Created research session for unified browser:', response.data.session_id)
          }
        }
        
        // Update the browser URL regardless of session creation
        currentBrowserUrl.value = browserUrl.value
        
        // Clear the input
        browserUrl.value = ''
        
      } catch (error) {
        console.error('Failed to navigate browser:', error)
        // Even on error, try to navigate the browser directly
        currentBrowserUrl.value = browserUrl.value
        showBrowser.value = true
      } finally {
        browserLoading.value = false
      }
    }
    
    const relaunchBrowser = () => {
      // Simply show the browser again with existing URL
      showBrowser.value = true
      console.log('Browser relaunched for session:', props.sessionId)
    }
    
    const pauseAgent = async () => {
      if (!props.sessionId) return
      
      try {
        // Signal the agent to pause by sending a manual_intervention action
        const response = await apiClient.post('/api/research/session/action', {
          session_id: props.sessionId,
          action: 'manual_intervention'
        })
        
        if (response.data && response.data.success) {
          agentPaused.value = true
          console.log('Agent research session paused - user has control')
          
          // Add a message to inform the user
          actionResult.value = {
            message: 'Agent paused - you now have control of the browser',
            timestamp: new Date().toISOString()
          }
        }
      } catch (error) {
        console.error('Failed to pause agent:', error)
      }
    }
    
    const resumeAgent = async () => {
      if (!props.sessionId) return
      
      try {
        // Resume agent by clearing the manual intervention
        const response = await apiClient.post('/api/research/session/action', {
          session_id: props.sessionId,
          action: 'wait', // This will resume normal agent operation
          timeout_seconds: 300
        })
        
        if (response.data) {
          agentPaused.value = false
          console.log('Agent research session resumed')
          
          // Add a message to inform the user
          actionResult.value = {
            message: 'Agent resumed - research session is now active',
            timestamp: new Date().toISOString()
          }
          
          // Refresh session status
          await refreshStatus()
        }
      } catch (error) {
        console.error('Failed to resume agent:', error)
      }
    }
    
    // Auto-refresh status periodically
    let statusInterval
    
    onMounted(() => {
      if (props.sessionId) {
        refreshStatus()
        statusInterval = setInterval(refreshStatus, 10000) // Refresh every 10 seconds
        showBrowser.value = true // Always show browser by default for observability
      } else if (props.researchData && props.researchData.results && props.researchData.results.length > 0) {
        // Show browser when we have research results with URLs
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
        console.log('Research data updated, showing browser with URL:', initialBrowserUrl.value)
      }
    }, { deep: true })
    
    return {
      loading,
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
      browserLoading,
      agentPaused,
      activeSessionId,
      currentUrlForDisplay,
      researchResults,
      statusClass,
      getResultStatusClass,
      refreshStatus,
      handleWaitForUser,
      handleSessionAction,
      openBrowserSession,
      openBrowserForResult,
      navigateToUrl,
      performNavigation,
      closeSession,
      copyUrl,
      toggleBrowserView,
      onBrowserLoad,
      onBrowserClose,
      onBrowserNavigate,
      onBrowserInteract,
      onBrowserPopout,
      onBrowserDock,
      popoutBrowser,
      navigateToBrowserUrl,
      relaunchBrowser,
      pauseAgent,
      resumeAgent
    }
  }
}
</script>

<style scoped>
.research-browser {
  @apply bg-white border rounded-lg overflow-hidden;
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
  @apply px-3 py-1 text-sm font-medium rounded border transition-colors duration-150;
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

.btn-warning {
  @apply bg-orange-600 text-white border-orange-600 hover:bg-orange-700;
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

.btn:disabled {
  @apply opacity-50 cursor-not-allowed;
}
</style>