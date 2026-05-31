<template>
  <div class="chat-header bg-autobot-bg-card border-b border-autobot-border px-3 sm:px-6 py-3 sm:py-4">
    <div class="flex items-center justify-between gap-2">
      <!-- Left: Mobile sidebar toggle + session info -->
      <div class="flex items-center gap-2 sm:gap-3 min-w-0">
        <!-- Mobile hamburger to open chat sidebar (#1804) -->
        <button
          class="header-btn lg:hidden shrink-0"
          :title="$t('chat.sidebar.expandSidebar')"
          :aria-label="$t('chat.sidebar.expandSidebar')"
          @click="$emit('toggle-mobile-sidebar')"
        >
          <Icon name="bars" />
        </button>

        <div class="w-7 h-7 sm:w-8 sm:h-8 bg-electric-600 rounded-full flex items-center justify-center shrink-0">
          <Icon name="robot" class="text-white text-xs sm:text-sm" />
        </div>
        <div class="min-w-0">
          <h1 class="text-sm sm:text-lg font-semibold text-autobot-text-primary truncate">
            {{ currentSessionTitle }}
          </h1>
          <p class="text-xs sm:text-sm text-autobot-text-muted truncate hidden sm:block">
            {{ sessionInfo }}
          </p>
        </div>
      </div>

      <!-- Right: Actions + connection status -->
      <div class="flex items-center gap-1 sm:gap-2 shrink-0">
        <!-- GH#8990: context window usage indicator (hidden on mobile to save space) -->
        <ContextWindowIndicator
          v-if="contextWindowProps?.hasData"
          class="hidden sm:flex"
          v-bind="contextWindowProps"
        />

        <!-- Custom Actions Slot -->
        <slot name="actions"></slot>

        <!-- Session Actions -->
        <button
          v-if="currentSessionId"
          @click="$emit('export-session')"
          class="header-btn"
          :title="$t('chat.exportChat')"
        >
          <Icon name="download" />
        </button>

        <button
          v-if="currentSessionId"
          @click="$emit('clear-session')"
          class="header-btn"
          :title="$t('chat.clearChat')"
        >
          <Icon name="trash" />
        </button>

        <!-- Connection Status — icon only on mobile, full label on sm+ -->
        <div class="connection-status" :class="connectionStatusClass">
          <Icon :name="connectionStatusIcon" />
          <span class="text-sm hidden sm:inline">{{ connectionStatus }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import ContextWindowIndicator from './ContextWindowIndicator.vue'
import { computed } from 'vue'

interface ContextWindowProps {
  tokensUsed: number
  contextWindow: number
  usagePercent: number
  isWarning: boolean
  isCritical: boolean
  hasData: boolean
}

interface Props {
  currentSessionId: string | null
  currentSessionTitle: string
  sessionInfo: string
  connectionStatus: string
  isConnected: boolean
  contextWindowProps?: ContextWindowProps
}

interface Emits {
  (e: 'export-session'): void
  (e: 'clear-session'): void
  (e: 'toggle-mobile-sidebar'): void
}

const props = defineProps<Props>()
defineEmits<Emits>()

const connectionStatusClass = computed(() => ({
  'text-green-600': props.isConnected,
  'text-red-600': !props.isConnected,
  'text-yellow-600': props.connectionStatus === 'Connecting'
}))

const connectionStatusIcon = computed(() => {
  if (!props.isConnected) return 'exclamation-circle'
  if (props.connectionStatus === 'Connecting') return 'spinner'
  return 'check-circle'
})
</script>

<style scoped>
@reference "../../assets/tailwind.css";
.chat-header {
  @apply flex-shrink-0;
}

.header-btn {
  /* min 44px touch target on mobile (#1804) */
  @apply w-8 h-8 sm:w-8 sm:h-8 flex items-center justify-center rounded-md transition-colors text-autobot-text-secondary hover:bg-autobot-bg-tertiary;
  min-width: 44px;
  min-height: 44px;
}

@media (min-width: 640px) {
  .header-btn {
    min-width: 2rem;
    min-height: 2rem;
  }
}

.connection-status {
  @apply flex items-center gap-1 sm:gap-2 px-2 sm:px-3 py-1.5 rounded-md bg-autobot-bg-tertiary;
}
</style>
