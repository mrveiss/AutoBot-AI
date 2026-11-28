<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  The modal pane for the server-built preview of a listed text attachment (#20906), on the kit `BaseModal`
  (#22349). Mounted by the parent with v-if, so focus is saved when it opens and returned to the trigger when it
  unmounts; Escape, the close button and the backdrop close it, Tab stays inside it, and the text area is
  keyboard-scrollable.
-->
<template>
  <BaseModal
    :model-value="true"
    :title="preview?.filename ?? $t('chat.filePanel.previewLoading')"
    :close-label="$t('chat.filePanel.closePreview')"
    size="md"
    data-testid="file-preview-pane"
    @close="emit('close')"
  >
    <p v-if="!preview" class="text-xs text-autobot-text-muted" role="status" data-testid="file-preview-loading">
      {{ $t('chat.filePanel.previewLoading') }}
    </p>
    <template v-else>
      <pre
        class="overflow-auto max-h-[60vh] text-xs font-mono whitespace-pre-wrap break-words"
        tabindex="0"
        :aria-label="$t('chat.filePanel.previewContentLabel', { name: preview.filename })"
        data-testid="file-preview-content"
      >{{ preview.data.preview_content || $t('chat.filePanel.previewEmpty') }}</pre>
      <p v-if="preview.truncated" class="mt-2 text-xs text-autobot-text-muted" data-testid="file-preview-truncated">
        {{ $t('chat.filePanel.previewTruncated') }}
      </p>
    </template>
  </BaseModal>
</template>

<script setup lang="ts">
import { BaseModal } from '@autobot/ui'
import type { PreviewPane } from '@/composables/useConversationFiles'

defineProps<{ preview: PreviewPane | null }>()
const emit = defineEmits<{ close: [] }>()
</script>
