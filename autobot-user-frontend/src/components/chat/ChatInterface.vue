<template>
  <ErrorBoundary fallback="Chat interface failed to load. Please refresh the page.">
    <div class="chat-interface flex h-full bg-white overflow-hidden">

      <!-- Chat Sidebar with Unified Loading -->
      <UnifiedLoadingView
        loading-key="chat-sidebar"
        :has-content="store.sessions.length > 0"
        :auto-timeout-ms="10000"
        @loading-complete="handleSidebarLoadingComplete"
        @loading-error="handleSidebarLoadingError"
        @loading-timeout="handleSidebarLoadingTimeout"
        class="sidebar-loading-view h-full w-80 flex-shrink-0"
      >
        <ChatSidebar />
      </UnifiedLoadingView>

      <!-- Main Chat Area -->
      <div class="flex-1 flex flex-col min-w-0 relative">

        <!-- Chat Header (Sticky at top) -->
        <ChatHeader
          :current-session-id="store.currentSessionId"
          :current-session-title="currentSessionTitle"
          :session-info="sessionInfo"
          :connection-status="connectionStatus"
          :is-connected="isConnected"
          @export-session="exportSession"
          @clear-session="clearSession"
          class="flex-shrink-0"
        >
          <!-- File Panel Toggle Button (injected into header) -->
          <template #actions>
            <button
              v-if="store.currentSessionId"
              @click="toggleFilePanel"
              class="header-btn"
              :class="{ 'bg-indigo-100 text-indigo-600': showFilePanel }"
              title="Toggle file panel"
            >
              <i class="fas fa-paperclip"></i>
            </button>
          </template>
        </ChatHeader>

        <!-- Chat/Tools Tabs (FIXED: outside scrollable container so sticky works) -->
        <ChatTabs
          :active-tab="activeTab"
          @tab-change="handleTabChange"
          class="flex-shrink-0"
        />

        <!-- Scrollable Content Area (Header scrolls away, input stays) -->
        <UnifiedLoadingView
          loading-key="chat-content"
          :has-content="store.currentMessages.length > 0"
          :auto-timeout-ms="15000"
          @loading-complete="handleContentLoadingComplete"
          @loading-error="handleContentLoadingError"
          @loading-timeout="handleContentLoadingTimeout"
          class="flex-1 min-h-0 flex flex-col overflow-y-auto"
        >
          <ChatTabContent
            :active-tab="activeTab"
            :current-session-id="store.currentSessionId"
            :novnc-url="novncUrl"
            @tool-call-detected="handleToolCallDetected"
          />
        </UnifiedLoadingView>
      </div>

      <!-- File Panel (Right Sidebar) -->
      <Transition name="slide-left">
        <ChatFilePanel
          v-if="showFilePanel && store.currentSessionId"
          :session-id="store.currentSessionId"
          @close="showFilePanel = false"
        />
      </Transition>

      <!-- REMOVED: Terminal Sidebar (line 57-61) - causes duplicate terminals -->
      <!-- The Terminal component is now ONLY shown in ChatTabContent when activeTab === 'terminal' -->

      <!-- Dialogs and Modals -->
      <KnowledgePersistenceDialog
        v-if="showKnowledgeDialog"
        :visible="showKnowledgeDialog"
        :chat-id="store.currentSessionId"
        :chat-context="currentChatContext"
        @close="showKnowledgeDialog = false"
        @decisions-applied="onKnowledgeDecisionsApplied"
        @chat-compiled="onChatCompiled"
      />

      <CommandPermissionDialog
        v-if="showCommandDialog"
        :show="showCommandDialog"
        :command="pendingCommand.command"
        :purpose="pendingCommand.purpose"
        :risk-level="pendingCommand.riskLevel"
        :chat-id="store.currentSessionId"
        :original-message="pendingCommand.originalMessage"
        :terminal-session-id="pendingCommand.terminalSessionId"
        @approved="onCommandApproved"
        @denied="onCommandDenied"
        @commented="onCommandCommented"
        @close="showCommandDialog = false"
      />

      <!-- Workflow Progress Widget -->
      <div v-if="showWorkflowProgress" class="workflow-progress-widget">
        <WorkflowProgressWidget
          :workflow-id="currentWorkflowId"
          @close="showWorkflowProgress = false"
        />
      </div>
    </div>
  </ErrorBoundary>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, provide } from 'vue'
