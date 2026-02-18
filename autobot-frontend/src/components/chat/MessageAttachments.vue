<template>
  <div v-if="attachments && attachments.length > 0" class="message-attachments">
    <div class="attachment-header">
      <i class="fas fa-paperclip" aria-hidden="true"></i>
      <span>{{ attachments.length }} attachment{{ attachments.length > 1 ? 's' : '' }}</span>
    </div>
    <div class="attachment-list">
      <div
        v-for="attachment in attachments"
        :key="attachment.id"
        class="attachment-item"
        @click="$emit('view', attachment)"
      >
        <i :class="getAttachmentIcon(attachment.type)" aria-hidden="true"></i>
        <span class="attachment-name">{{ attachment.name }}</span>
        <span class="attachment-size">{{ formatSize(attachment.size) }}</span>
        <button
          class="attachment-download"
          @click.stop="$emit('download', attachment)"
          :aria-label="`Download ${attachment.name}`"
        >
          <i class="fas fa-download" aria-hidden="true"></i>
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

const getAttachmentIcon = (type: string): string => {
  const iconMap: Record<string, string> = {
    image: 'fas fa-file-image',
    video: 'fas fa-file-video',
    audio: 'fas fa-file-audio',
    pdf: 'fas fa-file-pdf',
    document: 'fas fa-file-word',
    spreadsheet: 'fas fa-file-excel',
    code: 'fas fa-file-code',
    archive: 'fas fa-file-archive',
    text: 'fas fa-file-alt'
  }

  // Check for specific types
  if (type.startsWith('image/')) return iconMap.image
  if (type.startsWith('video/')) return iconMap.video
  if (type.startsWith('audio/')) return iconMap.audio
  if (type === 'application/pdf') return iconMap.pdf
  if (type.includes('word') || type.includes('document')) return iconMap.document
  if (type.includes('excel') || type.includes('spreadsheet')) return iconMap.spreadsheet
  if (type.includes('zip') || type.includes('tar') || type.includes('rar')) return iconMap.archive
  if (
    type.includes('javascript') ||
    type.includes('python') ||
    type.includes('typescript') ||
    type.includes('json')
  )
    return iconMap.code
  if (type.startsWith('text/')) return iconMap.text

  return 'fas fa-file'
}

const formatSize = (bytes: number): string => {
  if (!bytes || bytes === 0) return '0 B'

  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const k = 1024
  const i = Math.floor(Math.log(bytes) / Math.log(k))

  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + units[i]
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

.attachment-item i:first-child {
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
    margin-left: 30px;
    margin-top: -4px;
  }
}
</style>
