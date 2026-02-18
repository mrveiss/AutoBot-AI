<template>
  <div class="flex-1 flex flex-col relative">
    <!-- Chat Tab Content - Content scrolls, input stays sticky -->
    <div v-if="activeTab === 'chat'" class="flex-1 flex flex-col">
      <div class="flex-1">
        <ChatMessages @tool-call-detected="handleToolCallDetected" />
      </div>
      <ChatInput class="flex-shrink-0" />
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

    <!-- Browser Tab Content (Issue #73: Browser sessions tied to chat like terminal) -->
    <div v-else-if="activeTab === 'browser'" class="flex-1 flex flex-col min-h-0">
      <ChatBrowser
        :key="currentSessionId || 'default'"
        :chat-session-id="currentSessionId"
        :auto-connect="true"
        class="flex-1"
      />
    </div>

    <!-- noVNC Tab Content (Issue #715: Dynamic hosts from user config) -->
    <div v-else-if="activeTab === 'novnc'" class="flex-1 flex flex-col min-h-0">
      <div class="flex-1 flex flex-col bg-black">
        <!-- Host selector header for VNC -->
        <div class="vnc-header flex justify-between items-center bg-autobot-bg-secondary text-autobot-text-primary px-4 py-2 text-sm">
          <div class="flex items-center gap-3">
            <i class="fas fa-desktop"></i>
            <HostSelector
              ref="vncHostSelectorRef"
              v-model="selectedVncHost"
              :chat-id="currentSessionId"
              required-capability="vnc"
              @host-selected="onVncHostSelected"
              @open-secrets-manager="emit('open-secrets-manager')"
            />
          </div>
          <a
            v-if="selectedVncHost && dynamicVncUrl"
            :href="dynamicVncUrl"
            target="_blank"
            class="text-autobot-text-muted hover:text-autobot-text-secondary underline"
            title="Open noVNC in new window"
          >
            <i class="fas fa-external-link-alt mr-1"></i>
            Open in New Window
          </a>
        </div>
        <!-- VNC content - show iframe when host selected -->
        <template v-if="selectedVncHost && dynamicVncUrl">
          <iframe
            :key="`vnc-${selectedVncHost.id}`"
            :src="dynamicVncUrl"
            class="flex-1 w-full border-0"
            title="noVNC Remote Desktop"
            allowfullscreen
          ></iframe>
        </template>
        <!-- Empty state when no host selected -->
        <div v-else class="flex-1 flex items-center justify-center text-autobot-text-muted">
          <div class="text-center">
            <i class="fas fa-desktop text-5xl mb-4 opacity-50"></i>
            <p class="text-lg mb-2">Select a VNC Host</p>
            <p class="text-sm text-autobot-text-muted">
              Choose a host with VNC capability from your configured infrastructure hosts.
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
          :chat-id="currentSessionId"
          required-capability="ssh"
          @host-selected="onSshHostSelected"
          @open-secrets-manager="emit('open-secrets-manager')"
        />
        <span v-if="selectedSshHost" class="text-xs text-autobot-text-muted">
          Connected to: {{ selectedSshHost.name }}
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
          <i class="fas fa-terminal text-5xl mb-4 opacity-50"></i>
          <p class="text-lg mb-2">Select an SSH Host</p>
          <p class="text-sm text-autobot-text-muted">
            Choose a host to connect via SSH from your configured infrastructure hosts.
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ChatTabContent')

// Component imports
import ChatMessages from './ChatMessages.vue'
import ChatInput from './ChatInput.vue'
import FileBrowser from '@/components/file-browser/FileBrowser.vue'
import ChatBrowser from '@/components/chat/ChatBrowser.vue'  // Issue #73: Browser sessions tied to chat
import HostSelector from '@/components/ui/HostSelector.vue'  // Issue #715: Dynamic host selection
import SSHTerminal from '@/components/terminal/SSHTerminal.vue'    // Issue #715: SSH terminal component

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

// Dynamic VNC URL based on selected host
const dynamicVncUrl = computed(() => {
  if (!selectedVncHost.value) return null
  const host = selectedVncHost.value
  // noVNC websockify URL format: ws://host:vncport
  // The backend VNC proxy will handle the connection
  return `http://${host.host}:${host.vnc_port || 6080}/vnc.html?autoconnect=true`
})

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
