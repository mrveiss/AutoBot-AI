<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  The Files tab preview dialog on the kit `BaseModal` (#22349): focus is saved on open and restored on close, Tab
  stays inside, and Escape, the close button and the backdrop emit `close`.
-->
<template>
  <BaseModal
    v-if="previewFile"
    :model-value="showPreview"
    :title="previewFile.name"
    :close-label="$t('fileBrowser.preview.closeAriaLabel')"
    size="md"
    data-testid="file-preview-modal"
    @close="$emit('close')"
  >
    <div v-if="previewFile.type === 'html'" class="html-preview">
      <iframe
        :src="previewFile.url"
        class="preview-frame"
        sandbox="allow-same-origin allow-scripts"
        :title="$t('fileBrowser.preview.htmlPreview')"
      ></iframe>
    </div>
    <div v-else-if="previewFile.type === 'image'" class="image-preview">
      <img :src="previewFile.url" :alt="previewFile.name" class="preview-image" loading="lazy" />
    </div>
    <div v-else-if="previewFile.type === 'text'" class="text-preview">
      <pre tabindex="0"><code>{{ previewFile.content }}</code></pre>
    </div>
    <div v-else-if="previewFile.type === 'json'" class="json-preview">
      <pre tabindex="0"><code>{{ formatJson(previewFile.content || '') }}</code></pre>
    </div>
    <div v-else-if="previewFile.type === 'pdf'" class="pdf-preview">
      <iframe :src="previewFile.url" class="preview-frame" :title="$t('fileBrowser.preview.pdfPreview')"></iframe>
    </div>
    <div v-else class="file-info">
      <div class="info-item">
        <strong>{{ $t('fileBrowser.preview.file') }}</strong> {{ previewFile.name }}
      </div>
      <div class="info-item">
        <strong>{{ $t('fileBrowser.preview.type') }}</strong> {{ previewFile.fileType }}
      </div>
      <div class="info-item">
        <strong>{{ $t('fileBrowser.preview.size') }}</strong> {{ formatFileSize(previewFile.size, sizeOptions) }}
      </div>
      <p class="no-preview-message">{{ $t('fileBrowser.preview.noPreview') }}</p>
      <BaseButton variant="primary" data-testid="preview-download" @click="downloadFile">
        <Icon name="download" />
        {{ $t('fileBrowser.preview.downloadFile') }}
      </BaseButton>
    </div>
  </BaseModal>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { BaseButton, BaseModal } from '@autobot/ui'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { formatFileSize, fileBrowserSizeOptions } from '@/utils/formatHelpers'

interface FilePreviewData {
  name: string
  type: string
  url?: string
  content?: string
  fileType?: string
  size?: number
}

interface Props {
  showPreview: boolean
  previewFile: FilePreviewData | null
}

interface Emits {
  (e: 'close'): void
  (e: 'download', file: FilePreviewData): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const { t } = useI18n()
const sizeOptions = computed(() => fileBrowserSizeOptions(t('fileBrowser.zeroSize')))

// Methods
const formatJson = (content: string): string => {
  try {
    return JSON.stringify(JSON.parse(content), null, 2)
  } catch {
    return content
  }
}

const downloadFile = () => {
  if (props.previewFile) {
    emit('download', props.previewFile)
  }
}
</script>

<style scoped>
.preview-frame {
  width: 100%;
  height: 24rem;
  border: 1px solid var(--aui-color-border);
  border-radius: var(--aui-radius-md);
}
.preview-image {
  max-width: 100%;
  height: auto;
  border-radius: var(--aui-radius-md);
}
.text-preview pre,
.json-preview pre {
  margin: 0;
  padding: var(--aui-space-4);
  overflow: auto;
  max-height: 60vh;
  background: var(--aui-color-surface-sunken);
  border-radius: var(--aui-radius-md);
  font-family: var(--aui-font-mono);
  font-size: var(--aui-text-sm);
  white-space: pre-wrap;
  word-break: break-word;
}
.file-info {
  text-align: center;
  padding: var(--aui-space-6) 0;
}
.info-item {
  margin-bottom: var(--aui-space-2);
  font-size: var(--aui-text-sm);
}
.no-preview-message {
  margin: var(--aui-space-4) 0 var(--aui-space-6);
  color: var(--aui-color-text-muted);
}
</style>
