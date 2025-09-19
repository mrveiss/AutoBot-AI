<template>
  <ErrorBoundary fallback="Chat interface failed to load. Please refresh the page.">
    <div class="chat-interface flex h-full bg-white overflow-hidden">

      <!-- Chat Sidebar -->
      <ChatSidebar />

      <!-- Main Chat Area -->
      <div class="flex-1 flex flex-col min-w-0">

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
          @tab-change="activeTab = $event"
        />

        <!-- Chat Content -->
        <ChatTabContent
          :active-tab="activeTab"
          :current-session-id="store.currentSessionId"
          :novnc-url="novncUrl"
        />
      </div>

      <!-- Terminal Sidebar -->
      <TerminalSidebar
        v-if="showTerminalSidebar"
        :collapsed="terminalSidebarCollapsed"
        @update:collapsed="terminalSidebarCollapsed = $event"
        @open-new-tab="openTerminalInNewTab"
      />

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
import { ApiClient } from '@/utils/ApiClient.js'
import batchApiService from '@/services/BatchApiService'
import { API_CONFIG } from '@/config/environment.js'

// Components
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import ChatSidebar from './ChatSidebar.vue'
import ChatHeader from './ChatHeader.vue'
import ChatTabs from './ChatTabs.vue'
import ChatTabContent from './ChatTabContent.vue'
import KnowledgePersistenceDialog from '@/components/KnowledgePersistenceDialog.vue'
import CommandPermissionDialog from '@/components/CommandPermissionDialog.vue'
import WorkflowProgressWidget from '@/components/WorkflowProgressWidget.vue'
import TerminalSidebar from '@/components/TerminalSidebar.vue'

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
  riskLevel: 'MEDIUM',
  originalMessage: ''
})
const currentWorkflowId = ref<string | null>(null)

// Tab state
const activeTab = ref<string>('chat')

// Terminal sidebar state
const showTerminalSidebar = ref<boolean>(false)
const terminalSidebarCollapsed = ref<boolean>(false)

// Connection state
const connectionStatus = ref('Connected')
const isConnected = ref(true)
const lastHeartbeat = ref(Date.now())

// Tool URLs - Dynamic per-chat desktop URLs
const novncUrl = computed(() => {
  if (!store.currentSessionId) {
    return API_CONFIG.PLAYWRIGHT_VNC_URL // Fallback for no session
  }
  return store.getDesktopUrl(store.currentSessionId)
})

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

// Terminal tab handler
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

// Connection monitoring
const checkConnection = async () => {
  try {
    // Use ApiClient instead of direct fetch
    const apiClient = new ApiClient()
    const healthData = await apiClient.get('/api/health')
    
    // ApiClient returns data directly on success
    if (healthData) {
      isConnected.value = true
      connectionStatus.value = 'Connected'
      lastHeartbeat.value = Date.now()
    } else {
      isConnected.value = false
      connectionStatus.value = 'Disconnected'
    }
  } catch (error) {
    isConnected.value = false
    connectionStatus.value = 'Disconnected'
  }
}

// Interval refs for proper cleanup
const heartbeatInterval = ref(null)
const autoSaveInterval = ref(null)

const startHeartbeat = () => {
  // Clear any existing interval first
  if (heartbeatInterval.value) {
    clearInterval(heartbeatInterval.value)
  }
  // Check connection every 30 seconds
  heartbeatInterval.value = setInterval(checkConnection, 30000)
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
        .catch(error => console.warn('Auto-save failed:', error))
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

// Initialize chat interface with batch loading
const initializeChatInterface = async () => {
  try {
    console.log('🚀 Starting batch chat interface initialization')
    
    // Use batch API for optimized loading
    const data = await batchApiService.initializeChatInterface()
    
    // Process batch results
    if (data.chat_sessions && !data.chat_sessions.error) {
      // Load sessions into store if we got valid data
      if (Array.isArray(data.chat_sessions)) {
        data.chat_sessions.forEach(session => {
          store.importSession(session)
        })
      }
    } else if (store.sessions.length === 0) {
      // Fallback to individual loading if batch failed
      console.log('📡 Falling back to individual chat session loading')
      await controller.loadChatSessions()
    }
    
    // Update connection status from batch data
    if (data.system_health && !data.system_health.error) {
      isConnected.value = data.system_health.status === 'healthy'
      connectionStatus.value = isConnected.value ? 'Connected' : 'Disconnected'
    }
    
    console.log('✅ Batch chat initialization completed')
    
  } catch (error) {
    console.error('❌ Chat initialization failed:', error)
    // Fallback to traditional loading
    if (store.sessions.length === 0) {
      await controller.loadChatSessions().catch(err => 
        console.warn('Fallback session loading failed:', err)
      )
    }
  }
}

// Lifecycle
onMounted(async () => {
  // Initialize chat interface with batch loading
  await initializeChatInterface()

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

// Watch for session changes to update title
watch(() => store.currentSessionId, (newSessionId, oldSessionId) => {
  if (newSessionId !== oldSessionId) {
    // Session changed, could load messages if needed
    console.log('Session changed:', newSessionId)
  }
})

// Watch for typing status changes
watch(() => store.isTyping, (isTyping) => {
  if (isTyping) {
    connectionStatus.value = 'AI is typing...'
  } else if (isConnected.value) {
    connectionStatus.value = 'Connected'
  }
})

// Watch for tab changes to show/hide terminal sidebar
watch(() => activeTab.value, (newTab) => {
  showTerminalSidebar.value = newTab === 'terminal'
})
</script>

<style scoped>
.chat-interface {
  height: 100vh;
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
