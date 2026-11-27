<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  KnowledgeUploadFileItem — one picked file of the upload list (#747, #18244): icon, name, size,
  the auto-detected category, its upload progress or result, and the expandable content preview.
-->
<template>
  <li class="file-item flex flex-col gap-2 rounded-md border bg-[var(--surface)] p-3" :class="[item.status, item.status === 'failed' ? 'border-[var(--bad-fg)]' : 'border-[var(--border)]', { expanded }]">
    <div class="flex cursor-pointer items-center gap-3" @click="emit('toggle', item.id)">
      <Icon :name="getFileIcon(item.file.name, false)" aria-hidden="true" />
      <div class="flex min-w-0 flex-1 flex-col">
        <span class="file-name truncate text-[var(--text)]" :title="item.file.name">{{ truncateFileName(item.file.name, NAME_MAX) }}</span>
        <span class="inline-flex items-center gap-2 text-xs text-[var(--muted)]">
          {{ formatFileSize(item.file.size) }} {{ getFileExtension(item.file.name) }}
          <BaseBadge
            v-if="item.suggestedCategory"
            size="sm"
            :label="item.suggestedCategory"
            :title="$t('knowledge.upload.autoDetectedCategory', { category: item.suggestedCategory })"
          />
        </span>
      </div>
      <BaseButton
        v-if="item.previewAvailable"
        variant="ghost"
        size="xs"
        class="preview-toggle-btn"
        :aria-label="$t('knowledge.upload.previewContentTitle')"
        :aria-expanded="expanded"
        @click.stop="emit('toggle', item.id)"
      >
        <Icon :name="expanded ? 'chevron-up' : 'eye'" aria-hidden="true" />
      </BaseButton>
      <BaseButton variant="ghost" size="xs" class="remove-file-btn" :aria-label="$t('knowledge.upload.removeFileTitle')" @click.stop="emit('remove')">
        <Icon name="times" aria-hidden="true" />
      </BaseButton>
    </div>

    <BaseProgress v-if="item.status === 'uploading'" :value="item.progress" :label="item.file.name" size="sm" />
    <p v-if="item.status === 'completed'" class="file-status success m-0 flex items-center gap-2 text-sm text-[var(--ok-fg)]">
      <Icon name="check-circle" aria-hidden="true" />{{ $t('knowledge.upload.uploadedSuccessfully') }}
    </p>
    <p v-if="item.status === 'failed'" class="file-status error m-0 flex items-center gap-2 text-sm text-[var(--bad-fg)]">
      <Icon name="exclamation-circle" aria-hidden="true" />{{ item.errorMessage || $t('knowledge.upload.uploadFailed') }}
    </p>

    <div v-if="expanded && item.preview" class="flex flex-col gap-2">
      <div class="flex justify-between text-xs text-[var(--muted)]">
        <span>{{ $t('knowledge.upload.contentPreview') }}</span>
        <span>{{ $t('knowledge.upload.previewChars', { shown: item.preview.length, total: item.fullContentLength ?? 0 }) }}</span>
      </div>
      <pre class="m-0 max-h-48 overflow-auto whitespace-pre-wrap rounded-sm bg-[var(--surface2)] p-2 font-mono text-xs text-[var(--text)]">{{ item.preview }}</pre>
      <p v-if="item.previewTruncated" class="m-0 flex items-center gap-2 text-xs text-[var(--muted)]">
        <Icon name="info-circle" aria-hidden="true" />{{ $t('knowledge.upload.previewTruncated') }}
      </p>
    </div>
  </li>
</template>

<script setup lang="ts">
import { BaseBadge, BaseButton, BaseProgress } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import { useKnowledgeIcons } from '@/composables/knowledge/useKnowledgeIcons'
import { getFileExtension, truncateFileName } from '@/composables/knowledge/knowledgeUploadFileUtils'
import type { FileItem } from '@/composables/knowledge/useKnowledgeUploadFiles'
import { formatFileSize } from '@/utils/formatHelpers'

defineProps<{ item: FileItem; expanded: boolean }>()
const emit = defineEmits<{ toggle: [id: string]; remove: [] }>()

const NAME_MAX = 35
const { getFileIcon } = useKnowledgeIcons()
</script>