import { useChatStore } from '@/stores/useChatStore'
import { useChatController } from '@/models/controllers'
import { useAppStore } from '@/stores/useAppStore'
import { useToast } from '@/composables/useToast'
import { useOverseerAgent } from '@/composables/useOverseerAgent'
import ApiClient from '@/utils/ApiClient.js'
import batchApiService from '@/services/BatchApiService'
// MIGRATED: Using AppConfig.js for better configuration management
import appConfig from '@/config/AppConfig.js'
// FIXED: Import NetworkConstants for IP fallback values
import { NetworkConstants } from '@/constants/network'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ChatInterface')

// Components
import ErrorBoundary from '@/components/common/ErrorBoundary.vue'
import UnifiedLoadingView from '@/components/ui/UnifiedLoadingView.vue'
import ChatSidebar from './ChatSidebar.vue'
import ChatHeader from './ChatHeader.vue'
import ChatTabs from './ChatTabs.vue'
import ChatTabContent from './ChatTabContent.vue'
import ChatFilePanel from './ChatFilePanel.vue'
import KnowledgePersistenceDialog from '@/components/knowledge/KnowledgePersistenceDialog.vue'
import CommandPermissionDialog from '@/components/ui/CommandPermissionDialog.vue'
import WorkflowProgressWidget from '@/components/workflow/WorkflowProgressWidget.vue'

// Stores and controller
const store = useChatStore()
const controller = useChatController()
const appStore = useAppStore()

// Toast notifications
const { showToast } = useToast()
const notify = (message: string, type: 'info' | 'success' | 'warning' | 'error' = 'info') => {
  showToast(message, type, type === 'error' ? 5000 : 3000)
}

// Dialog states
const showKnowledgeDialog = ref(false)
const showCommandDialog = ref(false)
const showWorkflowProgress = ref(false)
const showFilePanel = ref(false)

// Dialog data
const currentChatContext = ref<any>(null)
const pendingCommand = ref({
  command: '',
  purpose: '',
  riskLevel: 'MEDIUM' as 'LOW' | 'MEDIUM' | 'HIGH',
  originalMessage: '',
  terminalSessionId: null as string | null
})
const currentWorkflowId = ref<string | null>(null)

// Tab state
const activeTab = ref<string>('chat')

// Issue #690: Overseer Agent State
const overseerEnabled = ref(false)

// Provide overseer state to child components (ChatInput)
provide('overseerEnabled', overseerEnabled)
provide('toggleOverseer', () => {
  overseerEnabled.value = !overseerEnabled.value
  logger.debug('Overseer mode toggled:', overseerEnabled.value)
})

// Issue #690: Overseer Agent Integration
// Initialize only when enabled AND we have a session
const overseerAgent = computed(() => {
  if (!overseerEnabled.value || !store.currentSessionId) {
    return null
  }
  return useOverseerAgent({
    sessionId: store.currentSessionId,
    autoConnect: true,
    onPlanCreated: (plan) => {
      logger.info('[Overseer] Plan created:', plan.plan_id)
      notify('Execution plan created', 'info')
    },
    onStepUpdate: (step) => {
      logger.debug('[Overseer] Step update:', { step_number: step.step_number, status: step.status })
    },
    onStreamChunk: (chunk) => {
      logger.debug('[Overseer] Stream chunk:', chunk.chunk_type)
    },
    onError: (error) => {
      logger.error('[Overseer] Error:', error)
      notify(`Overseer error: ${error}`, 'error')
    },
    onComplete: () => {
      logger.info('[Overseer] Execution complete')
      notify('Execution completed', 'success')
    }
  })
})

// Provide overseer agent to child components
provide('overseerAgent', overseerAgent)

// Issue #690: Handle overseer query submission
const submitOverseerQuery = async (query: string) => {
  if (!overseerAgent.value) {
    logger.warn('Overseer agent not available')
    return false
  }

  if (!overseerAgent.value.isConnected.value) {
    overseerAgent.value.connect()
    // Wait for connection
    await new Promise(resolve => setTimeout(resolve, 500))
  }

  overseerAgent.value.submitQuery(query)
  return true
}

// Provide submit function to child components
provide('submitOverseerQuery', submitOverseerQuery)

