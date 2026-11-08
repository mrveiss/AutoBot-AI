<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!--
  The modal pane for the server-built preview of a listed text attachment (#20906).
  Mounted by the parent with v-if, so focus is saved on mount and restored to the trigger on unmount;
  Escape and the backdrop close it, Tab stays inside it, and the text area is keyboard-scrollable.
-->
<template>
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
    data-testid="file-preview-pane"
    @click.self="emit('close')"
  >
    <div
      ref="dialogRef"
      class="bg-autobot-bg-card rounded-lg shadow-xl w-[480px] max-h-[80vh] flex flex-col p-4"
      role="dialog"
      aria-modal="true"
      tabindex="-1"
      :aria-label="preview?.filename ?? $t('chat.filePanel.previewLoading')"
      @keydown="onTrapKeydown"
      @keydown.escape="emit('close')"
    >
      <div class="flex items-center justify-between mb-3">
        <h4 class="text-sm font-semibold text-autobot-text-primary truncate">{{ preview?.filename }}</h4>
        <button class="action-btn" :aria-label="$t('chat.filePanel.closePreview')" data-testid="file-preview-close" @click="emit('close')">
          <Icon name="times" class="text-xs" />
        </button>
      </div>
      <p v-if="!preview" class="text-xs text-autobot-text-muted" role="status" data-testid="file-preview-loading">
        {{ $t('chat.filePanel.previewLoading') }}
      </p>
      <template v-else>
        <pre
          class="flex-1 overflow-auto text-xs font-mono whitespace-pre-wrap break-words"
          tabindex="0"
          :aria-label="$t('chat.filePanel.previewContentLabel', { name: preview.filename })"
          data-testid="file-preview-content"
        >{{ preview.data.preview_content || $t('chat.filePanel.previewEmpty') }}</pre>
        <p v-if="preview.truncated" class="mt-2 text-xs text-autobot-text-muted" data-testid="file-preview-truncated">
          {{ $t('chat.filePanel.previewTruncated') }}
        </p>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useFocusRestore, useFocusTrap, useInitialFocus } from '@autobot/ui'
import Icon from '@/components/ui/Icon.vue'
import type { PreviewPane } from '@/composables/useConversationFiles'

defineProps<{ preview: PreviewPane | null }>()
const emit = defineEmits<{ close: [] }>()

const dialogRef = ref<HTMLElement | null>(null)
const { onKeydown: onTrapKeydown } = useFocusTrap(dialogRef)
useFocusRestore()
const { focusFirst } = useInitialFocus(dialogRef)
onMounted(focusFirst)
</script>

<style scoped>
@reference "../../assets/tailwind.css";
.action-btn {
  @apply w-6 h-6 flex items-center justify-center rounded transition-colors text-autobot-text-muted hover:text-autobot-text-secondary hover:bg-autobot-bg-secondary;
}
</style>
