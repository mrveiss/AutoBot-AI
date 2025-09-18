<template>
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
</style>