// Connection state with stabilized status management
const baseConnectionStatus = ref('Connected')
const isConnected = ref(true)
const lastHeartbeat = ref(Date.now())
const connectionStatus = computed(() => {
  // If typing, show typing status temporarily
  if (store.isTyping) {
    return 'AI is typing...'
  }
  // Otherwise show base connection status
  return baseConnectionStatus.value
})

// FIXED: Tool URLs - Replace async computed with ref and async loader
// Issue #715: VNC URL is now dynamically set based on user-selected infrastructure hosts
// The legacy novncUrl is kept for backwards compatibility but actual VNC connections
// are handled by HostSelector in ChatTabContent.vue
const novncUrl = ref('')

// Legacy function - kept for backwards compatibility
// Issue #715: VNC startup check removed - users now select their own VNC hosts
// from infrastructure hosts configured in secrets management
const loadNovncUrl = async () => {
  // Legacy fallback URL for tools/desktop VNC (not chat VNC)
  // Chat VNC now uses dynamic host selection via HostSelector component
  const baseUrl = '/tools/novnc/vnc.html'

  if (!store.currentSessionId) {
    novncUrl.value = baseUrl + '?autoconnect=true&resize=scale'
    return
  }

  // Get session without side effects to prevent reactive loops
  const session = store.sessions.find(s => s.id === store.currentSessionId)

  if (!session?.desktopSession) {
    // Return base URL without creating session to prevent reactive side effects
    novncUrl.value = baseUrl + '?autoconnect=true&resize=scale'
    return
  }

  // Use existing desktop session data
  const params = new URLSearchParams({
    autoconnect: 'true',
    resize: 'scale',
    session: session.desktopSession.id || store.currentSessionId
  })

  novncUrl.value = `${baseUrl}?${params.toString()}`
}

// Computed
const currentSessionTitle = computed(() => {
  const session = store.currentSession
  if (!session) return 'New Chat'

  return session.title || `Chat ${session.id.slice(-8)}...`
})

const sessionInfo = computed(() => {
  const session = store.currentSession
  if (!session) return 'Start a conversation'

  const messageCount = session.messages.length
  const lastMessage = session.messages[session.messages.length - 1]
  const lastMessageTime = lastMessage ? new Date(lastMessage.timestamp).toLocaleTimeString() : null
  const sessionId = session.id  // Display full UUID

  if (messageCount === 0) {
    return `Session: ${sessionId} • No messages yet`
  }

  return `Session: ${sessionId} • ${messageCount} message${messageCount > 1 ? 's' : ''} • Last: ${lastMessageTime}`
})


// Methods
const toggleFilePanel = () => {
  showFilePanel.value = !showFilePanel.value
}

const exportSession = async () => {
  if (!store.currentSessionId) return

  try {
    const session = controller.exportChatSession(store.currentSessionId)
    if (!session) return

    const data = {
      id: session.id,
      title: session.title,
      messages: session.messages,
      createdAt: session.createdAt,
      updatedAt: session.updatedAt,
      exportedAt: new Date().toISOString()
    }

    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `chat-${session.title || session.id.slice(-8)}-${new Date().toISOString().split('T')[0]}.json`
    a.click()
    URL.revokeObjectURL(url)

  } catch (error) {
    logger.error('Failed to export session:', error)
    appStore.setGlobalError('Failed to export chat session')
  }
}

const clearSession = async () => {
  if (!store.currentSessionId) return

  if (confirm('Clear all messages in this chat? This action cannot be undone.')) {
    try {
      await controller.resetCurrentChat()
    } catch (error) {
      logger.error('Failed to clear session:', error)
      appStore.setGlobalError('Failed to clear chat session')
    }
  }
}

// Unified loading event handlers
const handleSidebarLoadingComplete = () => {
  logger.debug('Sidebar loading completed')
}

const handleSidebarLoadingError = (error: any) => {
  logger.error('Sidebar loading error:', error)
  appStore.setGlobalError('Failed to load chat sessions')
}

const handleSidebarLoadingTimeout = () => {
  logger.warn('Sidebar loading timed out')
}

const handleContentLoadingComplete = () => {
  logger.debug('Content loading completed')
}

