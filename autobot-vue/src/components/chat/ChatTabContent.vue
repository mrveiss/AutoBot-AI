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

    <!-- noVNC Tab Content -->
    <div v-else-if="activeTab === 'novnc'" class="flex-1 flex flex-col min-h-0">
      <div class="flex-1 flex flex-col bg-black">
        <div class="flex justify-between items-center bg-gray-800 text-white px-4 py-2 text-sm">
          <span>
            <i class="fas fa-desktop mr-2"></i>
            Remote Desktop (Chat Session: {{ currentSessionId?.slice(-8) || 'N/A' }})
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
          :key="`desktop-${currentSessionId}`"
          :src="novncUrl"
          class="flex-1 w-full border-0"
          title="noVNC Remote Desktop"
          allowfullscreen
        ></iframe>
      </div>
    </div>

    <!-- Persisted Terminal Component - rendered outside conditional chain to preserve state -->
    <div
      v-if="terminalMounted"
      v-show="activeTab === 'terminal'"
      class="absolute inset-0 flex flex-col min-h-0"
    >
      <ChatTerminal
        :key="currentSessionId || 'terminal'"
        :chat-session-id="currentSessionId"
        :auto-connect="true"
        :allow-user-takeover="true"
        class="flex-1"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ChatTabContent')

// Component imports
import ChatMessages from './ChatMessages.vue'
import ChatInput from './ChatInput.vue'
import FileBrowser from '@/components/FileBrowser.vue'
import ChatBrowser from '@/components/ChatBrowser.vue'  // Issue #73: Browser sessions tied to chat
import ChatTerminal from '@/components/ChatTerminal.vue'

interface Props {
  activeTab: string
  currentSessionId: string | null
  novncUrl: string
}

const props = defineProps<Props>()

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

// Define emits to propagate tool call events to parent
const emit = defineEmits<{
  'tool-call-detected': [toolCall: {
    command: string
    host: string
    purpose: string
    params: Record<string, any>
  }]
}>()

// Handler for tool call detection from ChatMessages
const handleToolCallDetected = (toolCall: any) => {
  logger.info('Propagating TOOL_CALL to ChatInterface:', toolCall)
  emit('tool-call-detected', toolCall)
}
</script>

<style scoped>
/* Content styling handled by child components */
</style>
