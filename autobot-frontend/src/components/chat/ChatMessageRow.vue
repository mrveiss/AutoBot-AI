<template>
  <div class="message-wrapper" :class="wrapperClass">
    <div class="message-header">
      <div class="message-ident">
        <div class="message-avatar" :class="message.sender">
          <Icon :name="senderIcon" />
        </div>
        <div class="message-info">
          <span class="sender-name">
            {{ senderName }}
            <span v-if="message.sender === 'assistant' && model" class="model-name">({{ model }})</span>
          </span>
          <!-- MVA-1993: lightweight mode cost indicator -->
          <BaseBadge
            v-if="message.sender === 'assistant' && message.metadata?.lightweight_mode_used"
            variant="info"
            size="xs"
            :rounded="false"
            :title="$t('chat.lightweightModeTooltip')"
          >
            <Icon name="bolt" />
            {{ $t('chat.lightweightMode') }}
          </BaseBadge>
          <!-- #11997: opt-in provider-fallback chip (off by default) -->
          <ProviderFallbackChip v-if="message.sender === 'assistant'" :fallback-info="fallbackInfo" />
          <!-- Issue #1310: visible type badge for typed messages -->
          <BaseBadge v-if="typeBadge" :variant="badgeVariant" size="xs" :rounded="false">
            <Icon :name="typeBadge.icon" />
            {{ typeBadge.label }}
          </BaseBadge>
          <span class="message-time">{{ formatTime(message.timestamp) }}</span>
        </div>
      </div>

      <div class="message-actions">
        <BaseButton
          v-if="message.sender === 'user'"
          variant="ghost"
          size="xs"
          :aria-label="$t('chat.editMessage')"
          :title="$t('chat.editMessage')"
          @click="emit('edit', message)"
        >
          <Icon name="edit" />
        </BaseButton>
        <BaseButton
          variant="ghost"
          size="xs"
          :aria-label="$t('chat.copyMessage')"
          :title="$t('chat.copyMessage')"
          @click="emit('copy', message)"
        >
          <Icon name="copy" />
        </BaseButton>
        <!-- Issue #3245: save an assistant response as a persistent AI document -->
        <BaseButton
          v-if="message.sender === 'assistant'"
          variant="ghost"
          size="xs"
          :disabled="isSavingDocument"
          :aria-label="$t('chat.message.saveAsDocument')"
          :title="$t('chat.message.saveAsDocument')"
          @click="saveAsDocument"
        >
          <Icon name="file-alt" />
        </BaseButton>
        <BaseButton
          variant="ghost"
          size="xs"
          :aria-label="$t('chat.deleteMessage')"
          :title="$t('chat.deleteMessage')"
          @click="emit('delete', message)"
        >
          <Icon name="trash" />
        </BaseButton>
      </div>
    </div>

    <div v-if="message.sender === 'user'" class="message-status-container">
      <MessageStatus
        :status="(message.status === 'error' ? 'failed' : message.status) || 'sent'"
        :show-text="true"
        :timestamp="message.timestamp"
        :error="message.error"
        @retry="emit('retry', message.id)"
      />
    </div>

    <slot />
  </div>
</template>

<script setup lang="ts">
/**
 * One message row of the chat stream (#18243, step 5a batch 2): the bubble frame, the header
 * (avatar, sender, badges, edit/copy/delete) and the user send-status. The body is the slot.
 * Split out of ChatMessages.vue; behaviour is unchanged.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseBadge, BaseButton } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import MessageStatus from '@/components/ui/MessageStatus.vue'
import ProviderFallbackChip from '@/components/chat/ProviderFallbackChip.vue'
import type { ProviderFallbackPayload } from '@/constants/providerFallbackEvents'
import {
  getMessageTypeBadge,
  getMessageWrapperClass,
  getSenderIcon,
  getSenderName,
  messageTypeOf,
} from '@/composables/chat/useChatMessageView'
import { useAIDocument } from '@/composables/useAIDocument'
import { formatTime } from '@/utils/formatHelpers'
import { shownModel } from '@/utils/internalMessage'
import type { ChatMessage } from '@/stores/useChatStore'

const props = withDefaults(defineProps<{
  message: ChatMessage
  fallbackInfo?: ProviderFallbackPayload | null
}>(), { fallbackInfo: null })

const emit = defineEmits<{
  edit: [message: ChatMessage]
  copy: [message: ChatMessage]
  delete: [message: ChatMessage]
  retry: [messageId: string]
  /** Issue #3245: emitted with the new document id after an assistant message is saved. */
  'save-as-document': [docId: string]
}>()

const { t } = useI18n()

const { saveMessageAsDocument } = useAIDocument()
const isSavingDocument = ref(false)

async function saveAsDocument() {
  if (isSavingDocument.value) return
  isSavingDocument.value = true
  try {
    const doc = await saveMessageAsDocument({ content: props.message.content, messageId: props.message.id })
    emit('save-as-document', doc.id)
  } finally {
    isSavingDocument.value = false
  }
}

