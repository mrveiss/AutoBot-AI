<template>
  <div class="message-wrapper" :class="messageWrapperClass">
    <!-- Message Header -->
    <div class="message-header">
      <div class="flex items-center gap-1.5">
        <div class="message-avatar" :class="avatarClass">
          <i :class="senderIcon" aria-hidden="true"></i>
        </div>
        <div class="message-info">
          <span class="sender-name">
            {{ senderName }}
            <span v-if="message.sender === 'assistant' && message.metadata?.model" class="model-name">
              ({{ message.metadata.model }})
            </span>
          </span>
          <span class="message-time">{{ formatTime(message.timestamp) }}</span>
        </div>
      </div>

      <div class="message-actions">
        <BaseButton
          v-if="message.sender === 'user'"
          variant="ghost"
          size="xs"
          @click="$emit('edit', message)"
          class="action-btn"
          aria-label="Edit message"
          title="Edit message"
        >
          <i class="fas fa-edit" aria-hidden="true"></i>
        </BaseButton>
        <BaseButton
          variant="ghost"
          size="xs"
          @click="$emit('copy', message)"
          class="action-btn"
          aria-label="Copy message"
          title="Copy message"
        >
          <i class="fas fa-copy" aria-hidden="true"></i>
        </BaseButton>
        <BaseButton
          variant="ghost"
          size="xs"
          @click="$emit('delete', message)"
          class="action-btn danger"
          aria-label="Delete message"
          title="Delete message"
        >
          <i class="fas fa-trash" aria-hidden="true"></i>
        </BaseButton>
      </div>
    </div>

    <!-- Enhanced Message Status -->
    <div v-if="message.sender === 'user'" class="message-status-container">
      <MessageStatus
        :status="(message.status === 'error' ? 'failed' : message.status) || 'sent'"
        :show-text="true"
        :timestamp="message.timestamp"
        :error="message.error"
        @retry="$emit('retry', message.id)"
      />
    </div>

    <!-- Message Content -->
    <div class="message-content" :class="contentClass">
      <!-- Streaming content with typing indicator -->
      <div v-if="isStreaming" class="streaming-content">
        <div class="message-text" v-html="formattedContent"></div>
        <div v-if="isTyping && isLast" class="typing-indicator">
          <div class="typing-dots">
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>
      </div>

      <!-- Regular message content -->
      <div v-else class="message-text" v-html="formattedContent"></div>

      <!-- Message Metadata -->
      <div v-if="showMetadata" class="message-metadata">
        <div class="metadata-items">
          <span v-if="message.metadata?.model" class="metadata-item">
            <i class="fas fa-robot" aria-hidden="true"></i>
            {{ message.metadata.model }}
          </span>
          <span v-if="message.metadata?.tokens" class="metadata-item">
            <i class="fas fa-coins" aria-hidden="true"></i>
            {{ message.metadata.tokens }} tokens
          </span>
          <span v-if="message.metadata?.duration" class="metadata-item">
            <i class="fas fa-clock" aria-hidden="true"></i>
            {{ message.metadata.duration }}ms
          </span>
        </div>
      </div>

      <!-- Issue #249: Knowledge Base Citations Display -->
      <CitationsDisplay
        v-if="hasCitations"
        :citations="message.metadata?.citations || []"
        :initially-expanded="citationsExpanded"
        @citation-click="$emit('citation-click', $event)"
        @expanded-change="$emit('citations-expanded-change', { messageId: message.id, expanded: $event })"
      />

      <!-- Attachments -->
      <MessageAttachments
        v-if="hasAttachments"
        :attachments="message.attachments || []"
        @view="$emit('view-attachment', $event)"
        @download="$emit('download-attachment', $event)"
      />

      <!-- Code blocks placeholder -->
      <div v-if="hasCodeBlocks" class="code-blocks">
        <!-- Rendered by formattedContent -->
      </div>

      <!-- Command Approval Request UI -->
      <ApprovalRequestCard
        v-if="hasApprovalRequest"
        :status="message.metadata?.approval_status"
        :requires-approval="message.metadata?.requires_approval"
        :command="message.metadata?.command"
        :comment="message.metadata?.approval_comment"
        :risk-level="message.metadata?.risk_level"
        :purpose="message.metadata?.purpose"
        :reasons="message.metadata?.reasons"
        :is-interactive="message.metadata?.is_interactive"
        :interactive-reasons="message.metadata?.interactive_reasons"
        :processing="processingApproval"
        :session-id="message.metadata?.terminal_session_id"
        @approve="$emit('approve', $event)"
        @deny="$emit('deny', $event)"
        @auto-approve-changed="$emit('auto-approve-changed', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Message Item Component
 *
 * Renders an individual chat message with all its features.
 * Extracted from ChatMessages.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */

