<template>
  <div class="flex-1 flex flex-col min-h-0 h-full">
    <!-- Chat Tab Content - FIXED: Enhanced layout for sticky input -->
    <div v-if="activeTab === 'chat'" class="flex-1 flex flex-col h-full overflow-hidden">
      <ChatMessages class="flex-1 overflow-y-auto min-h-0" />
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

    <!-- Terminal Tab Content -->
    <div v-else-if="activeTab === 'terminal'" class="flex-1 flex flex-col min-h-0">
      <Terminal
        :key="`chat-terminal-${currentSessionId}`"
        :sessionType="'main'"
        :autoConnect="true"
        :chatSessionId="currentSessionId"
        class="flex-1"
      />
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
  </div>
</template>

<script setup lang="ts">
// Component imports
import ChatMessages from './ChatMessages.vue'
import ChatInput from './ChatInput.vue'
import FileBrowser from '@/components/FileBrowser.vue'
import PopoutChromiumBrowser from '@/components/PopoutChromiumBrowser.vue'
import Terminal from '@/components/Terminal.vue'

interface Props {
  activeTab: string
  currentSessionId: string | null
  novncUrl: string
}

defineProps<Props>()
</script>

<style scoped>
/* Content styling handled by child components */
</style>