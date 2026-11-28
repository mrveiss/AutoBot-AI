<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  ChatComposerUploads -- the files of the message being composed (#18243): uploads in flight (progress,
  cancel, retry) and the attached files (remove one, clear all), as the Refined composer's file chips.
  Presentational: the state lives in `useComposerUploads`; this emits intents only.
-->
<template>
  <div>
    <ul v-if="uploads.length > 0" class="mb-3 flex max-h-48 list-none flex-col gap-2 overflow-y-auto p-0" :aria-label="$t('chat.input.uploadsInProgress')">
      <li v-for="upload in uploads" :key="upload.id" class="flex items-center gap-3 rounded-[var(--aui-radius-md)] border border-[var(--aui-color-border)] bg-[var(--aui-color-surface-raised)] px-3 py-2" data-testid="composer-upload">
        <div class="flex min-w-0 flex-1 flex-col">
          <span class="truncate text-sm font-medium text-[var(--aui-color-text)]">{{ upload.filename }}</span>
          <span class="text-xs" :class="upload.error ? 'text-[var(--aui-color-error)]' : 'text-[var(--aui-color-text-muted)]'">
            {{ upload.error || statusLabel(upload) }}
          </span>
          <ProgressBar
            :progress="upload.progress"
            :variant="upload.error ? 'error' : 'info'"
            :current="upload.current"
            :total="upload.total"
            :eta="upload.eta"
            size="sm"
            :show-details="true"
          />
        </div>
        <BaseButton
          v-if="isCancellable(upload)"
          variant="outline"
          size="xs"
          :aria-label="$t('chat.input.cancelUpload', { name: upload.filename })"
          @click="emit('cancel', upload.id)"
        >
          <Icon name="times" />
        </BaseButton>
        <BaseButton v-if="upload.error" variant="error" size="xs" :aria-label="$t('chat.input.retryUpload')" @click="emit('retry', upload.id)">
          <Icon name="redo" />
        </BaseButton>
      </li>
    </ul>

    <div v-if="files.length > 0" class="mb-3 flex max-h-48 flex-col gap-2 overflow-y-auto" role="group" :aria-label="$t('chat.input.filesAttached', { count: files.length })">
      <div class="flex items-center justify-between">
        <span class="inline-flex items-center gap-1 text-sm font-medium text-[var(--aui-color-text-muted)]">
          <Icon name="paperclip" size="sm" />
          {{ $t('chat.input.filesAttached', { count: files.length }) }}
        </span>
        <BaseButton variant="link" size="xs" @click="emit('clear-all')">{{ $t('chat.input.clearAll') }}</BaseButton>
      </div>
      <ul class="m-0 flex list-none flex-col gap-2 p-0">
        <li v-for="(file, index) in files" :key="index" class="flex items-center gap-3 rounded-[var(--aui-radius-md)] border border-[var(--aui-color-border)] bg-[var(--aui-color-surface-raised)] px-3 py-2" data-testid="composer-attached-file">
          <span class="inline-flex text-[var(--aui-color-text-muted)]" aria-hidden="true"><Icon :name="getFileIconNameByMimeType(file.type)" size="sm" /></span>
          <span class="flex min-w-0 flex-1 flex-col">
            <span class="truncate text-sm font-medium text-[var(--aui-color-text)]">{{ file.name }}</span>
            <span class="text-xs text-[var(--aui-color-text-muted)]">{{ formatFileSize(file.size) }}</span>
          </span>
          <BaseButton variant="ghost" size="xs" :aria-label="$t('chat.input.removeFileNamed', { name: file.name })" @click="emit('remove', index)">
            <Icon name="times" />
          </BaseButton>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { BaseButton } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import ProgressBar from '@/components/ui/ProgressBar.vue'
import { formatFileSize } from '@/utils/formatHelpers'
import { getFileIconNameByMimeType } from '@/utils/iconMappings'
import type { UploadItem } from '@/composables/chat/useComposerUploads'

defineProps<{
  uploads: UploadItem[]
  files: File[]
  isCancellable: (upload: UploadItem) => boolean
}>()
const emit = defineEmits<{ cancel: [id: string]; retry: [id: string]; remove: [index: number]; 'clear-all': [] }>()

const { t } = useI18n()

/** The row's status line: the phase, with the percentage once bytes are moving. */
function statusLabel(upload: UploadItem): string {
  if (upload.phase === 'uploading' && upload.progress > 0) {
    return t('chat.input.uploadStatus.uploadingPercent', { percent: Math.round(upload.progress) })
  }
  return t(`chat.input.uploadStatus.${upload.phase}`)
}
</script>
