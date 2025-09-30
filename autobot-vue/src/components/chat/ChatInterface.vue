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
      <div class="flex-1 flex flex-col min-w-0 overflow-hidden">

        <!-- Chat Header -->
        <ChatHeader
          :current-session-id="store.currentSessionId"
          :current-session-title="currentSessionTitle"
          :session-info="sessionInfo"
          :connection-status="connectionStatus"
          :is-connected="isConnected"
          @export-session="exportSession"
          @clear-session="clearSession"
        />

        <!-- Chat/Tools Tabs -->
        <ChatTabs
          :active-tab="activeTab"
          @tab-change="handleTabChange"
        />

        <!-- Chat Content with Unified Loading - FIXED: Removed overflow-hidden to allow sticky positioning -->
        <UnifiedLoadingView
          loading-key="chat-content"
          :has-content="store.currentMessages.length > 0"
          :auto-timeout-ms="15000"
          @loading-complete="handleContentLoadingComplete"
          @loading-error="handleContentLoadingError"
          @loading-timeout="handleContentLoadingTimeout"
          class="flex-1 min-h-0 flex flex-col"
        >
          <ChatTabContent
            :active-tab="activeTab"
            :current-session-id="store.currentSessionId"
            :novnc-url="novncUrl"
          />
        </UnifiedLoadingView>
      </div>

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
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useChatStore } from '@/stores/useChatStore'
import { useChatController } from '@/models/controllers'
import { useAppStore } from '@/stores/useAppStore'
import ApiClient from '@/utils/ApiClient.js'
import batchApiService from '@/services/BatchApiService'
// MIGRATED: Using AppConfig.js for better configuration management
import appConfig from '@/config/AppConfig.js'

// Components
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import UnifiedLoadingView from '@/components/ui/UnifiedLoadingView.vue'
import ChatSidebar from './ChatSidebar.vue'
import ChatHeader from './ChatHeader.vue'
import ChatTabs from './ChatTabs.vue'
import ChatTabContent from './ChatTabContent.vue'
import KnowledgePersistenceDialog from '@/components/KnowledgePersistenceDialog.vue'
import CommandPermissionDialog from '@/components/CommandPermissionDialog.vue'
import WorkflowProgressWidget from '@/components/WorkflowProgressWidget.vue'

// Stores and controller
const store = useChatStore()
const controller = useChatController()
const appStore = useAppStore()

// Dialog states
const showKnowledgeDialog = ref(false)
const showCommandDialog = ref(false)
const showWorkflowProgress = ref(false)

// Dialog data
const currentChatContext = ref<any>(null)
const pendingCommand = ref({
  command: '',
  purpose: '',
  riskLevel: 'MEDIUM' as const,
  originalMessage: ''
})
const currentWorkflowId = ref<string | null>(null)

// Tab state
const activeTab = ref<string>('chat')

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
const novncUrl = ref('')

// Async function to load NoVNC URL
const loadNovncUrl = async () => {
  if (!store.currentSessionId) {
    // MIGRATED: Use AppConfig for VNC URL fallback
    try {
      novncUrl.value = await appConfig.getVncUrl('playwright')
    } catch (error: any) {
      console.warn('[ChatInterface] Failed to get VNC URL from AppConfig:', error.message)
      novncUrl.value = import.meta.env.VITE_PLAYWRIGHT_VNC_URL || 'http://172.16.168.25:6080/vnc.html'
    }
    return
  }

  // Get session without side effects to prevent reactive loops
  const session = store.sessions.find(s => s.id === store.currentSessionId)
  const baseUrl = import.meta.env.VITE_DESKTOP_VNC_URL || 'http://172.16.168.20:6080/vnc.html'

  if (!session?.desktopSession) {
    // Return base URL without creating session to prevent reactive side effects
    novncUrl.value = baseUrl + '?autoconnect=true&password=autobot&resize=remote'
    return
  }

  // Use existing desktop session data
  const params = new URLSearchParams({
    autoconnect: 'true',
    password: import.meta.env.VITE_DESKTOP_VNC_PASSWORD || 'autobot',
    resize: 'remote',
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

  if (messageCount === 0) {
    return 'No messages yet'
  }

  return `${messageCount} message${messageCount > 1 ? 's' : ''} • Last: ${lastMessageTime}`
})


// Methods
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
    console.error('Failed to export session:', error)
    appStore.setGlobalError('Failed to export chat session')
  }
}

const clearSession = async () => {
  if (!store.currentSessionId) return

  if (confirm('Clear all messages in this chat? This action cannot be undone.')) {
    try {
      await controller.resetCurrentChat()
    } catch (error) {
      console.error('Failed to clear session:', error)
      appStore.setGlobalError('Failed to clear chat session')
    }
  }
}

