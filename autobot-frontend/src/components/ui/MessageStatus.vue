<template>
  <div class="message-status" :class="statusClass" :title="statusTooltip">
    <div class="status-icon">
      <LoadingSpinner
        v-if="status === 'sending'"
        variant="dots"
        size="xs"
        :animated="true"
      />
      <Icon v-else-if="status === 'sent'" name="check" size="xs" />
      <Icon v-else-if="status === 'delivered'" name="check-circle" size="xs" />
      <Icon v-else-if="status === 'failed'" name="exclamation-triangle" size="xs" />
      <Icon v-else-if="status === 'queued'" name="clock" size="xs" />
      <Icon v-else-if="status === 'read'" name="eye" size="xs" />
      <Icon v-else-if="status === 'retrying'" name="redo" size="xs" :spin="true" />
    </div>

    <span v-if="showText" class="status-text">{{ statusText }}</span>

    <button
      v-if="status === 'failed' && allowRetry"
      @click="$emit('retry')"
      class="retry-button"
      :title="t('ui.messageStatus.retrySending')"
    >
      <Icon name="redo" size="xs" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '@/components/ui/Icon.vue'
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

const { t } = useI18n()

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
  const texts: Record<string, string> = {
    sending: t('ui.messageStatus.sending'),
    sent: t('ui.messageStatus.sent'),
    delivered: t('ui.messageStatus.delivered'),
    read: t('ui.messageStatus.read'),
    failed: t('ui.messageStatus.failed'),
    queued: t('ui.messageStatus.queued'),
    retrying: t('ui.messageStatus.retrying')
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
    return t('ui.messageStatus.statusAtTime', { status: baseTooltip, time: timeString })
  }

  if (props.error && props.status === 'failed') {
    return `${baseTooltip}: ${props.error}`
  }

  return baseTooltip
})
</script>

<style scoped>
@reference "../../assets/tailwind.css";
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
  @apply ml-1 p-0.5 rounded hover:bg-autobot-bg-secondary transition-colors;
}

/* Status-specific styles */
.status-sending {
  color: var(--color-info);
}

.status-sent {
  @apply text-autobot-text-muted;
}

.status-delivered {
  color: var(--color-success);
}

.status-read {
  color: var(--color-success);
}

.status-failed {
  color: var(--color-error);
}

.status-queued {
  color: var(--color-warning);
}

.status-retrying {
  color: var(--color-info);
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
  @apply outline-hidden ring-2 ring-blue-500 ring-offset-1;
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