const handleContentLoadingError = (error: any) => {
  logger.error('Content loading error:', error)
  appStore.setGlobalError('Failed to load chat content')
}

const handleContentLoadingTimeout = () => {
  logger.warn('Content loading timed out')
}

// Tab change handler - ensures local tab state change without router navigation
const handleTabChange = (tabKey: string) => {
  logger.debug('Tab change requested:', tabKey)

  // Prevent any router navigation and only update local state
  // This fixes the Terminal tab issue where it was triggering unwanted navigation
  activeTab.value = tabKey

  // Log successful tab change
  logger.debug('Active tab changed to:', activeTab.value)
}

// Terminal tab handler for explicit new tab opening (not used for tab clicks)
const openTerminalInNewTab = () => {
  // Open terminal in a new browser tab by navigating to tools/terminal
  window.open('/tools/terminal', '_blank')
}

// Dialog handlers
const onKnowledgeDecisionsApplied = (decisions: any) => {
  logger.debug('Knowledge decisions applied:', decisions)
  // Handle knowledge persistence decisions
}

const onChatCompiled = (compiledData: any) => {
  logger.debug('Chat compiled:', compiledData)
  // Handle compiled chat data
}

// Handle TOOL_CALL detection from chat messages
const handleToolCallDetected = async (toolCall: any) => {
  logger.debug('TOOL_CALL detected, showing approval dialog:', toolCall)

  // Assess risk level (simple heuristics for now)
  let riskLevel: 'LOW' | 'MEDIUM' | 'HIGH' = 'MEDIUM'
  const cmd = toolCall.command.toLowerCase()

  if (cmd.includes('rm -rf') || cmd.includes('sudo') || cmd.includes('dd') || cmd.includes('mkfs')) {
    riskLevel = 'HIGH'
  } else if (cmd.includes('apt') || cmd.includes('systemctl') || cmd.includes('reboot')) {
    riskLevel = 'MEDIUM'
  } else {
    riskLevel = 'LOW'
  }

  // Set pending command data
  pendingCommand.value = {
    command: toolCall.command,
    purpose: toolCall.purpose,
    riskLevel: riskLevel,
    originalMessage: JSON.stringify(toolCall),
    terminalSessionId: toolCall.terminal_session_id || null
  }

  // Show approval dialog
  showCommandDialog.value = true
}

const onCommandApproved = async (commandData: any) => {
  logger.debug('Command approved:', commandData)

  // IMPORTANT: The backend is already waiting for approval and will execute automatically.
  // CommandPermissionDialog has already sent the approval POST request.
  // We just need to close the dialog and switch to terminal tab.
  // The backend polling loop will detect the approval and execute the command.

  // Switch to terminal tab to show execution
  activeTab.value = 'terminal'

  // Close dialog
  showCommandDialog.value = false

  logger.debug('Dialog closed, backend will execute the approved command')
}

const onCommandDenied = (reason: string) => {
  logger.debug('Command denied:', reason)
  showCommandDialog.value = false
  // Handle command denial
}

const onCommandCommented = async (commentData: any) => {
  logger.debug('Command commented:', commentData)

  try {
    // CRITICAL: Send denial with comment/feedback to agent terminal
    // This allows the agent to receive the user's alternative approach suggestion
    if (pendingCommand.value.terminalSessionId) {
      const approvalUrl = await appConfig.getApiUrl(
        `/api/agent-terminal/sessions/${pendingCommand.value.terminalSessionId}/approve`
      )

      const response = await fetch(approvalUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          approved: false,  // Deny the command
          user_id: 'web_user',
          comment: commentData.comment || commentData  // User's alternative suggestion
        })
      })

      if (!response.ok) {
        throw new Error(`Server returned ${response.status}`)
      }

      const result = await response.json()

      logger.debug('Command denied with user feedback/alternative approach')
      notify('Feedback sent to agent', 'success')
    }

    // Close the dialog
    showCommandDialog.value = false

    // The comment was already sent to chat via CommandPermissionDialog
    // The agent will receive the denial + feedback and can propose an alternative
  } catch (error) {
    logger.error('Error sending command comment/denial:', error)
    notify('Failed to send feedback to agent', 'error')
  }
}

