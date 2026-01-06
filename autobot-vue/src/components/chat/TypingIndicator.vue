<template>
  <div class="message-wrapper assistant-message typing-message">
    <div class="message-header">
      <div class="flex items-center gap-1.5">
        <div class="message-avatar assistant">
          <LoadingSpinner variant="pulse" size="sm" color="#3b82f6" />
        </div>
        <div class="message-info">
          <span class="sender-name">AI Assistant</span>
          <span class="message-time">{{ statusText }}</span>
        </div>
      </div>
    </div>
    <div class="message-content">
      <div class="enhanced-typing-indicator">
        <div class="typing-animation">
          <div class="typing-dots-enhanced">
            <span></span>
            <span></span>
            <span></span>
            <span></span>
          </div>
          <div class="typing-wave"></div>
        </div>
        <div class="typing-status">
          <span class="typing-text">{{ detailText }}</span>
          <span v-if="estimatedTime" class="typing-eta">
            ~{{ estimatedTime }}s
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Typing Indicator Component
 *
 * Displays enhanced AI typing indicator with animated dots and status text.
 * Extracted from ChatMessages.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 * Issue #691: Display actual streaming content instead of placeholder text
 */

import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import LoadingSpinner from '@/components/ui/LoadingSpinner.vue'

interface Props {
  isTyping: boolean
  messageComplexity?: number
  // Issue #691: Streaming preview from actual LLM content
  streamingPreview?: string
}

const props = withDefaults(defineProps<Props>(), {
  isTyping: false,
  messageComplexity: 0,
  streamingPreview: ''
})

// Typing timing state
const typingStartTime = ref<number | null>(null)
const estimatedTime = ref<number | null>(null)
const elapsedTime = ref(0)
let updateInterval: ReturnType<typeof setInterval> | null = null

const statusText = computed(() => {
  if (elapsedTime.value < 2000) return 'Thinking...'
  if (elapsedTime.value < 5000) return 'Processing...'
  if (elapsedTime.value < 10000) return 'Analyzing...'
  return 'Working on it...'
})

const detailText = computed(() => {
  // Issue #691: Display actual streaming content when available
  // This shows real LLM thinking/reasoning instead of hardcoded placeholders
  if (props.streamingPreview && props.streamingPreview.trim()) {
    return props.streamingPreview
  }

  // Fallback to time-based placeholder text when no streaming content yet
  const details = [
    'Understanding your request...',
    'Searching knowledge base...',
    'Formulating response...',
    'Crafting detailed answer...',
    'Reviewing response quality...'
  ]
  const index = Math.min(Math.floor(elapsedTime.value / 2000), details.length - 1)
  return details[index]
})

// Watch typing state to manage timing
watch(() => props.isTyping, (isTyping) => {
  if (isTyping) {
    typingStartTime.value = Date.now()
    elapsedTime.value = 0
    // Estimate response time based on message complexity
    const complexity = Math.min(props.messageComplexity / 100, 10)
    estimatedTime.value = Math.ceil(2 + complexity)

    // Start elapsed time counter
    updateInterval = setInterval(() => {
      if (typingStartTime.value) {
        elapsedTime.value = Date.now() - typingStartTime.value
      }
    }, 500)
  } else {
    typingStartTime.value = null
    estimatedTime.value = null
    elapsedTime.value = 0
    if (updateInterval) {
      clearInterval(updateInterval)
      updateInterval = null
    }
  }
}, { immediate: true })

onUnmounted(() => {
  if (updateInterval) {
    clearInterval(updateInterval)
  }
})
</script>

<style scoped>
.typing-message {
  @apply animate-pulse bg-gray-100 text-gray-900 border-gray-300 mr-auto ml-0 rounded-lg shadow-sm border;
  border-radius: 18px 18px 18px 4px;
  max-width: 85%;
  padding: 6px 10px;
}

.message-header {
  @apply flex items-start justify-between mb-1;
}

.message-avatar {
  @apply w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-semibold;
}

.message-avatar.assistant {
  @apply bg-gray-600;
}

.message-info {
  @apply flex flex-col ml-1.5;
}

.sender-name {
  @apply font-semibold text-xs text-gray-900;
}

.message-time {
  @apply text-xs leading-tight text-gray-600;
}

.message-content {
  @apply leading-snug text-sm text-gray-900;
}

.enhanced-typing-indicator {
  @apply flex flex-col gap-2 p-3;
}

.typing-animation {
  @apply relative;
}

.typing-dots-enhanced {
  @apply flex gap-1.5;
}

.typing-dots-enhanced span {
  @apply w-2.5 h-2.5 bg-blue-500 rounded-full;
  animation: typingBounce 1.4s ease-in-out infinite both;
}

.typing-dots-enhanced span:nth-child(1) { animation-delay: -0.32s; }
.typing-dots-enhanced span:nth-child(2) { animation-delay: -0.16s; }
.typing-dots-enhanced span:nth-child(3) { animation-delay: 0s; }
.typing-dots-enhanced span:nth-child(4) { animation-delay: 0.16s; }

@keyframes typingBounce {
  0%, 80%, 100% {
    transform: scale(0.8);
    opacity: 0.5;
  }
  40% {
    transform: scale(1.2);
    opacity: 1;
  }
}

.typing-wave {
  @apply absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-transparent via-blue-400 to-transparent rounded-full;
  animation: typingWave 2s ease-in-out infinite;
}

@keyframes typingWave {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

.typing-status {
  @apply flex justify-between items-center text-xs;
}

.typing-text {
  @apply text-gray-600;
}

.typing-eta {
  @apply text-blue-600 font-medium;
}
</style>
