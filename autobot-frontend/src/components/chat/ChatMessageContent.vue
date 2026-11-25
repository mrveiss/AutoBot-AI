<template>
  <!-- Issue #690: Overseer Agent plan -->
  <OverseerPlanMessage
    v-if="message.type === 'overseer_plan' && message.metadata?.plan"
    class="adv"
    :plan="message.metadata.plan as any"
    :steps="message.metadata?.steps as any"
  />
  <StallQuestionCard v-else-if="message.type === 'human_question'" :message="message" /> <!-- #21022 -->
  <!-- Issue #690: Overseer Agent step -->
  <OverseerStepMessage
    v-else-if="message.type === 'overseer_step' && message.metadata?.step"
    class="adv"
    :step="message.metadata.step as any"
  />
  <!-- GH#9015: AI-generated image -->
  <ImageCell
    v-else-if="isRich('image') && message.metadata?.image_payload"
    :rich-payload="(message.metadata.image_payload as Record<string, unknown>)"
  />
  <!-- GH#9016: AI-generated video -->
  <VideoCell
    v-else-if="isRich('video') && message.metadata?.video_payload"
    :rich-payload="(message.metadata.video_payload as Record<string, unknown>)"
  />

  <!-- MVA-2006: context summary -->
  <div v-else-if="message.type === 'summary' || message.metadata?.is_summary" class="message-content summary-message">
    <div class="summary-header">
      <Icon name="file-alt" />
      <span>{{ $t('chat.contextWindow.summaryTitle') }}</span>
    </div>
    <details class="summary-details">
      <summary class="summary-toggle">{{ $t('chat.contextWindow.summaryToggle') }}</summary>
      <div class="summary-content message-text" v-html="html" @click="handleContentClick"></div>
    </details>
  </div>

  <div v-else :class="contentClass">
    <!-- Streaming content with typing dots -->
    <div v-if="streaming" class="streaming-content">
      <div class="message-text" v-html="html" @click="handleContentClick"></div>
      <div v-if="isTyping && isLast" class="typing-indicator">
        <div class="typing-dots"><span></span><span></span><span></span></div>
      </div>
    </div>
    <div v-else class="message-text" v-html="html" @click="handleContentClick"></div>

    <!-- Mockup: model, tokens and time as one mono line, advanced mode only -->
    <div v-if="message.metadata && showMetadata" class="message-metadata adv">
      <div class="metadata-items">
        <BaseBadge
          v-if="message.sender === 'assistant' && message.metadata.thinking_used"
          variant="warning"
          size="xs"
          :rounded="false"
        >
          <Icon name="brain" />
          {{ $t('chat.messages.thinkingUsed') }}
        </BaseBadge>
        <BaseBadge
          v-if="thinkingMetadata?.used"
          variant="info"
          size="xs"
          :rounded="false"
          :title="$t('chat.message.thinking.tooltip')"
        >
          {{ $t('chat.message.thinking.badge', { count: thinkingMetadata.tokens_used || 0 }) }}
        </BaseBadge>
        <span v-if="model" class="metadata-item">
          <Icon name="robot" />
          {{ model }}
        </span>
        <span v-if="message.metadata.tokens" class="metadata-item">
          <Icon name="dollar-sign" />
          {{ $t('chat.messages.tokens', { count: message.metadata.tokens }) }}
        </span>
        <span v-if="message.metadata.duration" class="metadata-item">
          <Icon name="clock" />
          {{ message.metadata.duration }}ms
        </span>
      </div>
    </div>

    <!-- Issue #10548: model-only claim badge (no KB/graph evidence found) -->
    <BaseBadge v-if="isModelOnlyClaim" variant="warning" size="xs" :title="$t('chat.citations.modelOnlyTooltip')">
      <Icon name="robot" />
      {{ $t('chat.citations.modelOnly') }}
    </BaseBadge>

    <!-- #249, #1186, #4448, #21976: the answer's sources, stored and streamed alike -->
    <CitationsDisplay
      v-if="message.sender === 'assistant' && citations.length > 0"
      :citations="citations"
      :unproven="unprovenValues(message)"
      :partial="proofIsPartial(message)"
      @citation-click="openCitationStep"
    />

    <MessageAttachments
      v-if="message.attachments && message.attachments.length > 0"
      :attachments="message.attachments"
      @view="viewAttachment"
      @download="downloadAttachment"
    />

    <ChatMessageApproval :message="message" />
  </div>
