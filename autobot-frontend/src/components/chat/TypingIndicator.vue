<template>
  <div class="typing-message">
    <div class="message-header">
      <div class="message-ident">
        <div class="message-avatar assistant">
          <BaseSpinner size="sm" />
        </div>
        <div class="message-info">
          <span class="sender-name">{{ t('chat.typing.aiAssistant') }}</span>
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

import { computed, ref, watch, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseSpinner } from '@autobot/ui'

const { t } = useI18n()

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
  if (elapsedTime.value < 2000) return t('chat.typing.thinking')
  if (elapsedTime.value < 5000) return t('chat.typing.processing')
  if (elapsedTime.value < 10000) return t('chat.typing.analyzing')
  return t('chat.typing.workingOnIt')
})

const detailText = computed(() => {
  // Issue #691: Display actual streaming content when available
  // This shows real LLM thinking/reasoning instead of hardcoded placeholders
  if (props.streamingPreview && props.streamingPreview.trim()) {
    return props.streamingPreview
  }

  // Fallback to time-based placeholder text when no streaming content yet
  const details = [
    t('chat.typing.understanding'),
    t('chat.typing.searching'),
    t('chat.typing.formulating'),
    t('chat.typing.crafting'),
    t('chat.typing.reviewing')
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
  max-inline-size: 85%;
  margin-inline-end: auto;
  padding: var(--aui-space-2) var(--aui-space-3);
  border: 1px solid var(--aui-color-border);
  border-radius: var(--aui-radius-lg);
  background: var(--aui-color-surface-raised);
  color: var(--aui-color-text);
}

.message-header { display: flex; align-items: flex-start; justify-content: space-between; margin-block-end: var(--aui-space-1); }
.message-ident { display: flex; align-items: center; gap: var(--aui-space-2); }
.message-avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  inline-size: var(--aui-space-6);
  block-size: var(--aui-space-6);
  border-radius: var(--aui-radius-full);
  background: var(--aui-color-surface-sunken);
}
.message-info { display: flex; flex-direction: column; }
.sender-name { font-size: var(--aui-text-xs); font-weight: var(--aui-font-weight-semibold); }
.message-time { font-size: var(--aui-text-xs); color: var(--aui-color-text-muted); }
.message-content { font-size: var(--aui-text-sm); }

.enhanced-typing-indicator { display: flex; flex-direction: column; gap: var(--aui-space-2); padding: var(--aui-space-3); }
.typing-animation { position: relative; }
.typing-dots-enhanced { display: flex; gap: var(--aui-space-2); }
.typing-dots-enhanced span {
  inline-size: var(--aui-space-2);
  block-size: var(--aui-space-2);
  border-radius: var(--aui-radius-full);
  background: var(--aui-color-primary);
  animation: typing-bounce 1.4s ease-in-out infinite both;
}
.typing-dots-enhanced span:nth-child(1) { animation-delay: -0.32s; }
.typing-dots-enhanced span:nth-child(2) { animation-delay: -0.16s; }
.typing-dots-enhanced span:nth-child(3) { animation-delay: 0s; }
.typing-dots-enhanced span:nth-child(4) { animation-delay: 0.16s; }

.typing-wave {
  position: absolute;
  inset: 0 0 auto;
  block-size: var(--aui-space-1);
  border-radius: var(--aui-radius-full);
  background: var(--aui-color-primary-hover);
  opacity: 0.6;
  animation: typing-wave 2s ease-in-out infinite;
}
.typing-status { display: flex; align-items: center; justify-content: space-between; font-size: var(--aui-text-xs); }
.typing-text { color: var(--aui-color-text-muted); }
.typing-eta { color: var(--aui-color-primary); font-weight: var(--aui-font-weight-medium); }

@keyframes typing-bounce {
  0%, 80%, 100% { transform: scale(0.8); opacity: 0.5; }
  40% { transform: scale(1.2); opacity: 1; }
}
@keyframes typing-wave {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}
@media (prefers-reduced-motion: reduce) {
  .typing-dots-enhanced span, .typing-wave { animation: none; }
}
</style>
