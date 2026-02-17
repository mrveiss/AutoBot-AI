<template>
  <div class="chat-header bg-autobot-bg-card border-b border-autobot-border px-6 py-4">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 bg-electric-600 rounded-full flex items-center justify-center">
          <i class="fas fa-robot text-white text-sm"></i>
        </div>
        <div>
          <h1 class="text-lg font-semibold text-autobot-text-primary">
            {{ currentSessionTitle }}
          </h1>
          <p class="text-sm text-autobot-text-muted">
            {{ sessionInfo }}
          </p>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <!-- Custom Actions Slot -->
        <slot name="actions"></slot>

        <!-- Session Actions -->
        <button
          v-if="currentSessionId"
          @click="$emit('export-session')"
          class="header-btn"
          title="Export chat"
        >
          <i class="fas fa-download"></i>
        </button>

        <button
          v-if="currentSessionId"
          @click="$emit('clear-session')"
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
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  currentSessionId: string | null
  currentSessionTitle: string
  sessionInfo: string
  connectionStatus: string
  isConnected: boolean
}

interface Emits {
  (e: 'export-session'): void
  (e: 'clear-session'): void
}

const props = defineProps<Props>()
defineEmits<Emits>()

// Computed properties for connection status
const connectionStatusClass = computed(() => ({
  'text-green-600': props.isConnected,
  'text-red-600': !props.isConnected,
  'text-yellow-600': props.connectionStatus === 'Connecting'
}))

const connectionStatusIcon = computed(() => {
  if (!props.isConnected) return 'fas fa-exclamation-circle'
  if (props.connectionStatus === 'Connecting') return 'fas fa-spinner fa-spin'
  return 'fas fa-check-circle'
})
</script>

<style scoped>
.chat-header {
  @apply flex-shrink-0;
}

.header-btn {
  @apply w-8 h-8 flex items-center justify-center rounded-md transition-colors text-autobot-text-secondary hover:bg-autobot-bg-tertiary;
}

.connection-status {
  @apply flex items-center gap-2 px-3 py-1.5 rounded-md bg-autobot-bg-tertiary;
}
</style>