import { computed } from 'vue'
import type { ChatMessage } from '@/stores/useChatStore'
import { formatTime } from '@/utils/formatHelpers'
import MessageStatus from '@/components/ui/MessageStatus.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import ApprovalRequestCard from './ApprovalRequestCard.vue'
import CitationsDisplay from './CitationsDisplay.vue'
import MessageAttachments from './MessageAttachments.vue'

interface Props {
  message: ChatMessage
  isTyping?: boolean
  isLast?: boolean
  showJson?: boolean
  citationsExpanded?: boolean
  processingApproval?: boolean
}

interface Emits {
  (e: 'edit', message: ChatMessage): void
  (e: 'copy', message: ChatMessage): void
  (e: 'delete', message: ChatMessage): void
  (e: 'retry', messageId: string): void
  (e: 'citation-click', citation: unknown): void
  (e: 'citations-expanded-change', data: { messageId: string; expanded: boolean }): void
  (e: 'view-attachment', attachment: unknown): void
  (e: 'download-attachment', attachment: unknown): void
  (e: 'approve', data: unknown): void
  (e: 'deny', data: unknown): void
  (e: 'auto-approve-changed', value: boolean): void
}

const props = withDefaults(defineProps<Props>(), {
  isTyping: false,
  isLast: false,
  showJson: false,
  citationsExpanded: false,
  processingApproval: false
})

defineEmits<Emits>()

// Computed properties
const messageWrapperClass = computed(() => {
  const classes = ['message']
  classes.push(`${props.message.sender}-message`)
  if (props.message.status === 'error') classes.push('error')
  if (props.message.status === 'sending') classes.push('sending')
  return classes.join(' ')
})

const avatarClass = computed(() => `message-avatar ${props.message.sender}`)

const senderIcon = computed(() => {
  const icons: Record<string, string> = {
    user: 'fas fa-user',
    assistant: 'fas fa-robot',
    system: 'fas fa-cog',
    error: 'fas fa-exclamation-triangle',
    thought: 'fas fa-brain',
    'tool-code': 'fas fa-code',
    'tool-output': 'fas fa-terminal'
  }
  return icons[props.message.sender] || 'fas fa-comment'
})

const senderName = computed(() => {
  const names: Record<string, string> = {
    user: 'You',
    assistant: 'AI Assistant',
    system: 'System',
    error: 'Error',
    thought: 'AI Thought',
    'tool-code': 'Code Execution',
    'tool-output': 'Output'
  }
  return names[props.message.sender] || props.message.sender
})

const contentClass = computed(() => {
  const classes = ['message-content']
  if (props.message.sender === 'user') classes.push('user-content')
  if (props.message.sender === 'assistant') classes.push('assistant-content')
  if (props.message.sender === 'system') classes.push('system-content')
  return classes.join(' ')
})

const isStreaming = computed(() => {
  return props.message.sender === 'assistant' && props.isTyping && props.isLast
})

const showMetadata = computed(() => {
  return (
    props.showJson &&
    props.message.sender === 'assistant' &&
    props.message.metadata &&
    Object.keys(props.message.metadata).length > 0
  )
})

const hasCitations = computed(() => {
  return (
    props.message.sender === 'assistant' &&
    (props.message.metadata?.citations?.length || 0) > 0
  )
})

const hasAttachments = computed(() => {
  return (props.message.attachments?.length || 0) > 0
})

const hasCodeBlocks = computed(() => {
  return /```[\s\S]*?```/.test(props.message.content)
})

const hasApprovalRequest = computed(() => {
  return props.message.metadata?.approval_status || props.message.metadata?.requires_approval
})

const formattedContent = computed(() => {
  let content = props.message.content

  // Strip ANSI escape codes
  content = content
    .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')
    .replace(/\x1b\][0-9;]*[^\x07]*\x07/g, '')
    .replace(/\x1b\][0-9;]*[^\x07\x1b]*(?:\x1b\\)?/g, '')
    .replace(/\x1b[=>]/g, '')
    .replace(/\x1b[()][AB012]/g, '')
    .replace(/\[[?\d;]*[hlHJ]/g, '')
    .replace(/\]0;[^\x07\n]*\x07?/g, '')
    .trim()

  // Strip TOOL_CALL tags
  content = content.replace(/<tool_call[^>]*>.*?<\/tool_call>/gs, '')

  // Process code blocks
  content = content.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
    return `<pre class="code-block${lang ? ` language-${lang}` : ''}"><code>${code.trim()}</code></pre>`
  })

  // Basic markdown formatting
  content = content
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')

  // Links
  content = content.replace(
    /(https?:\/\/[^\s]+)/g,
    '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
  )

  return content
})
</script>

<style scoped>
.message-wrapper {
  @apply rounded-lg shadow-sm border transition-all duration-200;
  max-width: 85%;
  padding: 6px 10px;
  animation: slideInFromBottom 0.25s ease-out;
}

.message-wrapper:hover {
  @apply shadow-md;
}