// Connection monitoring - MIGRATED to use AppConfig
const checkConnection = async () => {
  try {
    // MIGRATED: Use AppConfig for connection validation
    const isConnectionValid = await appConfig.validateConnection()

    if (isConnectionValid) {
      isConnected.value = true
      baseConnectionStatus.value = 'Connected'
      lastHeartbeat.value = Date.now()
    } else {
      isConnected.value = false
      baseConnectionStatus.value = 'Disconnected'
    }
  } catch (error) {
    isConnected.value = false
    baseConnectionStatus.value = 'Disconnected'
  }
}

// Interval refs for proper cleanup
const heartbeatInterval = ref<number | null>(null)
const autoSaveInterval = ref<number | null>(null)
const messagePollingInterval = ref<number | null>(null)

const startHeartbeat = () => {
  // Clear any existing interval first
  if (heartbeatInterval.value) {
    clearInterval(heartbeatInterval.value)
  }
  // Check connection every 60 seconds (reduced from 30 to minimize UI updates)
  heartbeatInterval.value = setInterval(checkConnection, 60000) as unknown as number
}

// Auto-save functionality
const enableAutoSave = () => {
  // Clear any existing interval first
  if (autoSaveInterval.value) {
    clearInterval(autoSaveInterval.value)
  }
  // Auto-save current session every 2 minutes
  autoSaveInterval.value = setInterval(() => {
    if (store.settings.autoSave && store.currentSessionId) {
      controller.saveChatSession()
        .catch((error: any) => logger.warn('Auto-save failed:', error))
    }
  }, 2 * 60 * 1000) as unknown as number
}

// Message polling functionality - fetches new messages periodically
// OPTIMIZED: Slower polling to reduce UI flicker and server load
const startMessagePolling = () => {
  // Clear any existing interval first
  if (messagePollingInterval.value) {
    clearInterval(messagePollingInterval.value)
  }

  logger.debug('Starting message polling (10s interval - optimized)')

  // Poll for new messages every 10 seconds (reduced from 3s to prevent flicker)
  // This still picks up LLM interpretations and new messages, just less aggressively
  messagePollingInterval.value = setInterval(async () => {
    // CRITICAL FIX: Skip polling while AI is typing to prevent message flickering
    // The streaming/real-time updates handle messages during active conversation
    if (store.isTyping) {
      logger.debug('Skipping message poll - AI is typing')
      return
    }

    if (store.currentSessionId) {
      try {
        // Silently reload messages for current session
        // This will pick up any new interpretations or messages saved by backend
        await controller.loadChatMessages(store.currentSessionId)
      } catch (error) {
        // Fail silently - don't spam console with polling errors
        // Only log if it's not a simple 404 (session not found)
        if (error && typeof error === 'object' && 'status' in error && error.status !== 404) {
          logger.warn('[ChatInterface] Message polling failed:', error)
        }
      }
    }
  }, 10000) as unknown as number  // Poll every 10 seconds (optimized from 3s)
}

// Keyboard shortcuts
const handleKeyboardShortcuts = (event: KeyboardEvent) => {
  if (event.ctrlKey || event.metaKey) {
    switch (event.key) {
      case 'n':
        event.preventDefault()
        controller.createNewSession()
        break
      case 'k':
        event.preventDefault()
        showKnowledgeDialog.value = true
        break
      case 'e':
        if (store.currentSessionId) {
          event.preventDefault()
          exportSession()
        }
        break
      case 'f':
        if (store.currentSessionId) {
          event.preventDefault()
          toggleFilePanel()
        }
        break
    }
  }
}