</template>

<script setup lang="ts">
/**
 * The body of one chat message (#18243, step 5a batch 2): the type switch (Overseer plan and
 * step, stall question, image, video, summary) and the regular text with its metadata,
 * citations, attachments and inline approval. Split out of ChatMessages.vue; the branch
 * order is unchanged.
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { BaseBadge, saveUrl } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import CitationsDisplay from '@/components/chat/CitationsDisplay.vue'
import ChatMessageApproval from '@/components/chat/ChatMessageApproval.vue'
import MessageAttachments from '@/components/chat/MessageAttachments.vue'
import OverseerPlanMessage from '@/components/chat/OverseerPlanMessage.vue'
import OverseerStepMessage from '@/components/chat/OverseerStepMessage.vue'
import StallQuestionCard from '@/components/chat/StallQuestionCard.vue'
import ImageCell from '@/components/artifact-cells/ImageCell.vue'
import VideoCell from '@/components/artifact-cells/VideoCell.vue'
import { createEntityAnchorClickHandler } from '@/composables/chat/useEntityAnchors'
import { formatMessageContent } from '@/composables/chat/useChatMessageFormat'
import { sanitizeChatHtml } from '@/utils/sanitize'
import { getContentClass } from '@/composables/chat/useChatMessageView'
import { messageCitations, proofIsPartial, unprovenValues } from '@/utils/messageCitations'
import { shownModel } from '@/utils/internalMessage'
import type { ChatMessage } from '@/stores/useChatStore'

const props = withDefaults(defineProps<{
  message: ChatMessage
  /** The store is waiting for the assistant (drives the streaming dots on the last message). */
  isTyping?: boolean
  isLast?: boolean
  /** Display setting `showJson`: the metadata line is only shown when on. */
  showJson?: boolean
}>(), { isTyping: false, isLast: false, showJson: false })

const emit = defineEmits<{ 'citation-step': [stepId: string] }>()

const router = useRouter()
// #9479: entity anchors rendered by the shared formatter navigate in-app.
const handleContentClick = createEntityAnchorClickHandler(router)

// Sanitised at the sink: all three v-html bindings read this value (#19118, #21771).
const html = computed(() => sanitizeChatHtml(formatMessageContent(props.message.content, props.message.id)))
const contentClass = computed(() => getContentClass(props.message))
const model = computed(() => shownModel(props.message.metadata))
const citations = computed(() => messageCitations(props.message))
const streaming = computed(() => props.message.sender === 'assistant' && props.isTyping && props.isLast)
const showMetadata = computed(() =>
  props.showJson && props.message.sender === 'assistant' && !!props.message.metadata
  && Object.keys(props.message.metadata).length > 0,
)

/** Image/video cells render on the top-level type or on the backend's `display_type`. */
function isRich(kind: 'image' | 'video'): boolean {
  return props.message.type === kind || props.message.metadata?.display_type === kind
}

/** #21976: a citation that is a tool step scrolls to that step's messages. */
function openCitationStep(citation: { step_id?: string }) {
  if (citation.step_id) emit('citation-step', citation.step_id)
}

/** Fields the older message view read; absent on most messages, so each is optional. */
const thinkingMetadata = computed(() => (props.message as { thinking_metadata?: { used?: boolean; tokens_used?: number } }).thinking_metadata)
const isModelOnlyClaim = computed(() => {
  const grounding = (props.message as { grounding?: { grounded?: boolean } }).grounding
  return props.message.sender === 'assistant' && grounding != null && grounding.grounded === false
})

