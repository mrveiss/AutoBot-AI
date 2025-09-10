<template>
  <ErrorBoundary fallback="Chat interface failed to load. Please refresh the page.">
    <div class="chat-interface flex h-full bg-white overflow-hidden">

      <!-- Chat Sidebar -->
      <ChatSidebar />

      <!-- Main Chat Area -->
      <div class="flex-1 flex flex-col min-w-0">

        <!-- Chat Header -->
        <div class="chat-header bg-white border-b border-gray-200 px-6 py-4">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
              <div class="w-8 h-8 bg-indigo-600 rounded-full flex items-center justify-center">
                <i class="fas fa-robot text-white text-sm"></i>
              </div>
              <div>
                <h1 class="text-lg font-semibold text-gray-900">
                  {{ currentSessionTitle }}
                </h1>
                <p class="text-sm text-gray-500">
                  {{ sessionInfo }}
                </p>
              </div>
            </div>

            <div class="flex items-center gap-2">
              <!-- Session Actions -->
              <button
                v-if="store.currentSessionId"
                @click="exportSession"
                class="header-btn"
                title="Export chat"
              >
                <i class="fas fa-download"></i>
              </button>

              <button
                v-if="store.currentSessionId"
                @click="clearSession"
                class="header-btn"
                title="Clear chat"
              >
                <i class="fas fa-trash"></i>
              </button>

              <!-- Connection Status -->
              <div class="connection-status" :class="connectionStatusClass">
                <i :class="connectionStatusIcon"></i>
                <span class="text-sm">{{ connectionStatus }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Chat/Tools Tabs -->
        <div class="flex border-b border-gray-200 bg-white flex-shrink-0 overflow-x-auto">
          <button 
            @click="activeTab = 'chat'" 
            :class="['px-6 py-3 text-sm font-medium transition-colors whitespace-nowrap', activeTab === 'chat' ? 'border-b-2 border-indigo-500 text-indigo-600 bg-indigo-50' : 'text-gray-600 hover:text-gray-800 hover:bg-gray-50']"
          >
            <i class="fas fa-comments mr-2"></i>
            Chat
          </button>
          <button 
            @click="activeTab = 'files'" 
            :class="['px-6 py-3 text-sm font-medium transition-colors whitespace-nowrap', activeTab === 'files' ? 'border-b-2 border-indigo-500 text-indigo-600 bg-indigo-50' : 'text-gray-600 hover:text-gray-800 hover:bg-gray-50']"
          >
            <i class="fas fa-folder mr-2"></i>
            Files
          </button>
          <button 
            @click="activeTab = 'terminal'" 
            :class="['px-6 py-3 text-sm font-medium transition-colors whitespace-nowrap', activeTab === 'terminal' ? 'border-b-2 border-indigo-500 text-indigo-600 bg-indigo-50' : 'text-gray-600 hover:text-gray-800 hover:bg-gray-50']"
          >
            <i class="fas fa-terminal mr-2"></i>
            Terminal
          </button>
          <button 
            @click="activeTab = 'browser'" 
            :class="['px-6 py-3 text-sm font-medium transition-colors whitespace-nowrap', activeTab === 'browser' ? 'border-b-2 border-indigo-500 text-indigo-600 bg-indigo-50' : 'text-gray-600 hover:text-gray-800 hover:bg-gray-50']"
          >
            <i class="fas fa-globe mr-2"></i>
            Browser
          </button>
          <button 
            @click="activeTab = 'novnc'" 
            :class="['px-6 py-3 text-sm font-medium transition-colors whitespace-nowrap', activeTab === 'novnc' ? 'border-b-2 border-indigo-500 text-indigo-600 bg-indigo-50' : 'text-gray-600 hover:text-gray-800 hover:bg-gray-50']"
          >
            <i class="fas fa-desktop mr-2"></i>
            noVNC
          </button>
        </div>

        <!-- Chat Content -->
        <div class="flex-1 flex flex-col min-h-0">
          <!-- Chat Tab Content -->
          <div v-if="activeTab === 'chat'" class="flex-1 flex flex-col min-h-0">
            <ChatMessages />
            <ChatInput />
          </div>

          <!-- Files Tab Content -->
          <div v-else-if="activeTab === 'files'" class="flex-1 flex flex-col min-h-0">
            <FileBrowser 
              :key="store.currentSessionId"
              :chat-context="true"
              class="flex-1"
            />
          </div>

          <!-- Terminal Tab Content -->
          <div v-else-if="activeTab === 'terminal'" class="flex-1 flex flex-col min-h-0">
            <XTerminal 
              :key="store.currentSessionId"
              :session-id="store.currentSessionId"
              :chat-context="true"
              title="Chat Terminal"
              class="flex-1"
            />
          </div>

          <!-- Browser Tab Content -->
          <div v-else-if="activeTab === 'browser'" class="flex-1 flex flex-col min-h-0">
            <PopoutChromiumBrowser 
              :key="store.currentSessionId"
              :session-id="store.currentSessionId || 'chat-browser'"
              :chat-context="true"
              class="flex-1"
            />
          </div>

          <!-- noVNC Tab Content -->
          <div v-else-if="activeTab === 'novnc'" class="flex-1 flex flex-col min-h-0">
            <div class="flex-1 flex flex-col bg-black">
              <div class="flex justify-between items-center bg-gray-800 text-white px-4 py-2 text-sm">
                <span>
                  <i class="fas fa-desktop mr-2"></i>
                  Remote Desktop (Chat Session: {{ store.currentSessionId?.slice(-8) || 'N/A' }})
                </span>
                <a 
                  :href="novncUrl" 
                  target="_blank" 
                  class="text-indigo-300 hover:text-indigo-100 underline"
                  title="Open noVNC in new window"
                >
                  <i class="fas fa-external-link-alt mr-1"></i>
                  Open in New Window
                </a>
              </div>
              <iframe 
                :key="`desktop-${store.currentSessionId}`"
                :src="novncUrl"
                class="flex-1 w-full border-0"
                title="noVNC Remote Desktop"
                allowfullscreen
              ></iframe>
            </div>
          </div>
        </div>
      </div>

      <!-- Terminal Sidebar -->
      <!-- Temporarily commented out to fix reactive variable issues -->
      <!--
      <TerminalSidebar
        v-if="showTerminalSidebar"
        :collapsed="terminalSidebarCollapsed"
        @update:collapsed="terminalSidebarCollapsed = $event"
        @open-new-tab="openTerminalInNewTab"
      />
      -->

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

      <!-- Temporarily commented out to fix reactive variable issues -->
      <!--
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
      -->

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
import batchApiService from '@/services/BatchApiService.js'
import { API_CONFIG } from '@/config/environment.js'

// Components
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import ChatSidebar from './ChatSidebar.vue'
import ChatMessages from './ChatMessages.vue'
import ChatInput from './ChatInput.vue'
import KnowledgePersistenceDialog from '@/components/KnowledgePersistenceDialog.vue'
import FileBrowser from '@/components/FileBrowser.vue'
import PopoutChromiumBrowser from '@/components/PopoutChromiumBrowser.vue'
// import CommandPermissionDialog from '@/components/CommandPermissionDialog.vue' // Temporarily commented out
import WorkflowProgressWidget from '@/components/WorkflowProgressWidget.vue'
import XTerminal from '@/components/XTerminal.vue'

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

const connectionStatusClass = computed(() => ({
  'text-green-600': isConnected.value,
  'text-red-600': !isConnected.value,
  'text-yellow-600': connectionStatus.value === 'Connecting'
}))

const connectionStatusIcon = computed(() => {
  if (!isConnected.value) return 'fas fa-exclamation-circle'
  if (connectionStatus.value === 'Connecting') return 'fas fa-spinner fa-spin'
  return 'fas fa-check-circle'
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
    const healthData = await apiClient.get('/api/system/health')
    
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

const startHeartbeat = () => {
  // Check connection every 30 seconds
  const interval = setInterval(checkConnection, 30000)

  onUnmounted(() => {
    clearInterval(interval)
  })
}

// Auto-save functionality
const enableAutoSave = () => {
  // Auto-save current session every 2 minutes
  const interval = setInterval(() => {
    if (store.settings.autoSave && store.currentSessionId) {
      controller.saveChatSession()
        .catch(error => console.warn('Auto-save failed:', error))
    }
  }, 2 * 60 * 1000)

  onUnmounted(() => {
    clearInterval(interval)
  })
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
  document.removeEventListener('keydown', handleKeyboardShortcuts)
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

.chat-header {
  flex-shrink: 0;
}

.header-btn {
  @apply w-8 h-8 flex items-center justify-center text-gray-500 hover:text-gray-700 rounded transition-colors;
}

.header-btn:hover {
  @apply bg-gray-100;
}

.connection-status {
  @apply flex items-center gap-2 px-3 py-1 rounded-full bg-gray-100;
}

.workflow-progress-widget {
  @apply fixed bottom-4 right-4 z-50;
}

/* Responsive adjustments */
@media (max-width: 768px) {
  .chat-header {
    @apply px-4 py-3;
  }

  .chat-header h1 {
    @apply text-base;
  }

  .connection-status span {
    @apply hidden;
  }
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
