<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ChatFilePanelUpload -- the Chat files panel's upload target (#22349): one real button that opens the file
  picker and also accepts a drop, with the kit progress bar while an upload is between 1 and 99 percent.
  The kit has no drop-zone primitive yet; it is built once with the composer's (#22202), so this keeps its input.
-->
<template>
  <div class="p-3 border-b border-autobot-border shrink-0">
    <button
      type="button"
      class="upload-area w-full rounded-lg p-3 text-center transition-colors"
      :class="{ 'upload-area--dragging': isDragging }"
      :disabled="loading"
      data-testid="upload-target"
      @click="input?.click()"
      @dragover.prevent="isDragging = true"
      @dragleave.prevent="isDragging = false"
      @drop.prevent="onDrop"
    >
      <Icon name="cloud-upload-alt" class="text-2xl mb-1" />
      <span class="block text-xs text-autobot-text-secondary">
        {{ isDragging ? $t('chat.filePanel.dropFiles') : $t('chat.filePanel.clickOrDrag') }}
      </span>
    </button>
    <input ref="input" type="file" multiple class="hidden" data-testid="upload-input" :disabled="loading" @change="onSelect" />
    <div v-if="progress > 0 && progress < 100" class="mt-2" data-testid="upload-progress">
      <div class="flex items-center justify-between text-xs text-autobot-text-secondary mb-1">
        <span>{{ $t('chat.filePanel.uploading') }}</span>
        <span>{{ progress }}%</span>
      </div>
      <BaseProgress :value="progress" :label="$t('chat.filePanel.uploading')" size="sm" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { BaseProgress } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'

defineProps<{ loading: boolean; progress: number }>()
const emit = defineEmits<{ files: [files: File[]] }>()

const input = ref<HTMLInputElement>()
const isDragging = ref(false)

function onSelect(event: Event): void {
  const target = event.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    emit('files', Array.from(target.files))
    target.value = ''
  }
}

function onDrop(event: DragEvent): void {
  isDragging.value = false
  if (event.dataTransfer?.files && event.dataTransfer.files.length > 0) emit('files', Array.from(event.dataTransfer.files))
}
</script>

<style scoped>
.upload-area {
  border: 2px dashed var(--aui-color-border);
  background: var(--aui-color-surface-sunken);
  color: var(--aui-color-text);
  cursor: pointer;
}
.upload-area:hover:not(:disabled),
.upload-area--dragging {
  border-color: var(--aui-color-primary);
  background: var(--aui-color-surface-raised);
}
.upload-area:focus-visible {
  outline: var(--aui-focus-ring-width) solid var(--aui-color-focus-ring);
  outline-offset: 2px;
}
.upload-area:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
</style>