/** Download through the browser from the attachment's own URL, via the kit's one file-save helper (#20770). */
function downloadAttachment(attachment: { url?: string; name?: string }) {
  if (attachment.url) saveUrl(attachment.url, attachment.name ?? '')
}

function viewAttachment(attachment: { url?: string }) {
  if (attachment.url) window.open(attachment.url, '_blank')
}
</script>

<style scoped>
.message-content { font-size: var(--aui-text-sm); line-height: 1.4; }
.message-text { overflow-wrap: anywhere; line-height: 1.4; }
.streaming-content { display: flex; flex-direction: column; gap: var(--aui-space-2); }
.user-content { color: var(--aui-color-primary-contrast); }
.assistant-content { color: var(--aui-color-text); }

.message-text :deep(code) {
  padding: 0 var(--aui-space-1);
  border-radius: var(--aui-radius-sm);
  background: var(--aui-color-surface-sunken);
  font-family: var(--aui-font-mono);
  font-size: var(--aui-text-xs);
}
.message-text :deep(pre) {
  margin-block: var(--aui-space-2);
  padding: var(--aui-space-3);
  overflow-x: auto;
  border-radius: var(--aui-radius-lg);
  background: var(--aui-color-surface-sunken);
}
.message-text :deep(a) { color: var(--aui-color-primary); text-decoration: underline; }
.user-content .message-text :deep(code),
.user-content .message-text :deep(pre) {
  background: transparent;
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--aui-color-primary-contrast) 40%, transparent);
  color: var(--aui-color-primary-contrast);
}
.user-content .message-text :deep(a) { color: var(--aui-color-primary-contrast); }

.message-metadata {
  margin-block-start: var(--aui-space-2);
  padding-block-start: var(--aui-space-1);
  border-block-start: 1px solid var(--aui-color-border);
}
.metadata-items {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--aui-space-2);
  color: var(--aui-color-text-muted);
  font-family: var(--aui-font-mono);
  font-size: var(--aui-text-xs);
}
.metadata-item { display: inline-flex; align-items: center; gap: var(--aui-space-1); }

.typing-indicator { display: flex; align-items: center; gap: var(--aui-space-2); }
.typing-dots { display: flex; gap: var(--aui-space-1); }
.typing-dots span {
  inline-size: var(--aui-space-2);
  block-size: var(--aui-space-2);
  border-radius: var(--aui-radius-full);
  background: var(--aui-color-text-muted);
  animation: typing-pulse 1.2s ease-in-out infinite;
}
.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes typing-pulse { 50% { opacity: 0.3; } }
@media (prefers-reduced-motion: reduce) { .typing-dots span { animation: none; } }

/* MVA-2006: context-compression summary, an info card */
.summary-message {
  margin-block-end: var(--aui-space-2);
  padding: var(--aui-space-3);
  border: 1px solid color-mix(in srgb, var(--aui-color-info) 40%, transparent);
  border-radius: var(--aui-radius-lg);
  background: color-mix(in srgb, var(--aui-color-info) 8%, var(--aui-color-surface-raised));
}
.summary-header {
  display: flex;
  align-items: center;
  gap: var(--aui-space-2);
  margin-block-end: var(--aui-space-2);
  font-weight: var(--aui-font-weight-semibold);
}
.summary-toggle { cursor: pointer; color: var(--aui-color-info); font-size: var(--aui-text-sm); user-select: none; }
.summary-content {
  margin-block-start: var(--aui-space-2);
  padding-block-start: var(--aui-space-2);
  border-block-start: 1px solid var(--aui-color-border);
  color: var(--aui-color-text-muted);
  font-size: var(--aui-text-sm);
}
</style>
