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
        :key="currentSessionId"
        :chat-context="true"
        class="flex-1"
      />
    </div>

    <!-- Terminal Tab Placeholder - actual terminal rendered separately to persist -->
    <div v-else-if="activeTab === 'terminal'" class="flex-1 flex flex-col min-h-0">
      <!-- Placeholder for terminal layout -->
    </div>

    <!-- Browser Tab Content -->
    <div v-else-if="activeTab === 'browser'" class="flex-1 flex flex-col min-h-0">
      <PopoutChromiumBrowser
        :key="currentSessionId"
        :session-id="currentSessionId || 'chat-browser'"
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

// Component imports
import ChatMessages from './ChatMessages.vue'
import ChatInput from './ChatInput.vue'
import FileBrowser from '@/components/FileBrowser.vue'
import PopoutChromiumBrowser from '@/components/PopoutChromiumBrowser.vue'
import ChatTerminal from '@/components/ChatTerminal.vue'

interface Props {
  activeTab: string
  currentSessionId: string | null
  novncUrl: string
}

const props = defineProps<Props>()

// Terminal mounting state - only mount terminal when first accessed
const terminalMounted = ref(false)

// Watch for terminal tab activation
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
  console.log('[ChatTabContent] Propagating TOOL_CALL to ChatInterface:', toolCall)
  emit('tool-call-detected', toolCall)
}
</script>

<style scoped>
/* Content styling handled by child components */
</style>
