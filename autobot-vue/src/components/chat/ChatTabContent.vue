<template>
  <div class="flex-1 flex flex-col">
    <!-- Chat Tab Content - Content scrolls, input stays sticky -->
    <div v-if="activeTab === 'chat'" class="flex-1 flex flex-col relative">
      <div class="flex-1">
        <ChatMessages />
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

    <!-- Terminal Tab Content - UPDATED to use ChatTerminal with agent control -->
    <div v-else-if="activeTab === 'terminal'" class="flex-1 flex flex-col min-h-0">
      <ChatTerminal
        :key="`chat-terminal-${currentSessionId}`"
        :chat-session-id="currentSessionId"
        :auto-connect="true"
        :allow-user-takeover="true"
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
import ChatTerminal from '@/components/ChatTerminal.vue'

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
