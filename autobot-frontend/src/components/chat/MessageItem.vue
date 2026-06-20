<template>
  <div class="message-wrapper" :class="messageWrapperClass">
    <!-- Message Header -->
    <div class="message-header">
      <div class="flex items-center gap-1.5">
        <div class="message-avatar" :class="avatarClass">
          <Icon :name="senderIcon" />
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
          :aria-label="$t('chat.message.edit')"
          :title="$t('chat.message.edit')"
        >
          <Icon name="edit" />
        </BaseButton>
        <BaseButton
          variant="ghost"
          size="xs"
          @click="$emit('copy', message)"
          class="action-btn"
          :aria-label="$t('chat.message.copy')"
          :title="$t('chat.message.copy')"
        >
          <Icon name="copy" />
        </BaseButton>
        <!-- Issue #3245: Save assistant response as a persistent AI document -->
        <BaseButton
          v-if="message.sender === 'assistant'"
          variant="ghost"
          size="xs"
          :disabled="isSavingDocument"
          class="action-btn"
          aria-label="Save as document"
          title="Save as document"
          @click="handleSaveAsDocument"
        >
          <Icon name="file-alt" />
        </BaseButton>
        <BaseButton
          variant="ghost"
          size="xs"
          @click="$emit('delete', message)"
          class="action-btn danger"
          :aria-label="$t('chat.message.delete')"
          :title="$t('chat.message.delete')"
        >
          <Icon name="trash" />
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
        <!-- Issue #9479: intercept entity-anchor clicks for in-app navigation -->
        <div class="message-text" v-html="formattedContent" @click="handleContentClick"></div>
        <div v-if="isTyping && isLast" class="typing-indicator">
          <div class="typing-dots">
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>
      </div>

      <!-- Regular message content -->
      <!-- Issue #9479: intercept entity-anchor clicks for in-app navigation -->
      <div v-else class="message-text" v-html="formattedContent" @click="handleContentClick"></div>

      <!-- Message Metadata -->
      <div v-if="showMetadata" class="message-metadata">
        <div class="metadata-items">
          <span v-if="message.metadata?.model" class="metadata-item">
            <Icon name="robot" />
            {{ message.metadata.model }}
          </span>
          <span v-if="message.metadata?.tokens" class="metadata-item">
            <Icon name="dollar-sign" />
            {{ $t('chat.message.tokens', { count: message.metadata.tokens }) }}
          </span>
          <span v-if="message.metadata?.duration" class="metadata-item">
            <Icon name="clock" />
            {{ message.metadata.duration }}ms
          </span>
          <span
            v-if="message.thinking_metadata?.used"
            class="metadata-item thinking-badge"
            :title="$t('chat.message.thinking.tooltip')"
          >
            {{ $t('chat.message.thinking.badge', { count: message.thinking_metadata.tokens_used || 0 }) }}
          </span>
        </div>
      </div>

      <!-- Issue #249: Knowledge Base Citations Display -->
      <CitationsDisplay
        v-if="hasCitations"
        :citations="(message.metadata as any)?.citations || []"
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
        :status="(message.metadata as any)?.approval_status"
        :requires-approval="(message.metadata as any)?.requires_approval"
        :command="(message.metadata as any)?.command"
        :comment="(message.metadata as any)?.approval_comment"
        :risk-level="(message.metadata as any)?.risk_level"
        :purpose="(message.metadata as any)?.purpose"
        :reasons="(message.metadata as any)?.reasons"
        :is-interactive="(message.metadata as any)?.is_interactive"
        :interactive-reasons="(message.metadata as any)?.interactive_reasons"
        :processing="processingApproval"
        :session-id="(message.metadata as any)?.terminal_session_id"
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

import type { IconName } from '@/components/ui/Icon.vue'
import Icon from '@/components/ui/Icon.vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import type { ChatMessage } from '@/stores/useChatStore'
import { formatTime } from '@/utils/formatHelpers'

const { t } = useI18n()
import MessageStatus from '@/components/ui/MessageStatus.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import ApprovalRequestCard from './ApprovalRequestCard.vue'
import CitationsDisplay from './CitationsDisplay.vue'
import MessageAttachments from './MessageAttachments.vue'
import { sanitizeChatHtml } from '@/utils/sanitize'
import { useAIDocument } from '@/composables/useAIDocument'
import {
  createEntityAnchorClickHandler,
  renderMarkdownLinks,
} from '@/composables/chat/useEntityAnchors'

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
  /** Issue #3245: emitted after an assistant message is saved as an AI document */
  (e: 'save-as-document', docId: string): void
}

const props = withDefaults(defineProps<Props>(), {
  isTyping: false,
  isLast: false,
  showJson: false,
  citationsExpanded: false,
  processingApproval: false
})

const emit = defineEmits<Emits>()

// Issue #9479: route entity anchors (`[Name](#kind-id)`) to the right view
const router = useRouter()
const handleContentClick = createEntityAnchorClickHandler(router)

// Issue #3245: Save-as-document integration
const { saveMessageAsDocument } = useAIDocument()
const isSavingDocument = ref(false)