const wrapperClass = computed(() => getMessageWrapperClass(props.message))
const senderIcon = computed(() => getSenderIcon(props.message.sender, messageTypeOf(props.message)))
const senderName = computed(() => getSenderName(props.message.sender, t))
const model = computed(() => shownModel(props.message.metadata))
const typeBadge = computed(() => getMessageTypeBadge(props.message, t))
/** thought, planning and sources read as info; debug as a warning; utility stays neutral. */
const badgeVariant = computed(() => {
  const type = typeBadge.value?.type
  if (type === 'debug') return 'warning'
  return type === 'utility' ? 'neutral' : 'info'
})
</script>

<style scoped>
.message-wrapper {
  --msg-accent: var(--aui-color-border);
  position: relative;
  max-width: 85%;
  padding: var(--aui-space-2) var(--aui-space-3);
  border: 1px solid var(--aui-color-border);
  border-radius: var(--aui-radius-lg);
  background: var(--aui-color-surface-raised);
  color: var(--aui-color-text);
  animation: message-in var(--aui-transition) ease-out;
}

/* Type themes: one accent per type, every tint derived from it (no per-type colour copies). */
.message-wrapper.type-thought,
.message-wrapper.type-planning,
.message-wrapper.type-sources,
.message-wrapper.type-json { --msg-accent: var(--aui-color-info); }
.message-wrapper.type-debug,
.message-wrapper.type-command_approval_request { --msg-accent: var(--aui-color-warning); }
.message-wrapper.type-terminal_output { --msg-accent: var(--aui-color-success); }
.message-wrapper[class*='type-'] {
  border-color: color-mix(in srgb, var(--msg-accent) 40%, transparent);
  background: color-mix(in srgb, var(--msg-accent) 8%, var(--aui-color-surface-raised));
}
.message-wrapper.type-terminal_output { background: var(--aui-color-surface-sunken); }
.message-wrapper.type-debug { font-family: var(--aui-font-mono); }
.message-wrapper.type-thought .message-avatar,
.message-wrapper.type-planning .message-avatar,
.message-wrapper.type-sources .message-avatar,
.message-wrapper.type-json .message-avatar,
.message-wrapper.type-debug .message-avatar,
.message-wrapper.type-command_approval_request .message-avatar,
.message-wrapper.type-terminal_output .message-avatar {
  background: var(--msg-accent);
  color: var(--aui-color-primary-contrast);
}

/* Sender frames: the user bubble follows the mockup radius (10 10 2 10). */
.message-wrapper.user-message {
  margin-inline-start: auto;
  background: var(--aui-color-primary);
  border-color: var(--aui-color-primary);
  color: var(--aui-color-primary-contrast);
  border-radius: var(--aui-radius-lg) var(--aui-radius-lg) 2px var(--aui-radius-lg);
}
.message-wrapper.assistant-message { margin-inline-end: auto; }
.message-wrapper.system-message {
  margin-inline: auto;
  max-width: 70%;
  background: var(--aui-color-surface-sunken);
  color: var(--aui-color-text-muted);
}
.message-wrapper.sending { opacity: 0.7; }
.message-wrapper.error {
  background: color-mix(in srgb, var(--aui-color-error) 10%, var(--aui-color-surface-raised));
  border-color: color-mix(in srgb, var(--aui-color-error) 30%, transparent);
  color: var(--aui-color-error);
}

.message-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: var(--aui-space-1); }
.message-ident { display: flex; align-items: center; gap: var(--aui-space-2); }
.message-info { display: flex; flex-wrap: wrap; align-items: center; gap: var(--aui-space-1) var(--aui-space-2); }
.sender-name { font-size: var(--aui-text-xs); font-weight: var(--aui-font-weight-semibold); }
.model-name { margin-inline-start: var(--aui-space-1); font-weight: normal; opacity: 0.8; }
.message-time { font-size: var(--aui-text-xs); color: var(--aui-color-text-muted); }
.user-message .sender-name,
.user-message .message-time { color: var(--aui-color-primary-contrast); }

.message-avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  inline-size: var(--aui-space-6);
  block-size: var(--aui-space-6);
  border-radius: var(--aui-radius-full);
  background: var(--aui-color-surface-sunken);
  color: var(--aui-color-text);
  font-size: var(--aui-text-xs);
}
.message-avatar.user { background: var(--aui-color-primary); color: var(--aui-color-primary-contrast); }

/* Actions appear on hover and on keyboard focus (the old `group-hover` had no `group`), and are
   always visible where there is no hover (touch). */
.message-actions { display: flex; gap: var(--aui-space-1); opacity: 0; transition: opacity var(--aui-transition-fast); }
.message-wrapper:hover .message-actions,
.message-wrapper:focus-within .message-actions { opacity: 1; }
@media (hover: none) { .message-actions { opacity: 1; } }
.message-status-container { display: flex; justify-content: flex-end; margin-block: var(--aui-space-1); }

@keyframes message-in {
  from { opacity: 0; transform: translateY(15px); }
  to { opacity: 1; transform: translateY(0); }
}
@media (prefers-reduced-motion: reduce) { .message-wrapper { animation: none; } }
@media (max-width: 768px) {
  .message-avatar { inline-size: var(--aui-space-5); block-size: var(--aui-space-5); }
}
</style>
