<template>
  <div class="message-status" :class="statusClass" :title="statusTooltip">
    <div class="status-icon">
      <LoadingSpinner 
        v-if="status === 'sending'" 
        variant="dots" 
        size="xs" 
        :animated="true"
      />
      <CheckIcon v-else-if="status === 'sent'" class="h-3 w-3" />
      <CheckCircleIcon v-else-if="status === 'delivered'" class="h-3 w-3" />
      <ExclamationTriangleIcon v-else-if="status === 'failed'" class="h-3 w-3" />
      <ClockIcon v-else-if="status === 'queued'" class="h-3 w-3" />
      <EyeIcon v-else-if="status === 'read'" class="h-3 w-3" />
      <ArrowPathIcon v-else-if="status === 'retrying'" class="h-3 w-3 animate-spin" />
    </div>
    
    <span v-if="showText" class="status-text">{{ statusText }}</span>
    
    <button 
      v-if="status === 'failed' && allowRetry" 
      @click="$emit('retry')"
      class="retry-button"
      title="Retry sending message"
    >
      <ArrowPathIcon class="h-3 w-3" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  CheckIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  ClockIcon,
  EyeIcon,
  ArrowPathIcon
} from '@heroicons/vue/24/outline'
import LoadingSpinner from './LoadingSpinner.vue'

type MessageStatus = 'sending' | 'sent' | 'delivered' | 'read' | 'failed' | 'queued' | 'retrying'

interface Props {
  status: MessageStatus
  showText?: boolean
  allowRetry?: boolean
  timestamp?: Date | string
  error?: string
}

const props = withDefaults(defineProps<Props>(), {
  showText: false,
  allowRetry: true
})

defineEmits<{
  retry: []
}>()

const statusClass = computed(() => ({
  'status-sending': props.status === 'sending',
  'status-sent': props.status === 'sent',
  'status-delivered': props.status === 'delivered',
  'status-read': props.status === 'read',
  'status-failed': props.status === 'failed',
  'status-queued': props.status === 'queued',
  'status-retrying': props.status === 'retrying'
}))

const statusText = computed(() => {
  const texts = {
    sending: 'Sending...',
    sent: 'Sent',
    delivered: 'Delivered',
    read: 'Read',
    failed: 'Failed',
    queued: 'Queued',
    retrying: 'Retrying...'
  }
  return texts[props.status]
})

const statusTooltip = computed(() => {
  const baseTooltip = statusText.value
  
  if (props.timestamp) {
    const time = typeof props.timestamp === 'string' 
      ? new Date(props.timestamp) 
      : props.timestamp
    const timeString = time.toLocaleTimeString()
    return `${baseTooltip} at ${timeString}`
  }
  
  if (props.error && props.status === 'failed') {
    return `${baseTooltip}: ${props.error}`
  }
  
  return baseTooltip
})
</script>

<style scoped>
.message-status {
  @apply flex items-center gap-1 text-xs transition-all duration-200;
}

.status-icon {
  @apply flex items-center justify-center;
}

.status-text {
  @apply font-medium;
}

.retry-button {
  @apply ml-1 p-0.5 rounded hover:bg-gray-100 transition-colors;
}

/* Status-specific styles */
.status-sending {
  @apply text-blue-500;
}

.status-sent {
  @apply text-gray-400;
}

.status-delivered {
  @apply text-green-500;
}

.status-read {
  @apply text-green-600;
}

.status-failed {
  @apply text-red-500;
}

.status-queued {
  @apply text-yellow-500;
}

.status-retrying {
  @apply text-blue-500;
}

/* Animation for status changes */
.message-status {
  animation: statusFadeIn 0.3s ease-in-out;
}

@keyframes statusFadeIn {
  from {
    opacity: 0;
    transform: scale(0.8);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

/* Pulse animation for active states */
.status-sending .status-icon,
.status-retrying .status-icon {
  animation: statusPulse 2s infinite;
}

@keyframes statusPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* Accessibility improvements */
.retry-button:focus {
  @apply outline-none ring-2 ring-blue-500 ring-offset-1;
}

/* Mobile optimizations */
@media (max-width: 640px) {
  .message-status {
    @apply text-xs;
  }
  
  .status-text {
    @apply hidden;
  }
  
  .retry-button {
    @apply p-1;
  }
}
</style>