// Unified loading event handlers
const handleSidebarLoadingComplete = () => {
  console.log('[ChatInterface] Sidebar loading completed')
}

const handleSidebarLoadingError = (error: any) => {
  console.error('[ChatInterface] Sidebar loading error:', error)
  appStore.setGlobalError('Failed to load chat sessions')
}

const handleSidebarLoadingTimeout = () => {
  console.warn('[ChatInterface] Sidebar loading timed out')
}

const handleContentLoadingComplete = () => {
  console.log('[ChatInterface] Content loading completed')
}

const handleContentLoadingError = (error: any) => {
  console.error('[ChatInterface] Content loading error:', error)
  appStore.setGlobalError('Failed to load chat content')
}

const handleContentLoadingTimeout = () => {
  console.warn('[ChatInterface] Content loading timed out')
}

// Tab change handler - ensures local tab state change without router navigation
const handleTabChange = (tabKey: string) => {
  console.log('[ChatInterface] Tab change requested:', tabKey)

  // Prevent any router navigation and only update local state
  // This fixes the Terminal tab issue where it was triggering unwanted navigation
  activeTab.value = tabKey

  // Log successful tab change
  console.log('[ChatInterface] Active tab changed to:', activeTab.value)
}

// Terminal tab handler for explicit new tab opening (not used for tab clicks)
const openTerminalInNewTab = () => {
  // Open terminal in a new browser tab by navigating to tools/terminal
  window.open('/tools/terminal', '_blank')
}

// Dialog handlers
const onKnowledgeDecisionsApplied = (decisions: any) => {
  console.log('Knowledge decisions applied:', decisions)
  // Handle knowledge persistence decisions
}

const onChatCompiled = (compiledData: any) => {
  console.log('Chat compiled:', compiledData)
  // Handle compiled chat data
}

const onCommandApproved = (commandData: any) => {
  console.log('Command approved:', commandData)
  showCommandDialog.value = false
  // Execute the approved command
}

const onCommandDenied = (reason: string) => {
  console.log('Command denied:', reason)
  showCommandDialog.value = false
  // Handle command denial
}

const onCommandCommented = (comment: string) => {
  console.log('Command commented:', comment)
  // Handle command comment
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

const startHeartbeat = () => {
  // Clear any existing interval first
  if (heartbeatInterval.value) {
    clearInterval(heartbeatInterval.value)
  }
  // Check connection every 60 seconds (reduced from 30 to minimize UI updates)
  heartbeatInterval.value = setInterval(checkConnection, 60000)
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
        .catch((error: any) => console.warn('Auto-save failed:', error))
    }
  }, 2 * 60 * 1000)
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
    }
  }
}

// STREAMLINED: Simplified initialization without complex timeout racing
const initializeChatInterface = async () => {
  try {
    console.log('🚀 Starting streamlined chat interface initialization')

    // Load data with simple timeout
    const loadPromise = batchApiService.initializeChatInterface()
    const timeoutPromise = new Promise<never>((_, reject) => {
      setTimeout(() => reject(new Error('Initialization timeout')), 8000)
    })

    try {
      // Race initialization with timeout
      const data = await Promise.race([loadPromise, timeoutPromise])

      // Process results
      if (data.chat_sessions && !data.chat_sessions.error && Array.isArray(data.chat_sessions)) {
        data.chat_sessions.forEach((session: any) => {
          store.importSession(session)
        })
      }

      // Update connection status
      if (data.system_health && !data.system_health.error) {
        isConnected.value = data.system_health.status === 'healthy'
        baseConnectionStatus.value = isConnected.value ? 'Connected' : 'Disconnected'
      }
    } catch (error) {
      console.warn('⏱️ Initialization failed or timed out, using fallback:', error)
      // Fallback to individual loading
      if (store.sessions.length === 0) {
        await controller.loadChatSessions().catch(console.warn)
      }
    }

    console.log('✅ Chat interface initialization completed')

  } catch (error) {
    console.error('❌ Chat initialization failed:', error)
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
})

// Watch for session changes to update NoVNC URL
watch(() => store.currentSessionId, (newSessionId, oldSessionId) => {
  if (newSessionId !== oldSessionId) {
    // Session changed, reload NoVNC URL
    console.log('[ChatInterface] Session changed:', newSessionId)
    loadNovncUrl()
  }
})
</script>

<style scoped>
/* IMPROVED: Better overflow handling for chat interface */
.chat-interface {
  /* Removed height: 100vh - now relies on parent container */
}

/* CRITICAL FIX: Enhanced sidebar width constraint */
.sidebar-loading-view {
  /* Force sidebar width and prevent UnifiedLoadingView override */
  width: 320px !important; /* Force w-80 equivalent (320px) */
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
</style>