// STREAMLINED: Simplified initialization without complex timeout racing
// Issue #671: Added initialization state tracking for loading feedback
const initializeChatInterface = async () => {
  // Issue #671: Set initializing state to show loading indicator
  store.setInitializing(true)

  try {
    logger.debug('🚀 Starting streamlined chat interface initialization')

    // Issue #671: Reduced timeout from 8s to 5s for faster failure feedback
    const loadPromise = batchApiService.initializeChatInterface()
    const timeoutPromise = new Promise<never>((_, reject) => {
      setTimeout(() => reject(new Error('Initialization timeout')), 5000)
    })

    try {
      // Race initialization with timeout
      const data = await Promise.race([loadPromise, timeoutPromise])

      // Process results - sync with backend (source of truth)
      if (data.chat_sessions && !data.chat_sessions.error && Array.isArray(data.chat_sessions)) {
        // Use syncSessionsWithBackend to remove deleted sessions and add new ones
        store.syncSessionsWithBackend(data.chat_sessions)
      }

      // Update connection status
      if (data.system_health && !data.system_health.error) {
        isConnected.value = data.system_health.status === 'healthy'
        baseConnectionStatus.value = isConnected.value ? 'Connected' : 'Disconnected'
      }

      // Issue #671: Clear initialization state on success
      store.setInitializing(false)
    } catch (error) {
      logger.warn('⏱️ Initialization failed or timed out, using fallback:', error)

      // Fallback to individual loading
      if (store.sessions.length === 0) {
        await controller.loadChatSessions().catch((err) => logger.warn('Failed to load chat sessions:', err))
      }

      // Issue #671: Clear initialization state after fallback attempt
      store.setInitializing(false)
    }

    logger.debug('✅ Chat interface initialization completed')

  } catch (error) {
    logger.error('❌ Chat initialization failed:', error)

    // Issue #671: Set error state and show toast notification
    const errorMessage = error instanceof Error ? error.message : 'Failed to initialize chat interface'
    store.setInitializationError(errorMessage)
    notify('Chat initialization failed. Some features may not work correctly.', 'error')

    appStore.setGlobalError('Failed to initialize chat interface')
  }
}

// Lifecycle
onMounted(async () => {
  // Initialize chat interface with streamlined loading
  await initializeChatInterface()

  // Load NoVNC URL after initialization
  await loadNovncUrl()

  // Enable auto-save if not disabled
  if (store.settings.autoSave) {
    controller.enableAutoSave()
  }

  // Start connection monitoring
  checkConnection()
  startHeartbeat()
  enableAutoSave()

  // Start message polling to fetch new messages
  startMessagePolling()

  // Add keyboard shortcuts
  document.addEventListener('keydown', handleKeyboardShortcuts)
})

onUnmounted(() => {
  // Clean up event listeners
  document.removeEventListener('keydown', handleKeyboardShortcuts)

  // Clean up intervals
  if (heartbeatInterval.value) {
    clearInterval(heartbeatInterval.value)
    heartbeatInterval.value = null
  }

  if (autoSaveInterval.value) {
    clearInterval(autoSaveInterval.value)
    autoSaveInterval.value = null
  }

  if (messagePollingInterval.value) {
    logger.debug('[ChatInterface] Stopping message polling')
    clearInterval(messagePollingInterval.value)
    messagePollingInterval.value = null
  }
})

// Watch for session changes to update NoVNC URL
watch(() => store.currentSessionId, (newSessionId, oldSessionId) => {
  if (newSessionId !== oldSessionId) {
    // Session changed, reload NoVNC URL
    logger.debug('[ChatInterface] Session changed:', newSessionId)
    loadNovncUrl()

    // Close file panel when switching sessions
    showFilePanel.value = false
  }
})
</script>

<style scoped>
/* IMPROVED: Better overflow handling for chat interface */
.chat-interface {
  /* Removed height: 100vh - now relies on parent container */
}

/* CRITICAL FIX: Enhanced sidebar dimensions constraint */
.sidebar-loading-view {
  /* Force sidebar width and height - prevent UnifiedLoadingView override */
  width: 320px !important; /* Force w-80 equivalent (320px) */
  height: 100% !important; /* Force full height */
  flex-shrink: 0 !important;
  max-width: 320px !important;
  min-width: 320px !important;
}

.workflow-progress-widget {
  @apply fixed bottom-4 right-4 z-50;
}

/* Focus trap for dialogs */
.dialog-overlay {
  @apply fixed inset-0 z-50;
}

/* File Panel Transitions */
.slide-left-enter-active,
.slide-left-leave-active {
  transition: transform 0.3s ease-out, opacity 0.3s ease-out;
}

.slide-left-enter-from {
  transform: translateX(100%);
  opacity: 0;
}

.slide-left-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

/* Animations */
@keyframes slideInFromRight {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}

.workflow-progress-widget {
  animation: slideInFromRight 0.3s ease-out;
}

/* Header button styling for file panel toggle */
.header-btn {
  @apply w-8 h-8 flex items-center justify-center rounded-md transition-colors text-gray-600 hover:bg-gray-100;
}
</style>