/* USER MESSAGES - Right side, blue theme */
.message-wrapper.user-message {
  @apply bg-blue-600 text-white border-blue-700 ml-auto mr-0;
  border-radius: 18px 18px 4px 18px;
}

.message-wrapper.user-message .sender-name,
.message-wrapper.user-message .message-time {
  @apply text-blue-100;
}

.message-wrapper.user-message .message-content {
  @apply text-white;
}

/* ASSISTANT MESSAGES - Left side, gray theme */
.message-wrapper.assistant-message {
  @apply bg-autobot-bg-secondary text-autobot-text-primary border-autobot-border mr-auto ml-0;
  border-radius: 18px 18px 18px 4px;
}

.message-wrapper.assistant-message .sender-name {
  @apply text-autobot-text-primary;
}

.message-wrapper.assistant-message .message-time {
  @apply text-autobot-text-secondary;
}

.message-wrapper.assistant-message .message-content {
  @apply text-autobot-text-primary;
}

/* SYSTEM MESSAGES - Centered, subtle */
.message-wrapper.system-message {
  @apply bg-autobot-bg-tertiary border-autobot-border mx-auto text-autobot-text-secondary;
  max-width: 70%;
  border-radius: 12px;
}

.message-wrapper.error {
  @apply bg-red-50 border-red-300 text-red-900;
}

.message-wrapper.sending {
  @apply opacity-70;
}

.message-header {
  @apply flex items-start justify-between mb-1;
}

.message-avatar {
  @apply w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-semibold;
}

.message-avatar.user {
  @apply bg-blue-700;
}

.message-avatar.assistant {
  @apply bg-autobot-bg-tertiary;
}

.message-avatar.system {
  @apply bg-autobot-text-muted;
}

.message-info {
  @apply flex flex-col ml-1.5;
}

.sender-name {
  @apply font-semibold text-xs;
}

.model-name {
  @apply font-normal text-xs opacity-80 ml-1;
}

.message-time {
  @apply text-xs leading-tight;
}

.message-actions {
  @apply flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity;
}

.message-status-container {
  @apply mt-1.5 flex justify-end;
}

.message-content {
  @apply leading-snug text-sm;
}

.message-text {
  @apply break-words;
  line-height: 1.4;
}

/* User message code styling */
.user-message .message-text :deep(code) {
  @apply bg-blue-500 text-blue-50 px-1.5 py-0.5 rounded text-xs font-mono;
}

.user-message .message-text :deep(pre) {
  @apply bg-blue-800 text-blue-50 p-3 rounded-lg overflow-x-auto my-1.5;
}

.user-message .message-text :deep(a) {
  @apply text-blue-100 hover:text-white underline;
}

/* Assistant message code styling */
.assistant-message .message-text :deep(code) {
  @apply bg-gray-200 text-gray-800 px-1.5 py-0.5 rounded text-xs font-mono;
}

.assistant-message .message-text :deep(pre) {
  @apply bg-gray-800 text-gray-100 p-3 rounded-lg overflow-x-auto my-1.5;
}

.assistant-message .message-text :deep(a) {
  @apply text-blue-600 hover:text-blue-800 underline;
}

/* Metadata */
.user-message .message-metadata {
  @apply mt-1.5 pt-1 border-t border-blue-400;
}

.user-message .metadata-items {
  @apply flex flex-wrap gap-1.5 text-xs text-blue-100;
}

.assistant-message .message-metadata {
  @apply mt-1.5 pt-1 border-t border-autobot-border;
}

.assistant-message .metadata-items {
  @apply flex flex-wrap gap-1.5 text-xs text-autobot-text-secondary;
}

.metadata-item {
  @apply flex items-center gap-1;
}

.streaming-content {
  @apply space-y-1.5;
}

.typing-indicator {
  @apply flex items-center gap-1.5;
}

.typing-dots {
  @apply flex gap-1;
}

.typing-dots span {
  @apply w-1.5 h-1.5 bg-autobot-text-muted rounded-full animate-pulse;
  animation-delay: calc(var(--index) * 0.2s);
}

.typing-dots span:nth-child(1) {
  --index: 0;
}
.typing-dots span:nth-child(2) {
  --index: 1;
}
.typing-dots span:nth-child(3) {
  --index: 2;
}

@keyframes slideInFromBottom {
  from {
    opacity: 0;
    transform: translateY(15px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Responsive adjustments */
@media (max-width: 768px) {
  .message-wrapper.user-message {
    @apply ml-1 mr-0.5;
  }

  .message-wrapper.assistant-message {
    @apply mr-1 ml-0.5;
  }

  .message-wrapper.system-message {
    @apply mx-0.5;
  }

  .message-avatar {
    @apply w-5 h-5 text-xs;
  }

  .sender-name {
    @apply text-xs;
  }

  .message-time {
    @apply text-xs;
  }
}
</style>
