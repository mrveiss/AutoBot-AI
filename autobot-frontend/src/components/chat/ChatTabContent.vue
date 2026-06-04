<template>
  <div class="flex-1 flex flex-col min-h-0 relative overflow-hidden">
    <!-- Chat Tab Content - Content scrolls, input stays sticky -->
    <div v-if="activeTab === 'chat'" class="flex-1 flex flex-col min-h-0">
      <div class="flex-1 min-h-0 overflow-y-auto">
        <!-- Issue #4003: Lazy-load ChatMessages with Suspense fallback for fast initial paint -->
        <Suspense>
          <template #default>
            <ChatMessages @tool-call-detected="handleToolCallDetected" />
          </template>
          <template #fallback>
            <!-- Skeleton loader while ChatMessages is loading -->
            <div class="flex-1 flex flex-col gap-3 p-4 bg-autobot-bg-primary animate-pulse">
              <div class="h-16 bg-autobot-bg-secondary rounded"></div>
              <div class="h-12 bg-autobot-bg-secondary rounded"></div>
              <div class="flex-1 flex flex-col gap-2">
                <div class="h-8 bg-autobot-bg-secondary rounded w-3/4"></div>
                <div class="h-8 bg-autobot-bg-secondary rounded w-full"></div>
                <div class="h-8 bg-autobot-bg-secondary rounded w-5/6"></div>
              </div>
            </div>
          </template>
        </Suspense>
      </div>
      <ChatInput class="shrink-0" @vision-send-to-chat="(p: any) => emit('vision-send-to-chat', p)" />
    </div>

    <!-- Files Tab Content -->
    <div v-else-if="activeTab === 'files'" class="flex-1 flex flex-col min-h-0">
      <FileBrowser
        :key="currentSessionId || 'default'"
        :chat-context="true"
        class="flex-1"
      />
    </div>

    <!-- Terminal Tab Placeholder - actual terminal rendered separately to persist -->
    <div v-else-if="activeTab === 'terminal'" class="flex-1 flex flex-col min-h-0">
      <!-- Placeholder for terminal layout -->
    </div>

    <!-- Browser Tab Content (Issue #1130: screenshot-based visual browser) -->
    <div v-else-if="activeTab === 'browser'" class="flex-1 flex flex-col min-h-0">
      <VisualBrowserPanel class="flex-1" />
    </div>

    <!-- noVNC Tab Content (Issue #715: Dynamic hosts from user config, Issue #4977: DesktopInterface) -->
    <div v-else-if="activeTab === 'novnc'" class="flex-1 flex flex-col min-h-0">
      <div class="flex-1 flex flex-col bg-black">
        <!-- Host selector header for VNC -->
        <div class="vnc-header flex justify-between items-center bg-autobot-bg-secondary text-autobot-text-primary px-4 py-2 text-sm">
          <div class="flex items-center gap-3">
            <Icon name="desktop" />
            <HostSelector
              ref="vncHostSelectorRef"
              v-model="selectedVncHost"
              :chat-id="currentSessionId ?? undefined"
              required-capability="vnc"
              @host-selected="onVncHostSelected"
              @open-secrets-manager="emit('open-secrets-manager')"
            />
          </div>
        </div>
        <!-- VNC content - DesktopInterface when host selected (Issue #4977) -->
        <DesktopInterface
          v-if="selectedVncHost"
          :key="`vnc-${selectedVncHost.id}`"
          :host="selectedVncHost"
          class="flex-1"
        />
        <!-- Empty state when no host selected -->
        <div v-else class="flex-1 flex items-center justify-center text-autobot-text-muted">
          <div class="text-center">
            <Icon name="desktop" class="text-5xl mb-4 opacity-50" />
            <p class="text-lg mb-2">{{ $t('chat.tabContent.selectVncHost') }}</p>
            <p class="text-sm text-autobot-text-muted">
              {{ $t('chat.tabContent.selectVncHostDesc') }}
            </p>
          </div>
        </div>
      </div>
    </div>

    <!-- Persisted Terminal Component with Host Selector (Issue #715: SSH to user hosts) -->
    <div
      v-if="terminalMounted"
      v-show="activeTab === 'terminal'"
      class="absolute inset-0 flex flex-col min-h-0"
    >
      <!-- SSH Host selector header for terminal -->
      <div class="terminal-host-header flex items-center gap-3 px-3 py-2 bg-autobot-bg-secondary border-b border-autobot-border">
        <HostSelector
          ref="sshHostSelectorRef"
          v-model="selectedSshHost"
          :chat-id="currentSessionId ?? undefined"
          required-capability="ssh"
          @host-selected="onSshHostSelected"
          @open-secrets-manager="emit('open-secrets-manager')"
        />
        <span v-if="selectedSshHost" class="text-xs text-autobot-text-muted">
          {{ $t('chat.tabContent.connectedTo', { name: selectedSshHost.name }) }}
        </span>
      </div>
      <!-- SSH Terminal iframe or component -->
      <SSHTerminal
        v-if="selectedSshHost"
        :key="`ssh-${selectedSshHost.id}-${currentSessionId}`"
        :host-id="selectedSshHost.id"
        :chat-session-id="currentSessionId"
        class="flex-1"
      />
      <!-- Empty state when no host selected -->
      <div v-else class="flex-1 flex items-center justify-center bg-autobot-bg-secondary text-autobot-text-muted">
        <div class="text-center">
          <Icon name="terminal" class="text-5xl mb-4 opacity-50" />
          <p class="text-lg mb-2">{{ $t('chat.tabContent.selectSshHost') }}</p>
          <p class="text-sm text-autobot-text-muted">
            {{ $t('chat.tabContent.selectSshHostDesc') }}
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, watch, defineAsyncComponent } from 'vue'
import { useI18n } from 'vue-i18n'
import { createLogger } from '@/utils/debugUtils'

const { t } = useI18n()

const logger = createLogger('ChatTabContent')

// Component imports
// Issue #4003: Lazy-load ChatMessages (2221 lines) to reduce initial parse time
const ChatMessages = defineAsyncComponent(() => import('./ChatMessages.vue'))
import ChatInput from './ChatInput.vue'
import FileBrowser from '@/components/file-browser/FileBrowser.vue'
import VisualBrowserPanel from '@/components/chat/VisualBrowserPanel.vue'  // Issue #1130: screenshot-based browser
import HostSelector from '@/components/ui/HostSelector.vue'  // Issue #715: Dynamic host selection
import SSHTerminal from '@/components/terminal/SSHTerminal.vue'    // Issue #715: SSH terminal component
import DesktopInterface from '@/components/desktop/DesktopInterface.vue'  // Issue #4977: full VNC component

/**
 * Infrastructure host type for SSH/VNC connections.
 * Issue #715: Dynamic host management via secrets.
 */
interface InfrastructureHost {
  id: string
  name: string
  host: string
  ssh_port?: number
  vnc_port?: number
  capabilities?: string[]
}

/** Tool call structure detected from chat messages. */
interface ToolCall {
  command: string
  host: string
  purpose: string
  params: Record<string, unknown>
}

interface Props {
  activeTab: string
  currentSessionId: string | null
  novncUrl: string  // Legacy - kept for backwards compatibility
}

const props = defineProps<Props>()

// Host selection state (Issue #715)
const selectedSshHost = ref<InfrastructureHost | null>(null)
const selectedVncHost = ref<InfrastructureHost | null>(null)
const sshHostSelectorRef = ref<InstanceType<typeof HostSelector>>()
const vncHostSelectorRef = ref<InstanceType<typeof HostSelector>>()

// Host selection handlers
const onSshHostSelected = (host: InfrastructureHost) => {
  logger.info('SSH host selected:', { name: host.name, host: host.host })
  selectedSshHost.value = host
}

const onVncHostSelected = (host: InfrastructureHost) => {
  logger.info('VNC host selected:', { name: host.name, host: host.host })
  selectedVncHost.value = host
}

// Terminal mounting state - only mount terminal when first accessed
const terminalMounted = ref(false)

// CRITICAL FIX: Mount terminal immediately when session exists
// This ensures terminal WebSocket connects BEFORE commands execute
// Previously: terminal only mounted when switching to terminal tab → commands lost
watch(() => props.currentSessionId, (sessionId) => {
  if (sessionId && !terminalMounted.value) {
    logger.info('Session created - mounting terminal immediately:', sessionId)
    terminalMounted.value = true
  }
}, { immediate: true })

// Also watch for terminal tab activation (keeps existing behavior for manual switching)
watch(() => props.activeTab, (newTab) => {
  if (newTab === 'terminal' && !terminalMounted.value) {
    terminalMounted.value = true
  }
}, { immediate: true })

// Define emits to propagate events to parent
const emit = defineEmits<{
  'tool-call-detected': [toolCall: ToolCall]
  'open-secrets-manager': []  // Issue #715: Open secrets manager to add hosts
  'vision-send-to-chat': [payload: {
    filename: string
    intent: string
    question?: string
    result: {
      confidence: number
      processing_time: number
      device_used?: string
      result_data: Record<string, unknown>
    }
  }]  // Issue #1242
}>()

// Handler for tool call detection from ChatMessages
const handleToolCallDetected = (toolCall: ToolCall) => {
  logger.info('Propagating TOOL_CALL to ChatInterface:', toolCall)
  emit('tool-call-detected', toolCall)
}
</script>

<style scoped>
/* Content styling handled by child components */
</style>
