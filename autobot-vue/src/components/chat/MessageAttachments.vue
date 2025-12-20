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
.message-attachments {
  margin-top: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
}

.attachment-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
  font-size: 13px;
  font-weight: 500;
  color: #64748b;
}

.attachment-list {
  padding: 4px;
}

.attachment-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
}

.attachment-item:hover {
  background: #f1f5f9;
}

.attachment-item i:first-child {
  width: 20px;
  text-align: center;
  color: #64748b;
  font-size: 16px;
}

.attachment-name {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: #334155;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.attachment-size {
  flex-shrink: 0;
  font-size: 12px;
  color: #94a3b8;
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
  color: #64748b;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.attachment-download:hover {
  background: #e2e8f0;
  color: #334155;
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
