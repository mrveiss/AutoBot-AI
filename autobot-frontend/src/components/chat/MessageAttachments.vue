<template>
  <div v-if="attachments && attachments.length > 0" class="message-attachments">
    <div class="attachment-header">
      <Icon name="paperclip" />
      <span>{{ $t('chat.messages.attachments', { count: attachments.length }, attachments.length) }}</span>
    </div>
    <div class="attachment-list">
      <div
        v-for="attachment in attachments"
        :key="attachment.id"
        class="attachment-item"
        role="button"
        tabindex="0"
        @click="$emit('view', attachment)"
        @keydown.enter.self="$emit('view', attachment)"
      >
        <Icon :name="getAttachmentIcon(attachment.type)" />
        <span class="attachment-name">{{ attachment.name }}</span>
        <span class="attachment-size">{{ formatFileSize(attachment.size) }}</span>
        <button
          class="attachment-download"
          @click.stop="$emit('download', attachment)"
          :aria-label="$t('chat.messages.downloadAttachment', { name: attachment.name })"
        >
          <Icon name="download" />
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Message Attachments Component
 *
 * Displays file attachments for chat messages.
 * Extracted from ChatMessages.vue for better maintainability.
 *
 * Issue #184: Split oversized Vue components
 */
import type { IconName } from '@/components/ui/Icon.vue'
import Icon from '@/components/ui/Icon.vue'
import { formatFileSize } from '@/utils/formatHelpers'

interface Attachment {
  id: string
  name: string
  type: string
  size: number
  url?: string
}

interface Props {
  attachments: Attachment[]
}

interface Emits {
  (e: 'view', attachment: Attachment): void
  (e: 'download', attachment: Attachment): void
}

defineProps<Props>()
defineEmits<Emits>()

/** The icon map and size format the message stream always used. */
const getAttachmentIcon = (type: string): IconName => {
  if (type.startsWith('image/')) return 'image'
  if (type.startsWith('video/')) return 'video'
  if (type.startsWith('audio/')) return 'music'
  if (type.includes('pdf')) return 'file-pdf'
  if (type.includes('word')) return 'file-word'
  if (type.includes('excel')) return 'file-excel'
  return 'file'
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.message-attachments {
  margin-top: var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.attachment-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2-5) var(--spacing-3-5);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-secondary);
}

.attachment-list {
  padding: var(--spacing-1);
}

.attachment-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  padding: var(--spacing-2-5) var(--spacing-3);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background var(--duration-200) var(--ease-in-out);
}

.attachment-item:hover {
  background: var(--bg-hover);
}

.attachment-item .icon:first-child {
  width: 20px;
  text-align: center;
  color: var(--text-secondary);
  font-size: var(--text-base);
}

.attachment-name {
  flex: 1;
  min-width: 0;
  font-size: var(--text-sm);
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.attachment-size {
  flex-shrink: 0;
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.attachment-download {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--duration-200) var(--ease-in-out);
}

.attachment-download:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

@media (max-width: 640px) {
  .attachment-item {
    flex-wrap: wrap;
  }

  .attachment-name {
    width: calc(100% - 50px);
  }

  .attachment-size {
    width: 100%;
    margin-left: var(--spacing-8);
    margin-top: var(--spacing-neg-4px);
  }
}
</style>
