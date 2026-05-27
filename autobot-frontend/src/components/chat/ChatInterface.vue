<template>
  <ErrorBoundary :fallback="$t('chat.interface.loadFailed')">
    <div class="chat-interface flex h-full bg-autobot-bg-card overflow-hidden">

      <!-- Mobile Sidebar Backdrop -->
      <div
        v-if="showMobileSidebar"
        class="lg:hidden fixed inset-0 bg-black/40 z-30"
        @click="showMobileSidebar = false"
        aria-hidden="true"
      ></div>

      <!-- Chat Sidebar -->
      <!-- Desktop: inline. Mobile: fixed overlay when showMobileSidebar is true -->
      <div
        :class="[
          'sidebar-loading-view h-full shrink-0',
          'hidden lg:block',
          store.sidebarCollapsed ? 'w-12' : 'w-80',
        ]"
      >
        <ChatSidebar />
      </div>

      <!-- Mobile Sidebar Overlay -->
      <Transition
        enter-active-class="transition duration-250 ease-out"
        enter-from-class="-translate-x-full"
        enter-to-class="translate-x-0"
        leave-active-class="transition duration-200 ease-in"
        leave-from-class="translate-x-0"
        leave-to-class="-translate-x-full"
      >
        <div
          v-if="showMobileSidebar"
          class="lg:hidden fixed top-0 left-0 h-full w-80 max-w-[85vw] z-40 shadow-2xl overflow-hidden"
        >
          <ChatSidebar @close-mobile="showMobileSidebar = false" />
        </div>
      </Transition>

      <!-- Main Chat Area -->
      <div class="flex-1 flex flex-col min-w-0 min-h-0 relative overflow-hidden">

        <!-- Chat Header (Sticky at top) -->
        <ChatHeader
          :current-session-id="store.currentSessionId"
          :current-session-title="currentSessionTitle"
          :session-info="sessionInfo"
          :connection-status="connectionStatus"
          :is-connected="isConnected"
          @export-session="exportSession"
          @clear-session="clearSession"
          @toggle-mobile-sidebar="showMobileSidebar = !showMobileSidebar"
          class="shrink-0"
        >
          <!-- File Panel Toggle Button (injected into header) -->
          <template #actions>
            <!-- Voice controls group (GH#8755): proximity grouping for audio actions -->
            <div role="group" aria-label="Voice controls" class="header-btn-group">
              <!-- Voice Output Toggle (#928) -->
              <button
                @click="toggleVoiceOutput"
                class="header-btn"
                :class="{ 'bg-electric-100 text-electric-600': voiceOutputEnabled }"
                :title="voiceOutputEnabled ? $t('chat.interface.voiceOutputOn') : $t('chat.interface.voiceOutputOff')"
              >
                <Icon :name="isSpeaking || voiceOutputEnabled ? 'volume-up' : 'volume-mute'" :class="isSpeaking ? 'animate-pulse' : ''" />
              </button>
              <!-- Voice Conversation (#1029) -->
              <button
                @click="openVoiceConversation"
                class="header-btn"
                :class="{ 'bg-electric-100 text-electric-600': showVoiceOverlay || showVoicePanel }"
                :title="$t('chat.interface.voiceChat')"
              >
                <Icon name="headset" />
              </button>
            </div>
            <!-- Divider between voice group and utility actions -->
            <div class="header-btn-divider" aria-hidden="true"></div>
            <button
              v-if="store.currentSessionId"
              @click="toggleFilePanel"
              class="header-btn"
              :class="{ 'bg-electric-100 text-electric-600': showFilePanel }"
              :title="$t('chat.interface.toggleFilePanel')"
            >
              <Icon name="paperclip" />
            </button>
            <!-- Issue #4414: multi-model comparison toggle -->
            <button
              @click="showComparePanel = !showComparePanel"
              class="header-btn"
              :class="{ 'bg-electric-100 text-electric-600': showComparePanel }"
              :title="$t('chat.compare.toggleTitle')"
              :aria-pressed="showComparePanel"
            >
              <Icon name="columns" />
            </button>
          </template>
        </ChatHeader>

        <!-- Chat/Tools Tabs (FIXED: outside scrollable container so sticky works) -->
        <ChatTabs
          :active-tab="activeTab"
          @tab-change="handleTabChange"
          class="shrink-0"
        />

        <!-- Scrollable Content Area (Header scrolls away, input stays) -->
        <div class="flex-1 min-h-0 flex flex-col overflow-hidden">
          <!-- Issue #3232: Live reasoning trace panel above the chat input -->
          <ReasoningTrace
            v-if="activeTab === 'chat'"
            :entries="cotEntries"
            :is-active="cotIsActive"
            class="mx-2 mt-1"
          />
          <!-- Issue #4414: multi-model comparison panel -->
          <MultiModelChat
            v-if="showComparePanel && activeTab === 'chat'"
            class="mx-2 mt-1"
          />
          <ChatTabContent
            :active-tab="activeTab"
            :current-session-id="store.currentSessionId"
            :novnc-url="novncUrl"
            @tool-call-detected="handleToolCallDetected"
            @vision-send-to-chat="handleVisionSendToChat"
          />
        </div>
      </div>

      <!-- Right side panels (mutually exclusive) -->
      <Transition name="slide-left">
        <ChatFilePanel
          v-if="showFilePanel && store.currentSessionId"
          :session-id="store.currentSessionId"
          @close="showFilePanel = false"
        />
        <VoiceConversationPanel
          v-else-if="showVoicePanel"
          @close="closeVoicePanel"
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

      <!-- Agent-Loop Tool Approval Dialog (#4952) -->
      <!-- Shown when the agent loop publishes APPROVAL_REQUIRED for a sensitive tool -->
      <div
        v-if="pendingToolApproval"
        ref="toolApprovalDialogRef"
        class="tool-approval-overlay"
        role="dialog"
        aria-modal="true"
        :aria-label="$t('chat.interface.toolApprovalTitle')"
        tabindex="-1"
        @keydown="onToolApprovalKeydown"
        @keydown.escape="onToolDenied()"
      >
        <div class="tool-approval-dialog">
          <div class="tool-approval-header">
            <Icon name="shield-alt" />
            <h3>{{ $t('chat.interface.toolApprovalTitle') }}</h3>
          </div>
          <div class="tool-approval-body">
            <div class="tool-approval-row">
              <span class="tool-approval-label">{{ $t('chat.interface.toolApprovalTool') }}</span>
              <code class="tool-approval-value">{{ pendingToolApproval.tool_name }}</code>
            </div>
            <div class="tool-approval-row">
              <span class="tool-approval-label">{{ $t('chat.interface.toolApprovalRisk') }}</span>
              <span class="tool-approval-value" :class="`risk-${pendingToolApproval.risk_level.toLowerCase()}`">{{ pendingToolApproval.risk_level }}</span>
            </div>
            <div class="tool-approval-row">
              <span class="tool-approval-label">{{ $t('chat.interface.toolApprovalReason') }}</span>
              <span class="tool-approval-value">{{ pendingToolApproval.reason }}</span>
            </div>
            <div v-if="Object.keys(pendingToolApproval.arguments).length" class="tool-approval-row">
              <span class="tool-approval-label">{{ $t('chat.interface.toolApprovalArgs') }}</span>
              <pre class="tool-approval-args">{{ JSON.stringify(pendingToolApproval.arguments, null, 2) }}</pre>
            </div>
            <!-- Issue #4960: countdown timer -->
            <div class="tool-approval-countdown" role="timer" :aria-label="$t('chat.interface.toolApprovalCountdown', { seconds: toolApprovalSecondsLeft })">
              <div class="tool-approval-countdown-bar-track">
                <div
                  class="tool-approval-countdown-bar-fill"
                  :style="{ width: `${(toolApprovalSecondsLeft / Math.max(1, pendingToolApproval?.timeout_seconds ?? 1)) * 100}%` }"
                  :class="toolApprovalSecondsLeft <= 10 ? 'tool-approval-countdown-bar-fill--urgent' : ''"
                ></div>
              </div>
              <span class="tool-approval-countdown-label">{{ $t('chat.interface.toolApprovalCountdown', { seconds: toolApprovalSecondsLeft }) }}</span>
            </div>
          </div>
          <div class="tool-approval-footer">
            <button
              class="tool-approval-btn tool-approval-btn--deny"
              :disabled="submittingApproval"
              @click="onToolDenied()"
            >
              <Icon name="times" />
              {{ $t('chat.interface.toolApprovalDeny') }}
            </button>
            <button
              class="tool-approval-btn tool-approval-btn--approve"
              :disabled="submittingApproval"
              @click="onToolApproved()"
            >
              <Icon name="check" />
              {{ submittingApproval ? $t('chat.interface.toolApprovalSubmitting') : $t('chat.interface.toolApprovalApprove') }}
            </button>
          </div>
        </div>
      </div>

      <!-- Workflow Progress Widget -->
      <div v-if="showWorkflowProgress" class="workflow-progress-widget">
        <WorkflowProgressWidget
          :workflow-id="currentWorkflowId ?? undefined"
          @close="showWorkflowProgress = false"
        />
      </div>
    </div>

    <!-- Voice Conversation Overlay (#1029) — only mount for modal mode -->
    <VoiceConversationOverlay
      v-if="showVoiceOverlay"
      @close="showVoiceOverlay = false"
    />
  </ErrorBoundary>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, onMounted, onUnmounted, onActivated, onDeactivated, watch, provide } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useBackoffPoller } from '@/composables/useBackoffPoller'
import { useFocusTrap } from '@/composables/useFocusTrap'
import { useFocusRestore } from '@/composables/useFocusRestore'
import { useInitialFocus } from '@/composables/useInitialFocus'
import { useBodyScrollLock } from '@/composables/useBodyScrollLock'
import { useVoiceOutput } from '@/composables/useVoiceOutput'
import { useVoiceConversation } from '@/composables/useVoiceConversation'
import { useChatStore } from '@/stores/useChatStore'
import { useChatController } from '@/models/controllers'
import { useAppStore } from '@/stores/useAppStore'
import { useNotificationBus } from '@/composables/useNotificationBus'
import { usePreferences } from '@/composables/usePreferences'
import { useOverseerAgent } from '@/composables/useOverseerAgent'
import ApiClient from '@/utils/ApiClient'
import batchApiService from '@/services/BatchApiService'
// MIGRATED: Using AppConfig.js for better configuration management
import appConfig from '@/config/AppConfig.js'
import { getApiBase } from '@/config/ssot-config'
// FIXED: Import NetworkConstants for IP fallback values
import { NetworkConstants } from '@/constants/network'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ChatInterface')

// Components
import ErrorBoundary from '@/components/common/ErrorBoundary.vue'
import ChatSidebar from './ChatSidebar.vue'
import ChatHeader from './ChatHeader.vue'
import ChatTabs from './ChatTabs.vue'
import ChatTabContent from './ChatTabContent.vue'
import ChatFilePanel from './ChatFilePanel.vue'
import KnowledgePersistenceDialog from '@/components/knowledge/KnowledgePersistenceDialog.vue'
import CommandPermissionDialog from '@/components/ui/CommandPermissionDialog.vue'
import WorkflowProgressWidget from '@/components/workflow/WorkflowProgressWidget.vue'
import VoiceConversationOverlay from './VoiceConversationOverlay.vue'
import VoiceConversationPanel from './VoiceConversationPanel.vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
// Issue #3232: chain-of-thought reasoning trace
import ReasoningTrace from './ReasoningTrace.vue'
import { useReasoningTrace } from '@/composables/useReasoningTrace'
// Issue #4952: agent-loop tool approval
import { useToolApproval, type PendingToolApproval } from '@/composables/useToolApproval'
// Issue #4414: multi-model comparison
import MultiModelChat from './MultiModelChat.vue'

// i18n
const { t } = useI18n()

// Router — tab routes (#6415)
const route = useRoute()
const router = useRouter()

// Stores and controller
const store = useChatStore()
const controller = useChatController()
const appStore = useAppStore()

// Issue #3232: Chain-of-thought reasoning trace
const {
  entries: cotEntries,
  isActive: cotIsActive,
  clear: cotClear,
} = useReasoningTrace(store.currentSessionId)

// Issue #4952: agent-loop tool approval via POST /api/agent-terminal/tools/approve/{id}
const {
  pendingToolApproval,
  submittingApproval,
  submitToolApproval,
  clearToolApproval,
} = useToolApproval()

// Issue #4960: countdown timer — tracks seconds remaining until server auto-denies
const toolApprovalSecondsLeft = ref<number>(0)
let _countdownInterval: ReturnType<typeof setInterval> | null = null

const _stopCountdown = (): void => {
  if (_countdownInterval !== null) {
    clearInterval(_countdownInterval)
    _countdownInterval = null
  }
}

const _startCountdown = (timeoutSeconds: number, deadlineTs?: number): void => {
  _stopCountdown()
  toolApprovalSecondsLeft.value = timeoutSeconds
  _countdownInterval = setInterval(() => {
    // Issue #5024: use server deadline_ts for drift-free countdown when available
    const currentApproval = pendingToolApproval.value
    if (currentApproval?.deadline_ts) {
      toolApprovalSecondsLeft.value = Math.max(0, Math.round(currentApproval.deadline_ts - Date.now() / 1000))
    } else {
      toolApprovalSecondsLeft.value = Math.max(0, toolApprovalSecondsLeft.value - 1)
    }
    if (toolApprovalSecondsLeft.value <= 0) {
      _stopCountdown()
    }
  }, 1000)
}

// Start countdown when a new approval arrives; stop when cleared
watch(pendingToolApproval, (approval: PendingToolApproval | null) => {
  if (approval) {
    _startCountdown(approval.timeout_seconds, approval.deadline_ts)
  } else {
    _stopCountdown()
  }
}, { immediate: false })

// Tool-approval dialog a11y kit (#5410). Escape denies (safer default
// for a security prompt — avoids accidental approval via keyboard).
const toolApprovalDialogRef = ref<HTMLElement | null>(null)
const isToolApprovalOpen = computed(() => pendingToolApproval.value !== null)
const { onKeydown: onToolApprovalKeydown } = useFocusTrap(toolApprovalDialogRef)
useFocusRestore(isToolApprovalOpen)
useBodyScrollLock(isToolApprovalOpen)
const { focusFirst: focusToolApprovalFirst } = useInitialFocus(toolApprovalDialogRef)
watch(isToolApprovalOpen, (open) => { if (open) focusToolApprovalFirst() }, { immediate: true })

const onToolApproved = async (comment?: string): Promise<void> => {
  _stopCountdown()
  try {
    await submitToolApproval(true, comment)
    notify(t('chat.interface.toolApprovalApprovedMsg'), 'success')
  } catch {
    notify(t('chat.interface.toolApprovalErrorMsg'), 'error')
  }
}

const onToolDenied = async (comment?: string): Promise<void> => {
  _stopCountdown()
  try {
    await submitToolApproval(false, comment)
    notify(t('chat.interface.toolApprovalDeniedMsg'), 'warning')
  } catch {
    // On error, clear anyway so the dialog doesn't stay open forever
    clearToolApproval()
    notify(t('chat.interface.toolApprovalErrorMsg'), 'error')
  }
}

// Voice output (#928)
const {
  voiceOutputEnabled, isSpeaking, toggleVoiceOutput,
  speak, speakStreaming, flushStreaming,
} = useVoiceOutput()

// Voice conversation (#1029)
const voiceConversation = useVoiceConversation()
const showVoiceOverlay = ref(false)
const showVoicePanel = ref(false)
const { voiceDisplayMode } = usePreferences()

function openVoiceConversation(): void {
  if (voiceDisplayMode.value === 'sidepanel') {
    showFilePanel.value = false
    showVoicePanel.value = true
  } else {
    showVoiceOverlay.value = true
  }
  voiceConversation.activate()
}

function closeVoicePanel(): void {
  showVoicePanel.value = false
}

// Toast notifications
const { showToast } = useNotificationBus()
const notify = (message: string, type: 'info' | 'success' | 'warning' | 'error' = 'info') => {
  showToast(message, type, type === 'error' ? 0 : type === 'warning' ? 6000 : 4000)
}

// Issue #4414: multi-model compare panel toggle
const showComparePanel = ref(false)

// Dialog states
const showKnowledgeDialog = ref(false)
const showCommandDialog = ref(false)
const showWorkflowProgress = ref(false)
const showFilePanel = ref(false)
// Mobile sidebar overlay (#1804)
const showMobileSidebar = ref(false)

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

// Tab state — initialized from route meta so /chat/terminal and /chat/novnc deep-link correctly
const activeTab = ref<string>((route.meta.chatTab as string) ?? 'chat')
watch(() => route.meta.chatTab, (tab: unknown) => { activeTab.value = (tab as string) ?? 'chat' })

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
      notify(t('chat.interface.executionPlanCreated'), 'info')
    },
    onStepUpdate: (step) => {
      logger.debug('[Overseer] Step update:', { step_number: step.step_number, status: step.status })
    },
    onStreamChunk: (chunk) => {
      logger.debug('[Overseer] Stream chunk:', chunk.chunk_type)
    },
    onError: (error) => {
      logger.error('[Overseer] Error:', error)
      notify(t('chat.interface.overseerError', { error }), 'error')
    },
    onComplete: () => {
      logger.info('[Overseer] Execution complete')
      notify(t('chat.interface.executionCompleted'), 'success')
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

// Connection state with stabilized status management.
// #6773: backend-health is now sourced from `appStore.backendStatus`, which is
// driven by `OptimizedHealthMonitor` (the canonical /api/system/health poller
// wired in App.vue). Removed the local 60 s heartbeat poller that previously
// also hit /api/system/health, eliminating duplicate polling.
const baseConnectionStatus = ref(t('status.connected'))
const isConnected = ref(true)
const connectionStatus = computed(() => {
  // If typing, show typing status temporarily
  if (store.isTyping) {
    return t('chat.interface.aiTyping')
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
  if (!session) return t('chat.newChat')

  return session.title || `Chat ${session.id.slice(-8)}...`
})

const sessionInfo = computed(() => {
  const session = store.currentSession
  if (!session) return t('chat.interface.startConversation')

  const messageCount = session.messages.length
  const lastMessage = session.messages[session.messages.length - 1]
  const lastMessageTime = lastMessage ? new Date(lastMessage.timestamp).toLocaleTimeString() : null
  const sessionId = session.id  // Display full UUID

  if (messageCount === 0) {
    return t('chat.interface.sessionNoMessages', { sessionId })
  }

  return t('chat.interface.sessionInfo', { sessionId, count: messageCount, time: lastMessageTime })
})


// Methods
const toggleFilePanel = () => {
  showVoicePanel.value = false
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
    appStore.setGlobalError(t('chat.interface.failedToExport'))
  }
}

const clearSession = async () => {
  if (!store.currentSessionId) return

  if (confirm(t('chat.interface.confirmClear'))) {
    try {
      await controller.resetCurrentChat()
    } catch (error) {
      logger.error('Failed to clear session:', error)
      appStore.setGlobalError(t('chat.interface.failedToClear'))
    }
  }
}

// Tab change handler — updates local state and syncs URL to the named tab route (#6415)
const handleTabChange = (tabKey: string) => {
  logger.debug('Tab change requested:', tabKey)
  activeTab.value = tabKey
  const routeName = tabKey === 'chat' ? 'chat-default' : `chat-${tabKey}`
  router.push({ name: routeName }).catch(() => {})
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

// Issue #1242: Handle vision analysis results being sent to chat
const handleVisionSendToChat = (payload: {
  filename: string
  intent: string
  question?: string
  result: {
    confidence: number
    processing_time: number
    device_used?: string
    result_data: Record<string, unknown>
  }
}) => {
  logger.debug('Vision analysis sent to chat:', payload.filename)

  const intentLabels: Record<string, string> = {
    analysis: 'General Analysis',
    visual_qa: 'Visual Q&A',
    automation: 'Automation Detection',
    content_generation: 'Content Generation',
  }
  const intentLabel = intentLabels[payload.intent] || payload.intent

  // Add user message
  store.addMessage({
    content: `Analyzed image: **${payload.filename}** (${intentLabel})${payload.question ? `\nQuestion: ${payload.question}` : ''}`,
    sender: 'user',
    status: 'sent',
    type: 'message',
  })

  // Build formatted assistant response
  const rd = payload.result.result_data as Record<string, unknown>
  const parts: string[] = []

  parts.push(`**Image Analysis Results** — ${(payload.result.confidence * 100).toFixed(1)}% confidence, ${payload.result.processing_time.toFixed(2)}s`)

  if (rd.description) {
    parts.push(`\n**Description:** ${rd.description}`)
  }
  if (Array.isArray(rd.labels) && rd.labels.length > 0) {
    parts.push(`\n**Labels:** ${rd.labels.join(', ')}`)
  }
  if (Array.isArray(rd.objects) && rd.objects.length > 0) {
    const objLines = (rd.objects as Array<{ name?: string; label?: string; confidence?: number }>)
      .map(o => {
        const name = o.name || o.label || 'Unknown'
        const conf = o.confidence
          ? ` (${(o.confidence * 100).toFixed(0)}%)`
          : ''
        return `- ${name}${conf}`
      })
      .join('\n')
    parts.push(`\n**Detected Objects:**\n${objLines}`)
  }

  if (payload.result.device_used) {
    parts.push(`\n*Processed on: ${payload.result.device_used}*`)
  }

  store.addMessage({
    content: parts.join('\n'),
    sender: 'assistant',
    status: 'sent',
    type: 'message',
  })
}

const onCommandApproved = async (commandData: any) => {
  logger.debug('Command approved:', commandData)

  // IMPORTANT: The backend is already waiting for approval and will execute automatically.
  // CommandPermissionDialog has already sent the approval POST request.
  // We just need to close the dialog and switch to terminal tab.
  // The backend polling loop will detect the approval and execute the command.

  // Switch to terminal tab to show execution
  handleTabChange('terminal')

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
        `${getApiBase()}/agent-terminal/sessions/${pendingCommand.value.terminalSessionId}/approve`
      )

      const response = await fetchWithAuth(approvalUrl, {
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
      notify(t('chat.interface.feedbackSent'), 'success')
    }

    // Close the dialog
    showCommandDialog.value = false

    // The comment was already sent to chat via CommandPermissionDialog
    // The agent will receive the denial + feedback and can propose an alternative
  } catch (error) {
    logger.error('Error sending command comment/denial:', error)
    notify(t('chat.interface.feedbackFailed'), 'error')
  }
}

// #6773: connection state is mirrored from `appStore.backendStatus`, which
// `OptimizedHealthMonitor` updates from /api/system/health. Replaces the
// previous 60 s `appConfig.validateConnection()` poller — that poller was
// hitting the same endpoint as `OptimizedHealthMonitor`, producing duplicate
// /api/system/health requests per polling interval.
const syncConnectionFromStore = (): void => {
  const cls = appStore.backendStatus.class
  // 'success' is the only state that maps to "connected"; both 'warning'
  // (degraded) and 'error' (disconnected) surface as not-connected here, to
  // preserve the previous boolean semantics expected by isConnected consumers.
  isConnected.value = cls === 'success'
  baseConnectionStatus.value = cls === 'success'
    ? t('status.connected')
    : t('status.disconnected')
}

// React to OptimizedHealthMonitor → appStore updates immediately.
watch(() => appStore.backendStatus.class, syncConnectionFromStore, { immediate: false })

// #6746: autosave poller deleted. Backend now persists every chat message
// via add_messages_batch in the request handler (#6744 fix), so frontend-
// driven autosave is redundant — and was a session_id churn source: it ran
// every 2 min against `store.currentSessionId`, which could be racing with
// pushLocalOnlySessions, syncSessionsWithBackend, or message-poller
// state churn. Backend writes are now the sole authoritative path.

// Message polling with exponential backoff + circuit breaker (#1100)
// Prevents 499 cascade: skips in-flight polls, backs off on failure, opens circuit
// after 3 consecutive errors and retries slowly.
const messagePoller = useBackoffPoller({
  baseInterval: 30_000,          // 30 s when healthy (increased for inactive sessions #3999)
  maxInterval: 60_000,           // cap at 60 s during backoff
  backoffMultiplier: 2,
  circuitBreakerThreshold: 3,
  circuitBreakerResetMs: 60_000, // 60 s open-circuit probe interval
  fn: async () => {
    // Skip while AI is streaming to prevent message flickering
    if (store.isTyping) {
      logger.debug('Skipping message poll - AI is typing')
      return
    }
    if (!store.currentSessionId) return
    await controller.loadChatMessages(store.currentSessionId)
  },
})

const startMessagePolling = () => {
  logger.debug('Starting message polling (backoff poller, base 30 s)')
  messagePoller.start()
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
      // Explicitly check for error to distinguish API failures from empty responses
      if (data.chat_sessions && !data.chat_sessions.error && data.chat_sessions.data) {
        const sessions = data.chat_sessions.data
        // Issue #4431: Push local-only sessions to backend before sync so they are
        // not wiped by syncSessionsWithBackend. Only sessions with real messages are
        // pushed (empty placeholders are skipped).
        const backendIds = new Set<string>((sessions as Array<{ id: string }>).map(s => s.id))
        await controller.pushLocalOnlySessions(backendIds)
        // Issue #4352: intentional_empty=true means the backend confirmed 0 sessions
        // is correct (user deleted all). Pass this through so syncSessionsWithBackend
        // can bypass the #4328 defensive guard and clear local sessions as intended.
        const intentionalEmpty = Boolean(data.chat_sessions.intentional_empty)
        store.syncSessionsWithBackend(sessions, intentionalEmpty)
      } else if (data.chat_sessions?.error) {
        // Explicit error case - log and proceed with fallback
        logger.warn('Failed to load chat sessions from backend:', data.chat_sessions.error)
      }

      // Update connection status
      if (data.system_health && !data.system_health.error && data.system_health.data) {
        const healthData = data.system_health.data as Record<string, unknown>
        isConnected.value = healthData.status === 'healthy'
        baseConnectionStatus.value = isConnected.value ? t('status.connected') : t('status.disconnected')
      } else if (data.system_health?.error) {
        // Explicit error case for system health
        logger.warn('Failed to load system health:', data.system_health.error)
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
    notify(t('chat.interface.initFailed'), 'error')

    appStore.setGlobalError(t('chat.interface.failedToInit'))
  }
}

// Lifecycle
let _lgMediaQuery: MediaQueryList | null = null

function _onLgBreakpoint(e: MediaQueryListEvent): void {
  if (e.matches) showMobileSidebar.value = false
}

onMounted(async () => {
  // Initialize chat interface with streamlined loading
  await initializeChatInterface()

  // Load NoVNC URL after initialization
  await loadNovncUrl()

  // #6773: connection state mirrors appStore.backendStatus (driven by
  // OptimizedHealthMonitor). Seed once from current store state so initial
  // render reflects the latest known status without an extra fetch.
  syncConnectionFromStore()
  // #6746: autosave removed; backend persists messages directly

  // Start message polling to fetch new messages
  startMessagePolling()

  // Add keyboard shortcuts
  document.addEventListener('keydown', handleKeyboardShortcuts)

  // Reset mobile sidebar when viewport reaches desktop width (#4446)
  _lgMediaQuery = window.matchMedia('(min-width: 1024px)')
  _lgMediaQuery.addEventListener('change', _onLgBreakpoint)

})

onUnmounted(() => {
  // Clean up event listeners
  document.removeEventListener('keydown', handleKeyboardShortcuts)
  _lgMediaQuery?.removeEventListener('change', _onLgBreakpoint)
  _lgMediaQuery = null

  // Clean up intervals (#6773: heartbeatPoller removed — see syncConnectionFromStore)
  _stopCountdown()
  messagePoller.stop()
})

// Issue #4356: Handle keep-alive activation (component re-enters view)
// Resume polling and heartbeat when ChatInterface is activated from keep-alive cache
onActivated(() => {
  logger.debug('[ChatInterface] Activated from keep-alive - resuming operations')

  // #6773: re-seed connection state from the canonical store on re-activation;
  // the watch() above keeps it in sync going forward.
  syncConnectionFromStore()

  // Resume auto-save
  // #6746: autosave removed; backend persists messages directly

  // Resume message polling
  startMessagePolling()

  // Re-attach keyboard shortcuts
  document.addEventListener('keydown', handleKeyboardShortcuts)
})

// Issue #4356: Handle keep-alive deactivation (component leaves view but stays cached)
// Pause polling and cleanup before caching to reduce background activity
onDeactivated(() => {
  logger.debug('[ChatInterface] Deactivated for keep-alive caching - pausing operations')

  // Pause message polling (will resume on onActivated)
  messagePoller.stop()

  // #6773: heartbeatPoller removed — connection state is now passive (watcher
  // on appStore.backendStatus); no interval to pause.

  // Clean up keyboard shortcuts while cached
  document.removeEventListener('keydown', handleKeyboardShortcuts)
})

// Watch for session changes to update NoVNC URL
watch(() => store.currentSessionId, (newSessionId, oldSessionId) => {
  if (newSessionId !== oldSessionId) {
    // Session changed, reload NoVNC URL
    logger.debug('[ChatInterface] Session changed:', newSessionId)
    loadNovncUrl()

    // Close file panel when switching sessions
    showFilePanel.value = false
    showVoicePanel.value = false

    // Prime TTS cursor to end of new session's last speakable message (#1488).
    // Without this the TTS watcher fires, sees current.id !== _lastStreamingMsgId,
    // resets _lastSpokenIdx = 0, and re-speaks the full existing message.
    _primeTtsCursor()

    // Issue #3232: clear reasoning trace on session switch so stale entries
    // from the previous session are not shown in the new one.
    cotClear()
  }
})

// Issue #3232: clear reasoning trace when a new user turn begins (isTyping goes
// from false → true, meaning the backend just started processing a new message).
watch(
  () => store.isTyping,
  (nowTyping, wasTyping) => {
    if (nowTyping && !wasTyping) {
      cotClear()
    }
  },
)

// Streaming sentence-level TTS (#1319)
// During LLM streaming: extract completed sentences and send each to TTS immediately.
// After streaming: flush remainder. Falls back to HTTP speak() if WS unavailable.
const _SPEAKABLE_TYPES = new Set(['response', 'message'])
let _lastSpokenIdx = 0
let _lastStreamingMsgId: string | null = null

/** Prime TTS cursor to end of current last message. Used on voice-enable and session switch. */
function _primeTtsCursor(): void {
  const session = store.sessions.find(s => s.id === store.currentSessionId)
  const msgs = session?.messages ?? []
  for (let i = msgs.length - 1; i >= 0; i--) {
    const m = msgs[i]
    if (m.sender !== 'assistant' || !m.content) continue
    if (m.type && !_SPEAKABLE_TYPES.has(m.type)) continue
    _lastStreamingMsgId = m.id
    _lastSpokenIdx = m.content.length
    break
  }
}

// When voice output is enabled mid-stream, prime cursor to current content end
// so already-accumulated text is not re-spoken (#1491).
watch(voiceOutputEnabled, (enabled) => {
  if (enabled) _primeTtsCursor()
})

watch(
  () => {
    const session = store.sessions.find(s => s.id === store.currentSessionId)
    const msgs = session?.messages ?? []
    for (let i = msgs.length - 1; i >= 0; i--) {
      const m = msgs[i]
      if (m.sender !== 'assistant' || !m.content) continue
      if (m.type && !_SPEAKABLE_TYPES.has(m.type)) continue
      return { id: m.id, content: m.content }
    }
    return null
  },
  (current, previous) => {
    if (!voiceOutputEnabled.value || voiceConversation.isActive.value) return
    if (!current) return

    // Reset index when message changes.
    // If not actively streaming, treat the incoming message as already-spoken (#1490):
    // it is a historical message (session switch with unloaded messages, page reload,
    // etc.) and should not be re-spoken. Only reset to 0 when isTyping so newly
    // generated content is picked up from the start.
    if (current.id !== _lastStreamingMsgId) {
      _lastStreamingMsgId = current.id
      _lastSpokenIdx = store.isTyping ? 0 : current.content.length
    }

    if (store.isTyping && current.content) {
      // During streaming: extract and speak completed sentences
      const newText = current.content.slice(_lastSpokenIdx)
      const sentences = _extractCompleteSentences(newText)
      for (const s of sentences) {
        speakStreaming(s)
        _lastSpokenIdx += s.length
      }
    } else if (!store.isTyping && current.content) {
      // Stream ended: flush any remaining text
      const remainder = current.content.slice(_lastSpokenIdx).trim()
      if (remainder) speakStreaming(remainder)
      flushStreaming()
      // Mark all content as spoken — do NOT reset to 0/null here.
      // Resetting _lastStreamingMsgId to null would cause any subsequent reactive
      // trigger (e.g. updateMessage({status:'sent'}) in the finalization loop) to
      // see current.id !== null, reset _lastSpokenIdx to 0, and re-speak the full
      // accumulated content. Keep current.id so spurious re-triggers are no-ops.
      _lastSpokenIdx = current.content.length
    }
  }
)

// Minimum chars a candidate sentence must have before it is dispatched to TTS (#1485).
// Short fragments like "Hello there! " (13 chars) sound choppy when spoken alone —
// buffer them until they combine with the next sentence or flush as a remainder.
const _MIN_TTS_SENTENCE_CHARS = 20

/** Extract sentences terminated by ". ", "! ", or "? " — remainder stays buffered. */
function _extractCompleteSentences(text: string): string[] {
  const sentences: string[] = []
  const terminators = /(?<=[.!?])\s+/g
  let lastEnd = 0
  let match
  while ((match = terminators.exec(text)) !== null) {
    const candidate = text.slice(lastEnd, match.index + 1)
    if (candidate.length >= _MIN_TTS_SENTENCE_CHARS) {
      sentences.push(candidate)
      lastEnd = match.index + match[0].length
    }
  }
  return sentences
}
</script>

<style scoped>
@reference "../../assets/tailwind.css";
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
  transition: transform var(--duration-300) var(--ease-out), opacity var(--duration-300) var(--ease-out);
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
  @apply w-8 h-8 flex items-center justify-center rounded-md transition-colors text-autobot-text-secondary hover:bg-autobot-bg-tertiary;
}

/* GH#8755: voice action group — subtle pill wraps related audio controls */
.header-btn-group {
  @apply flex items-center gap-0.5 rounded-md px-0.5;
  background: var(--bg-tertiary);
}

/* GH#8755: vertical divider between voice group and utility buttons */
.header-btn-divider {
  @apply self-stretch my-1 mx-1;
  width: 1px;
  background: var(--border-light);
}

/* Agent-loop tool approval dialog (#4952) */
.tool-approval-overlay {
  @apply fixed inset-0 z-50 flex items-center justify-center bg-black/50;
}
.tool-approval-dialog {
  @apply bg-autobot-bg-card rounded-xl shadow-2xl max-w-md w-full mx-4 p-0 overflow-hidden;
  border: 1px solid var(--border-light);
}
.tool-approval-header {
  @apply flex items-center gap-3 px-5 py-4;
  background: var(--color-warning-bg);
  border-bottom: 1px solid var(--color-warning-border);
}
.tool-approval-header i { color: var(--color-warning); font-size: 1.25rem; }
.tool-approval-header h3 { @apply text-sm font-semibold; color: var(--text-primary); margin: var(--spacing-0); }
.tool-approval-body { @apply flex flex-col gap-3 px-5 py-4; }
.tool-approval-row { @apply flex flex-col gap-1; }
.tool-approval-label { @apply text-xs font-medium; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.05em; }
.tool-approval-value { @apply text-sm; color: var(--text-primary); }
.tool-approval-value code { @apply font-mono text-xs px-2 py-0.5 rounded; background: var(--bg-tertiary); }
.tool-approval-args { @apply text-xs font-mono p-2 rounded overflow-auto max-h-32; background: var(--bg-tertiary); color: var(--text-primary); margin: var(--spacing-0); }
.risk-low    { color: var(--color-success); font-weight: 600; }
.risk-medium { color: var(--color-warning); font-weight: 600; }
.risk-high   { color: var(--color-error); font-weight: 600; }
.risk-critical { color: var(--color-error-hover); font-weight: 700; }
.tool-approval-footer { @apply flex items-center justify-end gap-3 px-5 py-4; border-top: 1px solid var(--border-subtle); }
.tool-approval-btn { @apply flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors; }
.tool-approval-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.tool-approval-btn--deny { background: var(--color-error-bg); color: var(--color-error); border: 1px solid var(--color-error-border); }
.tool-approval-btn--deny:hover:not(:disabled) { background: var(--color-error); color: #fff; }
.tool-approval-btn--approve { background: var(--color-success-bg); color: var(--color-success); border: 1px solid var(--color-success-border); }
.tool-approval-btn--approve:hover:not(:disabled) { background: var(--color-success); color: #fff; }
/* Issue #4960: countdown timer */
.tool-approval-countdown { @apply flex flex-col gap-1 pt-1; }
.tool-approval-countdown-bar-track { @apply w-full rounded-full overflow-hidden; height: 4px; background: var(--bg-tertiary); }
.tool-approval-countdown-bar-fill { height: 4px; border-radius: 9999px; background: var(--color-warning); transition: width 1s linear, background 0.3s ease; }
.tool-approval-countdown-bar-fill--urgent { background: var(--color-error); }
.tool-approval-countdown-label { @apply text-xs; color: var(--text-tertiary); }
</style>
