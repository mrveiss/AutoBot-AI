<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  KnowledgeUploadFiles — "Upload files" of Knowledge · Manage · Upload (#747, #18244): the drop
  zone, the picked files with previews, the category and tags for all of them, and the upload.
-->
<template>
  <BaseCard :title="$t('knowledge.upload.uploadFiles')">
    <template #actions>
      <BaseBadge v-if="files.selectedFiles.value.length > 0" :label="String(files.selectedFiles.value.length)" size="sm" />
    </template>

    <div class="flex flex-col gap-3">
      <div
        class="file-drop-zone flex cursor-pointer flex-col items-center gap-1 rounded-lg border-2 border-dashed bg-[var(--surface2)] p-6 text-center text-[var(--muted)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent)]"
        :class="[dropZoneTone, { dragging: files.isDragging.value, 'has-files': files.selectedFiles.value.length > 0 }]"
        role="button"
        tabindex="0"
        @drop="files.onDrop"
        @dragover.prevent="files.onDragOver"
        @dragenter.prevent="files.onDragEnter"
        @dragleave="files.onDragLeave"
        @click="files.fileInput.value?.click()"
        @keydown.enter.prevent="files.fileInput.value?.click()"
      >
        <input :ref="files.fileInput" type="file" multiple hidden :accept="files.uploadAccept.value" @change="files.onFileSelect" />
        <Icon :name="files.dropZoneIcon.value" aria-hidden="true" />
        <p class="m-0">
          <template v-if="files.isDragging.value">
            {{ files.dragValid.value ? $t('knowledge.upload.dropToAdd') : $t('knowledge.upload.invalidFileType') }}
          </template>
          <template v-else>{{ $t('knowledge.upload.dragAndDrop') }} <span class="text-[var(--accent)] underline">{{ $t('knowledge.upload.browse') }}</span></template>
        </p>
        <p v-if="!files.isDragging.value" class="m-0 text-xs">{{ $t('knowledge.upload.supportedFormats') }}</p>
      </div>

      <div v-if="files.selectedFiles.value.length > 0" class="selected-files flex flex-col gap-3">
        <div class="flex items-center justify-between">
          <h5 class="m-0 text-[var(--text)]">
            <Icon name="folder-open" aria-hidden="true" />
            {{ $t('knowledge.upload.filesSelected', { count: files.selectedFiles.value.length }, files.selectedFiles.value.length) }}
          </h5>
          <BaseButton variant="ghost" size="sm" class="clear-all-btn" :title="$t('knowledge.upload.clearAllTitle')" @click="files.clearAllFiles">
            <Icon name="trash-alt" aria-hidden="true" />{{ $t('knowledge.upload.clearAll') }}
          </BaseButton>
        </div>
        <ul class="m-0 flex list-none flex-col gap-2 p-0" :aria-label="$t('knowledge.upload.filesAria')">
          <KnowledgeUploadFileItem
            v-for="(item, index) in files.selectedFiles.value"
            :key="item.id"
            :item="item"
            :expanded="files.isFileExpanded(item.id)"
            @toggle="files.toggleFilePreview"
            @remove="files.removeFile(index)"
          />
        </ul>
      </div>

      <div v-if="files.selectedFiles.value.length > 0" class="batch-options flex flex-col gap-3">
        <div class="grid grid-cols-[repeat(auto-fit,minmax(14rem,1fr))] gap-3">
          <BaseSelectMenu
            v-model="category"
            :label="hasAuto ? `${$t('knowledge.upload.categoryForAll')} ${$t('knowledge.upload.orAutoDetected')}` : $t('knowledge.upload.categoryForAll')"
            :placeholder="hasAuto ? $t('knowledge.upload.useAutoDetected') : $t('knowledge.upload.selectCategory')"
            :options="categoryOptions"
          />
          <BaseInput v-model="files.fileEntry.tagsInput" :label="$t('knowledge.upload.tagsForAll')" :placeholder="$t('knowledge.upload.tagsPlaceholder')" />
        </div>
        <BaseButton variant="primary" class="upload-btn self-start" :disabled="feedback.isSubmitting.value" :loading="feedback.isSubmitting.value" @click="files.uploadFiles">
          <template v-if="feedback.isSubmitting.value">{{ $t('knowledge.upload.uploading') }}</template>
          <template v-else>
            <Icon name="cloud-upload-alt" aria-hidden="true" />{{ $t('knowledge.upload.uploadNFiles', { count: files.selectedFiles.value.length }, files.selectedFiles.value.length) }}
          </template>
        </BaseButton>
      </div>
    </div>
  </BaseCard>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { BaseBadge, BaseButton, BaseCard, BaseInput, BaseSelectMenu } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import { useKnowledgeUploadFiles } from '@/composables/knowledge/useKnowledgeUploadFiles'
import type { UploadFeedback } from '@/composables/knowledge/useKnowledgeUploadFeedback'
import KnowledgeUploadFileItem from './KnowledgeUploadFileItem.vue'

const props = defineProps<{ feedback: UploadFeedback; accept: string }>()

const store = useKnowledgeStore()
const files = useKnowledgeUploadFiles(props.feedback, props.accept)

const hasAuto = files.hasAutoCategories
const category = computed({
  get: () => files.fileEntry.category || undefined,
  set: (value) => { files.fileEntry.category = value ?? '' },
})
// The drop zone's border says whether what is being dragged can be added.
const dropZoneTone = computed(() => {
  if (!files.isDragging.value) return 'border-[var(--border)]'
  return files.dragValid.value ? 'border-[var(--accent)]' : 'border-[var(--bad-fg)]'
})
const categoryOptions = computed(() => store.categories.map((c) => ({ value: c.name, label: c.name })))

onMounted(files.onMount)
</script>