async function handleSaveAsDocument() {
  if (isSavingDocument.value) return
  isSavingDocument.value = true
  try {
    const doc = await saveMessageAsDocument({
      content: props.message.content,
      messageId: props.message.id,
    })
    emit('save-as-document', doc.id)
  } finally {
    isSavingDocument.value = false
  }
}

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
  const icons: Record<string, IconName> = {
    user: 'user',
    assistant: 'robot',
    system: 'cog',
    error: 'exclamation-triangle',
    thought: 'brain',
    'tool-code': 'code',
    'tool-output': 'terminal'
  }
  return icons[props.message.sender] || 'comment'
})

const senderName = computed(() => {
  const key = `chat.message.sender.${props.message.sender}`
  const translated = t(key, props.message.sender)
  return translated !== key ? translated : props.message.sender
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
    ((props.message.metadata as any)?.citations?.length || 0) > 0
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
    .replace(/\u001b\[[0-9;]*[a-zA-Z]/g, '')
    .replace(/\u001b\][0-9;]*[^\u0007]*\u0007/g, '')
    .replace(/\u001b\][0-9;]*[^\u0007\u001b]*(?:\u001b\\)?/g, '')
    .replace(/\u001b[=>]/g, '')
    .replace(/\u001b[()][AB012]/g, '')
    .replace(/\[[?\d;]*[hlHJ]/g, '')
    .replace(/\]0;[^\u0007\n]*\u0007?/g, '')
    .trim()

  // Strip TOOL_CALL tags
  content = content.replace(/<tool_call[^>]*>.*?<\/tool_call>/gs, '')

  // Process code blocks
  content = content.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
    return `<pre class="code-block${lang ? ` language-${lang}` : ''}"><code>${code.trim()}</code></pre>`
  })

  // Issue #9479: render `[text](href)` markdown links — including entity
  // anchors (`#kind-id`) — into <a> before inline formatting so they become
  // clickable. Output is sanitized by sanitizeChatHtml below.
  content = renderMarkdownLinks(content)

  // Basic markdown formatting
  content = content
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')

  // Bare URLs — skip URLs already inside an anchor href (rendered above)
  content = content.replace(
    /(?<!href=")(https?:\/\/[^\s<]+)/g,
    '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
  )

  return sanitizeChatHtml(content)
})
</script>

<style scoped src="@/design-system/styles/chat-message-shared.css"></style>

<style scoped>
@reference "../../assets/tailwind.css";

.message-wrapper {
  @apply rounded-lg shadow-sm border transition-all duration-200;
  max-width: 85%;
  padding: var(--spacing-1-5) var(--spacing-2-5);
  animation: slideInFromBottom 0.25s ease-out;
}

.message-wrapper.user-message .message-content {
  @apply text-white;
}

/* ASSISTANT MESSAGES - Left side, gray theme */
.message-wrapper.assistant-message {
  @apply bg-autobot-bg-secondary text-autobot-text-primary border-autobot-border mr-auto ml-0;
  border-radius: 18px 18px 18px 4px;
}

.message-wrapper.error {
  background: var(--color-error-bg);
  border-color: var(--color-error-border);
  color: var(--color-error);
}

.message-avatar.assistant {
  @apply bg-autobot-bg-tertiary;
}

.message-avatar.system {
  @apply bg-autobot-text-muted;
}

.message-status-container {
  @apply mt-1.5 flex justify-end;
}

/* User message code styling */
.user-message .message-text :deep(code) {
  @apply px-1.5 py-0.5 rounded text-xs font-mono;
  background: rgba(0, 0, 0, 0.2);
  color: var(--text-inverse);
}

/* Assistant message code styling */
.assistant-message .message-text :deep(code) {
  @apply bg-autobot-bg-tertiary text-autobot-text-primary px-1.5 py-0.5 rounded text-xs font-mono;
}

.assistant-message .message-text :deep(a) {
  @apply text-autobot-text-link hover:text-autobot-text-link underline;
  opacity: 0.9;
}

.assistant-message .message-text :deep(a):hover {
  opacity: 1;
}

/* Metadata */
.user-message .message-metadata {
  @apply mt-1.5 pt-1 border-t;
  border-color: rgba(255, 255, 255, 0.3);
}

.assistant-message .message-metadata {
  @apply mt-1.5 pt-1 border-t border-autobot-border;
}

.metadata-item.thinking-badge {
  @apply font-semibold;
  color: var(--color-primary);
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

/* RTL layout support (#1337) */
:global([dir="rtl"]) .message-wrapper.user-message {
  margin-left: var(--spacing-0);
  margin-right: auto;
  border-radius: 18px 18px 18px 4px;
}

:global([dir="rtl"]) .message-wrapper.assistant-message {
  margin-right: var(--spacing-0);
  margin-left: auto;
  border-radius: 18px 18px 4px 18px;
}

:global([dir="rtl"]) .message-info {
  margin-left: var(--spacing-0);
  margin-right: var(--spacing-1-5);
}

:global([dir="rtl"]) .message-status-container {
  justify-content: flex-start;
}

/* Code blocks stay LTR inside RTL (#1337) */
:global([dir="rtl"]) .message-text :deep(pre),
:global([dir="rtl"]) .message-text :deep(code) {
  direction: ltr;
  unicode-bidi: isolate;
  text-align: left;
}

@media (max-width: 768px) {
  :global([dir="rtl"]) .message-wrapper.user-message {
    margin-left: var(--spacing-0);
    margin-right: var(--spacing-0-5);
  }

  :global([dir="rtl"]) .message-wrapper.assistant-message {
    margin-right: var(--spacing-0);
    margin-left: var(--spacing-0-5);
  }
}
</style>
